from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.evaluation import (
    ExperimentMetricRow,
    ExperimentMetricsResponse,
    FailureClassificationEvidence,
    LlmDisplayEvidence,
    LlmOverride,
    ReplayMetricsContract,
    ResolvedLlmSpec,
    SourceContextPolicy,
    TestReplayContract,
    V2_PHASE0_DB_SCHEMA_DRAFT,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "eval" / "fixtures" / "mock_experiment_v2.json"


def _fixture_data() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_mock_experiment_fixture_validates_and_keeps_v1_metric_shape():
    response = ExperimentMetricsResponse.model_validate(_fixture_data())

    assert response.schema_version == "v2.phase0"
    assert response.data_source.kind == "mock"
    assert response.clean_runs
    assert response.replay_runs
    assert response.experiment_replay_runs

    legacy_row_keys = {
        "strategy_id",
        "strategy_name",
        "repeats",
        "captured_per_repeat",
        "captured_mean",
        "total_in_scope",
        "capture_rate_mean",
        "capture_rate_std",
        "false_positive_rate",
        "avg_tokens",
        "avg_tool_calls",
        "reflection_used",
        "cost_per_captured_bug",
    }
    for row in response.rows:
        assert legacy_row_keys.issubset(row.model_dump())

    for strategy_hits in response.capture_matrix.values():
        assert set(strategy_hits) == {row.strategy_id for row in response.rows}
        assert all(isinstance(value, bool) for value in strategy_hits.values())

    for clean_run in response.clean_runs:
        [inventory_item] = clean_run.report_quality.test_inventory
        assert inventory_item.source_path == "tests/generated/test_pricing.py"
        assert inventory_item.start_line <= inventory_item.end_line


def test_cost_per_captured_bug_cannot_fake_zero_capture_as_zero_cost():
    base = {
        "strategy_id": "sv-zero",
        "strategy_name": "Zero Capture",
        "repeats": 1,
        "captured_per_repeat": [0],
        "captured_mean": 0,
        "total_in_scope": 1,
        "capture_rate_mean": 0,
        "capture_rate_std": 0,
        "false_positive_rate": 0,
        "avg_tokens": 100,
        "avg_tool_calls": 1,
        "reflection_used": False,
        "data_source": "mock",
        "llm_display": LlmDisplayEvidence(
            provider="mock",
            model="scripted",
            derived_from_clean_run_ids=["ecr-zero"],
        ).model_dump(),
    }

    ok = ExperimentMetricRow.model_validate(
        base
        | {
            "metric_status": "evaluable_zero_capture",
            "cost_per_captured_bug": None,
            "cost_per_captured_bug_status": "no_bug_captured",
        }
    )
    assert ok.cost_per_captured_bug is None
    assert ok.metric_status == "evaluable_zero_capture"

    with pytest.raises(ValidationError):
        ExperimentMetricRow.model_validate(
            base
            | {
                "metric_status": "evaluable_zero_capture",
                "cost_per_captured_bug": 0,
                "cost_per_captured_bug_status": "ok",
            }
        )


def test_metric_row_separates_invalid_test_set_from_zero_capture():
    row = ExperimentMetricRow.model_validate(
        {
            "strategy_id": "sv-invalid",
            "strategy_name": "Invalid",
            "repeats": 0,
            "captured_per_repeat": [],
            "captured_mean": 0,
            "total_in_scope": 1,
            "capture_rate_mean": 0,
            "capture_rate_std": 0,
            "false_positive_rate": 0,
            "avg_tokens": 0,
            "avg_tool_calls": 0,
            "reflection_used": False,
            "invalid_test_set_count": 1,
            "metric_status": "invalid_test_set",
            "cost_per_captured_bug": None,
            "cost_per_captured_bug_status": "no_bug_captured",
            "data_source": "mock",
            "llm_display": LlmDisplayEvidence(
                provider="mock",
                model="scripted",
                derived_from_clean_run_ids=["ecr-invalid"],
            ).model_dump(),
        }
    )

    assert row.metric_status == "invalid_test_set"


def test_metric_row_rejects_repeat_and_mean_drift():
    base = {
        "strategy_id": "sv-drift",
        "strategy_name": "Drift",
        "repeats": 2,
        "captured_per_repeat": [1, 0],
        "captured_mean": 0.5,
        "total_in_scope": 2,
        "capture_rate_mean": 0.25,
        "capture_rate_std": 0,
        "false_positive_rate": 0,
        "avg_tokens": 100,
        "avg_tool_calls": 1,
        "reflection_used": False,
        "cost_per_captured_bug": 100,
        "cost_per_captured_bug_status": "ok",
        "data_source": "mock",
        "llm_display": LlmDisplayEvidence(
            provider="mock",
            model="scripted",
            derived_from_clean_run_ids=["ecr-drift"],
        ).model_dump(),
    }

    assert ExperimentMetricRow.model_validate(base).captured_mean == 0.5

    with pytest.raises(ValidationError):
        ExperimentMetricRow.model_validate(base | {"repeats": 3})

    with pytest.raises(ValidationError):
        ExperimentMetricRow.model_validate(base | {"captured_mean": 1})


def test_replay_contract_forbids_llm_calls_and_provider_fields():
    base = {
        "id": "replay-1",
        "experiment_clean_run_id": "ecr-1",
        "generated_test_set_artifact_id": "artifact-testset-1",
        "target_snapshot_id": "snap-bug",
        "bug_variant_id": "bug-1",
        "status": "completed",
        "pytest_summary": {
            "collected": 1,
            "passed": 0,
            "failed": 1,
            "skipped": 0,
            "collection_errors": 0,
            "duration_ms": 10,
        },
        "replay_mode": "frozen_test_set",
        "llm_calls": 0,
    }

    assert TestReplayContract.model_validate(base).llm_calls == 0

    with pytest.raises(ValidationError):
        TestReplayContract.model_validate(base | {"llm_calls": 1})

    with pytest.raises(ValidationError):
        TestReplayContract.model_validate(base | {"model_provider": "openai"})


def test_resolved_llm_spec_only_lives_on_clean_run_strategy_snapshot():
    response = ExperimentMetricsResponse.model_validate(_fixture_data())

    experiment_dump = response.experiment.model_dump()
    assert "resolved_llm" not in experiment_dump

    for clean_run in response.clean_runs:
        resolved = clean_run.strategy_snapshot.resolved_llm
        assert resolved.provider == "mock"
        assert resolved.model == "scripted-v2"
        assert resolved.repeat_index == clean_run.repeat_index
        assert resolved.secret_included is False

    for row in response.rows:
        assert row.llm_display.source == "derived_from_clean_run_strategy_snapshots"


def test_llm_override_rejects_secret_shaped_parameters():
    with pytest.raises(ValidationError):
        LlmOverride.model_validate(
            {
                "provider": "openai",
                "model": "gpt-5",
                "temperature_policy": {"mode": "fixed", "value": 0.2},
                "model_params": {"api_key": "should-not-persist"},
            }
        )


def test_model_params_reject_shadow_provider_model_temperature_fields():
    with pytest.raises(ValidationError):
        LlmOverride.model_validate(
            {
                "provider": "openai",
                "model": "gpt-5",
                "temperature_policy": {"mode": "fixed", "value": 0.2},
                "model_params": {"temperature": 0.9},
            }
        )

    with pytest.raises(ValidationError):
        ResolvedLlmSpec.model_validate(
            {
                "provider": "openai",
                "model": "gpt-5",
                "temperature": 0.2,
                "repeat_index": 0,
                "model_params": {"max_output_tokens": 128},
            }
        )


def test_failure_classification_uses_tool_failure_type_vocab():
    assert FailureClassificationEvidence(
        nodeid="tests/test_x.py::test_fixture",
        classification="fixture",
    ).classification == "fixture"
    assert FailureClassificationEvidence(
        nodeid="tests/test_x.py::test_error",
        classification="error",
    ).classification == "error"

    with pytest.raises(ValidationError):
        FailureClassificationEvidence(nodeid="tests/test_x.py::test_system", classification="system")


def test_context_policy_keeps_agent_inside_project_and_generated_test_boundaries():
    response = ExperimentMetricsResponse.model_validate(_fixture_data())
    policy = response.source_context_policy

    assert policy.project_root_boundary == "project_snapshot_root"
    assert policy.generated_tests_dir == "tests/generated"
    assert policy.agent_source_write_permission == "generated_tests_only"
    assert policy.missing_context_marker == "context_incomplete"
    assert "../**" in policy.deny_globs
    assert policy.max_total_bytes >= policy.max_file_bytes

    for clean_run in response.clean_runs:
        context = clean_run.report_quality.context_completeness
        assert context.context_incomplete is False
        assert context.snippets
        assert all(not snippet.path.startswith("../") for snippet in context.snippets)


def test_context_policy_rejects_escape_paths_and_missing_parent_deny_rule():
    base = {
        "project_root_boundary": "project_snapshot_root",
        "read_allowlist_globs": ["shop/**/*.py"],
        "deny_globs": ["../**"],
        "generated_tests_dir": "tests/generated",
        "max_file_bytes": 16000,
        "max_total_bytes": 48000,
        "max_snippets": 12,
        "trace_payload_required": True,
        "missing_context_marker": "context_incomplete",
        "agent_source_write_permission": "generated_tests_only",
    }

    assert SourceContextPolicy.model_validate(base).generated_tests_dir == "tests/generated"

    with pytest.raises(ValidationError):
        SourceContextPolicy.model_validate(base | {"read_allowlist_globs": ["../**"]})

    with pytest.raises(ValidationError):
        SourceContextPolicy.model_validate(base | {"generated_tests_dir": "D:/tmp/generated"})

    with pytest.raises(ValidationError):
        SourceContextPolicy.model_validate(base | {"deny_globs": []})


def test_replay_metrics_require_capturing_nodeids_to_be_clean_variant_intersection():
    ok = ReplayMetricsContract(
        clean_passed_nodeids=["tests/generated/test_x.py::test_bug"],
        variant_assertion_failure_nodeids=["tests/generated/test_x.py::test_bug"],
        capturing_nodeids=["tests/generated/test_x.py::test_bug"],
    )
    assert ok.capturing_nodeids

    with pytest.raises(ValidationError):
        ReplayMetricsContract(
            clean_passed_nodeids=[],
            variant_assertion_failure_nodeids=["tests/generated/test_x.py::test_bug"],
            capturing_nodeids=["tests/generated/test_x.py::test_bug"],
        )

    with pytest.raises(ValidationError):
        ReplayMetricsContract(
            clean_passed_nodeids=["tests/generated/test_x.py::test_bug"],
            variant_assertion_failure_nodeids=[],
            capturing_nodeids=["tests/generated/test_x.py::test_bug"],
        )


def test_db_schema_draft_covers_phase0_tables():
    table_names = {table.name for table in V2_PHASE0_DB_SCHEMA_DRAFT}

    assert {
        "runtime_profiles",
        "strategies",
        "prompt_versions",
        "tool_schema_versions",
        "eval_datasets",
        "eval_tasks",
        "seeded_bugs",
        "bug_variants",
        "experiments",
        "experiment_strategy_versions",
        "experiment_clean_runs",
        "test_replays",
        "experiment_replay_runs",
    }.issubset(table_names)
