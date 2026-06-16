from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.models.evaluation import BugVariant, EvalDataset, EvalTask, SeededBug
from app.models.project import ProjectSnapshot
from app.repositories.evaluation import (
    add_bug_variant,
    add_dataset,
    add_eval_task,
    add_seeded_bug,
    get_dataset,
    get_dataset_by_name_version,
    get_bug_variant,
    get_eval_task,
    get_seeded_bug,
    list_datasets as repo_list_datasets,
    list_seeded_bugs_for_task,
    list_seeded_bugs_for_tasks,
    list_tasks_for_dataset,
    list_variants_for_bug,
    list_variants_for_bugs,
)
from app.schemas.api_evaluation import BugVariantOut, EvalDatasetDetailOut, EvalTaskDetailOut, SeededBugDetailOut


class EvaluationError(ValueError):
    status_code = 400


class EvaluationNotFoundError(EvaluationError):
    status_code = 404


class EvaluationConflictError(EvaluationError):
    status_code = 409


def _sha256_json(value: dict) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _snapshot_or_error(session: Session, snapshot_id: str) -> ProjectSnapshot:
    snapshot = session.get(ProjectSnapshot, snapshot_id)
    if snapshot is None:
        raise EvaluationNotFoundError("project snapshot not found")
    return snapshot


def _project_file_path(root: str | Path, file: str) -> Path:
    root = Path(root).resolve()
    target = (root / file).resolve()
    if root not in target.parents and target != root:
        raise EvaluationError("patch file escapes project snapshot root")
    if not target.is_file():
        raise EvaluationError("patch target file not found")
    return target


def count_canonical_hits(root: str | Path, file: str, old: str) -> tuple[str, int]:
    text = _project_file_path(root, file).read_text(encoding="utf-8")
    return text, text.count(old)


def _validate_patch_unique_hit(snapshot: ProjectSnapshot, *, file: str, old: str) -> str:
    text, count = count_canonical_hits(snapshot.root_path, file, old)
    if count != 1:
        raise EvaluationError(f"canonical patch must hit exactly once, got {count}")
    return text


def _canonical_patch_payload(*, file: str, old: str, new: str) -> dict:
    return {"file": file, "old": old, "new": new}


def _patched_text(clean_text: str, *, old: str, new: str) -> str:
    return clean_text.replace(old, new, 1)


def _validate_mutated_snapshot_matches_patch(
    mutated_snapshot: ProjectSnapshot,
    *,
    file: str,
    clean_text: str,
    old: str,
    new: str,
) -> None:
    mutated_text = _project_file_path(mutated_snapshot.root_path, file).read_text(encoding="utf-8")
    expected_text = _patched_text(clean_text, old=old, new=new)
    if mutated_text != expected_text:
        raise EvaluationError("mutated snapshot does not match canonical patch")


def inline_patch_payload(*, file: str, old: str, new: str) -> dict:
    patch = _canonical_patch_payload(file=file, old=old, new=new)
    content_hash = _sha256_json(patch)
    content_id = f"patch-{content_hash[:32]}"
    size_bytes = len(json.dumps(patch, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return {
        "content_id": content_id,
        "artifact_type": "bug_patch",
        "storage": "inline",
        "content_hash": content_hash,
        "size_bytes": size_bytes,
        "metadata": {
            "kind": "bug_patch",
            "created_by": "seed_script",
            "content_role": "inline_canonical_patch",
            "relative_paths": [file],
            "hash_algorithm": "sha256",
        },
        "patch": patch,
    }


def create_eval_dataset(
    session: Session,
    *,
    name: str,
    version: str,
    description: str | None = None,
    project_snapshot_ids: list[str] | None = None,
    dataset_id: str | None = None,
) -> EvalDataset:
    if get_dataset_by_name_version(session, name=name, version=version) is not None:
        raise EvaluationConflictError("dataset name/version already exists")
    if dataset_id is not None and get_dataset(session, dataset_id) is not None:
        raise EvaluationConflictError("dataset id already exists")
    snapshot_ids = project_snapshot_ids or []
    for snapshot_id in snapshot_ids:
        _snapshot_or_error(session, snapshot_id)
    record = EvalDataset(
        id=dataset_id or f"dataset-{new_id()}",
        name=name,
        version=version,
        description=description,
        project_snapshot_ids=snapshot_ids,
    )
    return add_dataset(session, record)


def list_eval_datasets(session: Session) -> list[EvalDataset]:
    return repo_list_datasets(session)


def get_dataset_or_404(session: Session, dataset_id: str) -> EvalDataset:
    dataset = get_dataset(session, dataset_id)
    if dataset is None:
        raise EvaluationNotFoundError("dataset not found")
    return dataset


def create_eval_task(
    session: Session,
    *,
    dataset_id: str,
    project_snapshot_id: str,
    target_scope: dict | None = None,
    goal: str,
    expected_capabilities: list | None = None,
    task_id: str | None = None,
) -> EvalTask:
    dataset = get_dataset_or_404(session, dataset_id)
    snapshot = _snapshot_or_error(session, project_snapshot_id)
    if task_id is not None and get_eval_task(session, task_id) is not None:
        raise EvaluationConflictError("eval task id already exists")
    if dataset.project_snapshot_ids and snapshot.id not in dataset.project_snapshot_ids:
        raise EvaluationError("project snapshot is not part of dataset")
    record = EvalTask(
        id=task_id or f"task-{new_id()}",
        dataset_id=dataset.id,
        project_snapshot_id=snapshot.id,
        target_scope=target_scope or {},
        goal=goal,
        expected_capabilities=expected_capabilities or [],
    )
    return add_eval_task(session, record)


def list_dataset_tasks(session: Session, dataset_id: str) -> list[EvalTask]:
    get_dataset_or_404(session, dataset_id)
    return list_tasks_for_dataset(session, dataset_id)


def get_eval_task_or_404(session: Session, task_id: str) -> EvalTask:
    task = get_eval_task(session, task_id)
    if task is None:
        raise EvaluationNotFoundError("eval task not found")
    return task


def create_seeded_bug(
    session: Session,
    *,
    eval_task_id: str,
    bug_type: str,
    description: str,
    expected_detection: str,
    bug_id: str | None = None,
) -> SeededBug:
    task = get_eval_task_or_404(session, eval_task_id)
    if bug_id is not None and get_seeded_bug(session, bug_id) is not None:
        raise EvaluationConflictError("seeded bug id already exists")
    record = SeededBug(
        id=bug_id or f"bug-{new_id()}",
        eval_task_id=task.id,
        bug_type=bug_type,
        description=description,
        expected_detection=expected_detection,
    )
    return add_seeded_bug(session, record)


def list_task_seeded_bugs(session: Session, task_id: str) -> list[SeededBug]:
    get_eval_task_or_404(session, task_id)
    return list_seeded_bugs_for_task(session, task_id)


def get_seeded_bug_or_404(session: Session, bug_id: str) -> SeededBug:
    bug = get_seeded_bug(session, bug_id)
    if bug is None:
        raise EvaluationNotFoundError("seeded bug not found")
    return bug


def create_bug_variant(
    session: Session,
    *,
    seeded_bug_id: str,
    variant_name: str,
    patch: dict,
    canonical_kind: str = "patch",
    mutated_snapshot_id: str | None = None,
    ground_truth: dict | None = None,
    variant_id: str | None = None,
) -> BugVariant:
    if canonical_kind != "patch":
        raise EvaluationError("V2.1 only supports canonical_kind=patch")
    if variant_id is not None and get_bug_variant(session, variant_id) is not None:
        raise EvaluationConflictError("bug variant id already exists")
    bug = get_seeded_bug_or_404(session, seeded_bug_id)
    task = get_eval_task_or_404(session, bug.eval_task_id)
    clean_snapshot = _snapshot_or_error(session, task.project_snapshot_id)
    mutated_snapshot = None
    if mutated_snapshot_id is not None:
        mutated_snapshot = _snapshot_or_error(session, mutated_snapshot_id)

    file = patch["file"]
    old = patch["old"]
    new = patch["new"]
    clean_text = _validate_patch_unique_hit(clean_snapshot, file=file, old=old)
    if mutated_snapshot is not None:
        _validate_mutated_snapshot_matches_patch(
            mutated_snapshot,
            file=file,
            clean_text=clean_text,
            old=old,
            new=new,
        )

    patch_artifact = inline_patch_payload(file=file, old=old, new=new)
    merged_ground_truth = dict(ground_truth or {})
    merged_ground_truth["patch_artifact"] = patch_artifact
    merged_ground_truth["patch_unique_hit"] = {
        "project_snapshot_id": clean_snapshot.id,
        "file": file,
        "hit_count": 1,
    }
    if mutated_snapshot is not None:
        merged_ground_truth["mutated_snapshot_verification"] = {
            "mutated_snapshot_id": mutated_snapshot.id,
            "matches_canonical_patch": True,
        }

    record = BugVariant(
        id=variant_id or f"variant-{new_id()}",
        seeded_bug_id=bug.id,
        variant_name=variant_name,
        canonical_kind=canonical_kind,
        patch_artifact_id=None,
        mutated_snapshot_id=mutated_snapshot_id,
        ground_truth=merged_ground_truth,
    )
    return add_bug_variant(session, record)


def list_bug_variants(session: Session, seeded_bug_id: str) -> list[BugVariant]:
    get_seeded_bug_or_404(session, seeded_bug_id)
    return list_variants_for_bug(session, seeded_bug_id)


def get_dataset_detail(session: Session, dataset_id: str) -> EvalDatasetDetailOut:
    dataset = get_dataset_or_404(session, dataset_id)
    tasks = list_tasks_for_dataset(session, dataset.id)
    bugs = list_seeded_bugs_for_tasks(session, [task.id for task in tasks])
    variants = list_variants_for_bugs(session, [bug.id for bug in bugs])

    variants_by_bug_id = defaultdict(list)
    for variant in variants:
        variants_by_bug_id[variant.seeded_bug_id].append(BugVariantOut.model_validate(variant))

    bugs_by_task_id = defaultdict(list)
    for bug in bugs:
        bug_out = SeededBugDetailOut.model_validate(bug).model_copy(
            update={"variants": variants_by_bug_id[bug.id]}
        )
        bugs_by_task_id[bug.eval_task_id].append(bug_out)

    task_outs = [
        EvalTaskDetailOut.model_validate(task).model_copy(update={"seeded_bugs": bugs_by_task_id[task.id]})
        for task in tasks
    ]
    return EvalDatasetDetailOut.model_validate(dataset).model_copy(update={"tasks": task_outs})
