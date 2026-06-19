from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

import app.models as models
from app.db.session import get_engine
from app.services.evaluation_seed import DEMO_DATASET_ID, DEMO_SNAPSHOT_ID, seed_demo_dataset
from app.services.replay_orchestration import (
    VariantReplayJobOutput,
    build_variant_replay_jobs,
    persist_variant_replay_results,
)
from app.services.replay_scheduler import ReplaySchedulerConfig, run_replay_jobs
from app.services.strategies import seed_strategy_versions


def test_replay_scheduler_preserves_input_order_under_parallel_completion():
    def worker(item: int) -> int:
        time.sleep(0.01 * (3 - item))
        return item * 10

    results = run_replay_jobs([0, 1, 2], worker, config=ReplaySchedulerConfig(concurrency=3))

    assert [result.index for result in results] == [0, 1, 2]
    assert [result.result for result in results] == [0, 10, 20]
    assert all(result.ok for result in results)


def test_replay_scheduler_captures_failures_without_stopping_batch():
    def worker(item: int) -> int:
        if item == 1:
            raise ValueError("bad replay")
        return item

    results = run_replay_jobs([0, 1, 2], worker, config=ReplaySchedulerConfig(concurrency=2))

    assert [result.ok for result in results] == [True, False, True]
    assert "ValueError" in (results[1].error or "")


def test_variant_replay_jobs_are_built_in_variant_order(clean_db):
    with Session(get_engine()) as session:
        seed_strategy_versions(session)
        seed_demo_dataset(session)
        variants = list(
            session.execute(
                select(models.SeededBug, models.BugVariant)
                .join(models.BugVariant, models.BugVariant.seeded_bug_id == models.SeededBug.id)
                .where(models.SeededBug.eval_task_id == "task-demo-shop-pricing-v2")
                .order_by(models.BugVariant.id.asc())
            )
        )

    jobs = build_variant_replay_jobs(
        clean_run_id="clean-1",
        artifact_id="artifact-1",
        target_snapshot_id=DEMO_SNAPSHOT_ID,
        variants=variants,
        clean_passed={"tests/generated/test_demo.py::test_case"},
        timeout_seconds=45,
    )

    assert [job.variant_id for job in jobs] == sorted(job.variant_id for job in jobs)
    assert all(job.clean_run_id == "clean-1" for job in jobs)
    assert all(job.timeout_seconds == 45 for job in jobs)


def test_persist_variant_replay_results_updates_existing_row_idempotently(clean_db):
    seen_cancellation_checks: list[str] = []

    def cancellation_checker(session, experiment_id):
        seen_cancellation_checks.append(experiment_id)

    with Session(get_engine()) as session:
        seed_strategy_versions(session)
        seed_demo_dataset(session)
        snapshot = session.get(models.ProjectSnapshot, DEMO_SNAPSHOT_ID)
        assert snapshot is not None
        session.add(
            models.Experiment(
                id="exp-1",
                name="orchestration",
                dataset_id=DEMO_DATASET_ID,
                repeat_count=1,
                llm_override={"provider": "mock", "model": "mock-1"},
                status="running",
            )
        )
        plan = models.TestPlan(
            id="plan-1",
            project_id=snapshot.project_id,
            name="plan",
            target_scope=[],
            goal="goal",
            budget={},
            output_options={},
            default_strategy_version_id="sv-direct-v1",
        )
        run = models.TestRun(
            id="run-1",
            test_plan_id=plan.id,
            project_snapshot_id=snapshot.id,
            strategy_version_id="sv-direct-v1",
            runtime_snapshot={},
            strategy_snapshot={},
            status="completed",
            pytest_summary={},
        )
        artifact = models.RunArtifact(
            id="artifact-1",
            run_id=run.id,
            artifact_type="generated_test_set",
            uri="memory://artifact-1",
            content_hash="sha256:test",
            size_bytes=1,
            metadata_json={},
        )
        clean = models.ExperimentCleanRun(
            id="clean-1",
            experiment_id="exp-1",
            eval_task_id="task-demo-shop-pricing-v2",
            strategy_version_id="sv-direct-v1",
            repeat_index=0,
            clean_run_id=run.id,
            generated_test_set_artifact_id=artifact.id,
            false_positive=False,
            clean_metrics={},
        )
        session.add_all([plan, run])
        session.commit()
        session.add(artifact)
        session.commit()
        session.add(clean)
        session.commit()
        replays = [
            models.TestReplay(
                id=replay_id,
                experiment_clean_run_id=clean.id,
                generated_test_set_artifact_id=artifact.id,
                target_snapshot_id=snapshot.id,
                bug_variant_id="variant-wrong-status",
                status="completed",
                pytest_summary={},
                runtime_snapshot={},
                executor_metadata={},
                workspace_manifest={},
                cache_status="miss",
                replay_mode="frozen_test_set",
                llm_calls=0,
            )
            for replay_id in ["replay-1", "replay-2"]
        ]
        session.add_all(replays)
        session.commit()
        first = run_replay_jobs(
            [
                VariantReplayJobOutput(
                    replay_id="replay-1",
                    bug_variant_id="variant-wrong-status",
                    captured_bug=False,
                    replay_metrics={"capturing_nodeids": []},
                )
            ],
            lambda item: item,
            config=ReplaySchedulerConfig(concurrency=1),
        )
        persist_variant_replay_results(
            session,
            results=first,
            experiment_id="exp-1",
            clean_run_id="clean-1",
            clean_replay_id="clean-replay-1",
            cancellation_checker=cancellation_checker,
            error_cls=RuntimeError,
        )
        second = run_replay_jobs(
            [
                VariantReplayJobOutput(
                    replay_id="replay-2",
                    bug_variant_id="variant-wrong-status",
                    captured_bug=True,
                    replay_metrics={"capturing_nodeids": ["nodeid-1"]},
                )
            ],
            lambda item: item,
            config=ReplaySchedulerConfig(concurrency=1),
        )
        persist_variant_replay_results(
            session,
            results=second,
            experiment_id="exp-1",
            clean_run_id="clean-1",
            clean_replay_id="clean-replay-2",
            cancellation_checker=cancellation_checker,
            error_cls=RuntimeError,
        )

        rows = list(session.scalars(select(models.ExperimentReplayRun)))

    assert len(rows) == 1
    assert rows[0].replay_id == "replay-2"
    assert rows[0].captured_bug is True
    assert rows[0].replay_metrics["clean_replay_id"] == "clean-replay-2"
    assert seen_cancellation_checks == ["exp-1", "exp-1"]


def test_persist_variant_replay_results_does_not_create_capture_for_failed_job(clean_db):
    seen_cancellation_checks: list[str] = []

    def cancellation_checker(session, experiment_id):
        seen_cancellation_checks.append(experiment_id)

    results = run_replay_jobs([0], lambda _item: (_ for _ in ()).throw(RuntimeError("executor failed")))

    with Session(get_engine()) as session:
        try:
            persist_variant_replay_results(
                session,
                results=results,
                experiment_id="exp-failed-job",
                clean_run_id="clean-failed-job",
                clean_replay_id="clean-replay",
                cancellation_checker=cancellation_checker,
                error_cls=RuntimeError,
            )
        except RuntimeError as exc:
            assert "executor failed" in str(exc)
        else:
            raise AssertionError("failed replay job should raise")

        assert session.scalar(select(models.ExperimentReplayRun)) is None

    assert seen_cancellation_checks == ["exp-failed-job"]
