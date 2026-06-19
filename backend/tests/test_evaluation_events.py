from __future__ import annotations

from app.models import Experiment, ExperimentCleanRun, ExperimentReplayRun, TestReplay as ReplayModel
from app.services.evaluation_events import build_reflection_event_backfeed, project_evaluation_events


def _experiment(**overrides) -> Experiment:
    values = {
        "id": "exp-events",
        "name": "events",
        "dataset_id": "dataset-1",
        "repeat_count": 1,
        "status": "completed",
    }
    values.update(overrides)
    return Experiment(**values)


def _clean(clean_metrics: dict | None = None, **overrides) -> ExperimentCleanRun:
    values = {
        "id": "clean-1",
        "experiment_id": "exp-events",
        "eval_task_id": "task-1",
        "strategy_version_id": "sv-direct-v1",
        "repeat_index": 0,
        "clean_run_id": "run-clean-1",
        "generated_test_set_artifact_id": "artifact-tests-1",
        "false_positive": False,
        "clean_metrics": clean_metrics or {"validity_status": "evaluable"},
    }
    values.update(overrides)
    return ExperimentCleanRun(**values)


def _replay(**overrides) -> ReplayModel:
    values = {
        "id": "replay-1",
        "experiment_clean_run_id": "clean-1",
        "generated_test_set_artifact_id": "artifact-tests-1",
        "target_snapshot_id": "snapshot-1",
        "bug_variant_id": "variant-1",
        "status": "completed",
        "pytest_summary": {},
        "replay_mode": "frozen_test_set",
        "llm_calls": 0,
    }
    values.update(overrides)
    return ReplayModel(**values)


def _replay_result(**overrides) -> ExperimentReplayRun:
    values = {
        "id": "experiment-replay-1",
        "experiment_clean_run_id": "clean-1",
        "bug_variant_id": "variant-1",
        "replay_id": "replay-1",
        "captured_bug": True,
        "replay_metrics": {
            "capture_rule": "clean_passed_variant_assertion_failure_same_nodeid",
            "clean_passed_nodeids": ["tests/generated/test_x.py::test_bug"],
            "variant_assertion_failure_nodeids": ["tests/generated/test_x.py::test_bug"],
            "capturing_nodeids": ["tests/generated/test_x.py::test_bug"],
            "clean_replay_id": "replay-clean-1",
            "probe_check": {
                "status": "passed",
                "clean_actual": 200,
                "clean_expected": 200,
                "buggy_actual": 500,
                "buggy_expected": 500,
            },
        },
    }
    values.update(overrides)
    return ExperimentReplayRun(**values)


def test_project_evaluation_events_project_invalid_clean_and_flaky_reason():
    clean = _clean(
        {
            "validity_status": "invalid_test_set",
            "invalid_reason": "flaky_clean_replay",
            "flaky_check": {
                "required_runs": 3,
                "actual_runs": 3,
                "baseline_replay_id": "replay-clean-1",
                "replay_ids": ["replay-clean-1", "replay-clean-2"],
                "reasons": ["run 2 mismatch: status changed"],
            },
        }
    )

    events = project_evaluation_events(_experiment(), [clean], [], [])

    assert len(events) == 1
    [event] = events
    assert event["event_type"] == "flaky_clean_replay"
    assert event["severity"] == "blocking"
    assert event["scope"] == "clean_run"
    assert event["stable_code"] == "flaky_clean_replay"
    assert event["source_ids"] == {"test_run_id": "run-clean-1", "baseline_replay_id": "replay-clean-1"}
    assert event["artifact_ids"] == ["artifact-tests-1"]
    assert event["payload"]["replay_ids"] == ["replay-clean-1", "replay-clean-2"]


def test_project_evaluation_events_project_replay_probe_and_capture_with_stable_ids():
    clean = _clean()
    replay_result = _replay_result()

    first = project_evaluation_events(_experiment(), [clean], [_replay()], [replay_result])
    second = project_evaluation_events(_experiment(), [clean], [_replay()], [replay_result])

    assert [event["event_id"] for event in first] == [event["event_id"] for event in second]
    assert [event["event_type"] for event in first] == ["probe_check_passed", "replay_captured"]
    capture = first[1]
    assert capture["nodeids"] == ["tests/generated/test_x.py::test_bug"]
    assert capture["payload"]["capturing_count"] == 1
    assert capture["source_ids"] == {
        "experiment_replay_run_id": "experiment-replay-1",
        "clean_replay_id": "replay-clean-1",
    }


def test_project_evaluation_events_project_failures_without_metrics_blob_leakage():
    clean = _clean()
    replay = _replay(status="failed", error_code="ExperimentError", error_message="bug variant probe check failed")
    provider_events = project_evaluation_events(
        _experiment(status="failed", error_code="ExperimentError", error_message="clean run failed before replay: LLM_PROVIDER_ERROR"),
        [],
        [],
        [],
    )
    artifact_events = project_evaluation_events(
        _experiment(status="failed", error_code="ExperimentError", error_message="generated test set artifact hash mismatch"),
        [],
        [],
        [],
    )
    replay_events = project_evaluation_events(_experiment(), [clean], [replay], [])

    assert [event["event_type"] for event in provider_events] == ["provider_failure"]
    assert [event["event_type"] for event in artifact_events] == ["artifact_hash_mismatch"]
    assert [event["event_type"] for event in replay_events] == ["replay_failure", "probe_check_failed"]
    for event in [*provider_events, *artifact_events, *replay_events]:
        assert "clean_metrics" not in event["payload"]
        assert "replay_metrics" not in event["payload"]
        assert event["created_from"] == "experiment_service_projection"


def test_reflection_event_backfeed_filters_prompt_safe_events_with_reasons():
    flaky_clean = _clean(
        {
            "validity_status": "invalid_test_set",
            "invalid_reason": "flaky_clean_replay",
            "flaky_check": {
                "required_runs": 3,
                "actual_runs": 3,
                "baseline_replay_id": "replay-clean-1",
                "replay_ids": ["replay-clean-1", "replay-clean-2"],
                "reasons": ["run 2 mismatch: status changed"],
            },
        }
    )
    replay = _replay(status="failed", error_code="ExperimentError", error_message="bug variant probe check failed")
    events = [
        *project_evaluation_events(_experiment(), [flaky_clean], [replay], []),
        *project_evaluation_events(
            _experiment(
                status="failed",
                error_code="ExperimentError",
                error_message="clean run failed before replay: LLM_PROVIDER_ERROR",
            ),
            [],
            [],
            [],
        ),
        *project_evaluation_events(
            _experiment(
                status="failed",
                error_code="ExperimentError",
                error_message="generated test set artifact hash mismatch",
            ),
            [],
            [],
            [],
        ),
        *project_evaluation_events(_experiment(), [_clean()], [_replay()], [_replay_result()]),
    ]

    backfeed = build_reflection_event_backfeed(
        events,
        eval_task_id="task-1",
        strategy_version_id="sv-direct-v1",
        before_repeat_index=1,
    )

    assert [event.event_type for event in backfeed.events] == [
        "flaky_clean_replay",
        "replay_failure",
        "probe_check_failed",
    ]
    assert backfeed.events[0].severity == "blocking"
    filtered = [decision for decision in backfeed.decisions if decision["action"] == "filtered"]
    assert filtered
    assert all(decision["reason"] for decision in filtered)
    filtered_types = {decision["event_type"] for decision in filtered}
    assert {"provider_failure", "artifact_hash_mismatch", "probe_check_passed", "replay_captured"} <= filtered_types


def test_reflection_event_backfeed_keeps_task_and_strategy_boundary():
    current = project_evaluation_events(
        _experiment(),
        [
            _clean(
                {
                    "validity_status": "invalid_test_set",
                    "invalid_reason": "flaky_clean_replay",
                    "flaky_check": {"reasons": ["current repeat should not leak"]},
                },
                repeat_index=1,
            )
        ],
        [],
        [],
    )
    other_strategy = project_evaluation_events(
        _experiment(),
        [
            _clean(
                {
                    "validity_status": "invalid_test_set",
                    "invalid_reason": "flaky_clean_replay",
                    "flaky_check": {"reasons": ["other strategy"]},
                },
                strategy_version_id="sv-plan-v1",
            )
        ],
        [],
        [],
    )

    backfeed = build_reflection_event_backfeed(
        [*current, *other_strategy],
        eval_task_id="task-1",
        strategy_version_id="sv-direct-v1",
        before_repeat_index=1,
    )

    assert backfeed.events == []
    assert {decision["reason"] for decision in backfeed.decisions} == {
        "event belongs to current or future repeat",
        "event belongs to another strategy_version_id",
    }
