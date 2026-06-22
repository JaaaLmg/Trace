from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.models.evaluation import BugVariant, EvalDataset, EvalTask, SeededBug
from app.models.project import Project, ProjectSnapshot
from app.services.evaluation import count_canonical_hits, inline_patch_payload

TRACE_ROOT = Path(__file__).resolve().parents[3]
DEMO_CLEAN_ROOT = TRACE_ROOT / "eval" / "demo" / "clean"
DEMO_PROJECT_ID = "project-demo-shop-v2"
DEMO_SNAPSHOT_ID = "snapshot-demo-shop-clean-v2"
DEMO_DATASET_ID = "dataset-demo-v2"
DEMO_TASK_ID = "task-demo-shop-pricing-v2"


def _ensure_demo_project(session: Session) -> Project:
    project = session.get(Project, DEMO_PROJECT_ID)
    if project is not None:
        return project
    record = Project(
        id=DEMO_PROJECT_ID,
        name="TRACE demo shop",
        description="Clean demo project used by the V2 seeded bug evaluation dataset.",
        source_type="local_path",
        local_path=str(DEMO_CLEAN_ROOT),
        language="python",
        framework="fastapi",
        status="active",
    )
    session.add(record)
    session.flush()
    session.refresh(record)
    return record


def _ensure_demo_snapshot(session: Session, project: Project) -> ProjectSnapshot:
    snapshot = session.get(ProjectSnapshot, DEMO_SNAPSHOT_ID)
    if snapshot is not None:
        return snapshot
    record = ProjectSnapshot(
        id=DEMO_SNAPSHOT_ID,
        project_id=project.id,
        source_kind="local_path",
        root_path=str(DEMO_CLEAN_ROOT),
        content_hash=None,
    )
    session.add(record)
    session.flush()
    session.refresh(record)
    return record


def _prevalidate_demo_patches(bugs) -> None:
    for bug in bugs:
        _text, count = count_canonical_hits(DEMO_CLEAN_ROOT, bug.file, bug.old)
        if count != 1:
            raise ValueError(f"demo bug {bug.id} canonical patch must hit exactly once, got {count}")


def seed_demo_dataset(session: Session) -> dict:
    from eval.demo.bugs import BUGS, TASKS

    _prevalidate_demo_patches(BUGS)
    bugs_by_task = {task_id: [bug for bug in BUGS if bug.task_id == task_id] for task_id in TASKS}

    try:
        project = _ensure_demo_project(session)
        snapshot = _ensure_demo_snapshot(session, project)

        dataset = session.get(EvalDataset, DEMO_DATASET_ID)
        if dataset is None:
            dataset = EvalDataset(
                id=DEMO_DATASET_ID,
                name="TRACE demo seeded bugs",
                version="v2",
                description="Demo seeded bug suite for V2 experiment plumbing.",
                project_snapshot_ids=[snapshot.id],
            )
            session.add(dataset)

        tasks: dict[str, EvalTask] = {}
        for task_id, task_spec in TASKS.items():
            task_bugs = bugs_by_task.get(task_id, [])
            task = session.get(EvalTask, task_id)
            target_scope = {
                "targets": list(task_spec.targets),
                "bug_count": len(task_bugs),
                "source": "eval.demo.bugs",
            }
            if task is None:
                task = EvalTask(
                    id=task_id,
                    dataset_id=dataset.id,
                    project_snapshot_id=snapshot.id,
                    target_scope=target_scope,
                    goal=task_spec.goal,
                    expected_capabilities=list(task_spec.expected_capabilities),
                )
                session.add(task)
            else:
                task.dataset_id = dataset.id
                task.project_snapshot_id = snapshot.id
                task.target_scope = target_scope
                task.goal = task_spec.goal
                task.expected_capabilities = list(task_spec.expected_capabilities)
            tasks[task_id] = task
        session.flush()

        created_bugs = 0
        created_variants = 0
        for bug in BUGS:
            task = tasks[bug.task_id]
            seeded_bug = session.get(SeededBug, bug.id)
            if seeded_bug is None:
                seeded_bug = SeededBug(
                    id=bug.id,
                    eval_task_id=bug.task_id,
                    bug_type=bug.bug_type,
                    description=bug.description,
                    expected_detection=bug.expected_detection,
                )
                session.add(seeded_bug)
                created_bugs += 1
            else:
                seeded_bug.eval_task_id = bug.task_id
                seeded_bug.bug_type = bug.bug_type
                seeded_bug.description = bug.description
                seeded_bug.expected_detection = bug.expected_detection

            variant_id = f"variant-{bug.id}"
            if session.get(BugVariant, variant_id) is None:
                patch_artifact = inline_patch_payload(file=bug.file, old=bug.old, new=bug.new)
                ground_truth = {
                    "target": bug.target,
                    "target_kind": bug.kind,
                    "probe": bug.probe,
                    "clean_value": bug.clean_value,
                    "buggy_value": bug.buggy_value,
                    "expected_detection": bug.expected_detection,
                    "patch_artifact": patch_artifact,
                    "patch_unique_hit": {
                        "project_snapshot_id": snapshot.id,
                        "file": bug.file,
                        "hit_count": 1,
                    },
                }
                session.add(
                    BugVariant(
                        id=variant_id,
                        seeded_bug_id=seeded_bug.id,
                        variant_name=f"{bug.id} canonical patch",
                        canonical_kind="patch",
                        patch_artifact_id=None,
                        mutated_snapshot_id=None,
                        ground_truth=ground_truth,
                    )
                )
                created_variants += 1

        session.commit()
    except Exception:
        session.rollback()
        raise

    return {
        "dataset_id": dataset.id,
        "task_id": DEMO_TASK_ID,
        "task_count": len(TASKS),
        "task_ids": list(TASKS),
        "project_id": project.id,
        "snapshot_id": snapshot.id,
        "seeded_bug_count": len(BUGS),
        "created_bugs": created_bugs,
        "created_variants": created_variants,
    }
