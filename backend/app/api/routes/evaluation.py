from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.api_evaluation import (
    BugVariantCreate,
    BugVariantOut,
    EvalDatasetCreate,
    EvalDatasetDetailOut,
    EvalDatasetOut,
    EvalTaskCreate,
    EvalTaskOut,
    MutationCandidateConfirmRequest,
    MutationDiscoveryDryRunRequest,
    SeededBugCreate,
    SeededBugDetailOut,
    SeededBugOut,
)
from app.schemas.evaluation import MutationDiscoveryResultContract
from app.services.evaluation import (
    EvaluationError,
    create_bug_variant,
    create_eval_dataset,
    create_eval_task,
    create_seeded_bug,
    confirm_selected_mutation_candidate,
    dry_run_task_mutation_discovery,
    get_dataset_detail,
    list_bug_variants,
    list_dataset_tasks,
    list_eval_datasets,
    list_task_seeded_bugs,
)

router = APIRouter(tags=["evaluation"])


def _evaluation_http_error(error: EvaluationError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=str(error))


@router.post("/api/v1/eval-datasets", response_model=EvalDatasetOut)
def create_eval_dataset_route(body: EvalDatasetCreate, db: Session = Depends(get_db)):
    try:
        return create_eval_dataset(
            db,
            dataset_id=body.id,
            name=body.name,
            version=body.version,
            description=body.description,
            project_snapshot_ids=body.project_snapshot_ids,
        )
    except EvaluationError as e:
        raise _evaluation_http_error(e) from e


@router.get("/api/v1/eval-datasets", response_model=list[EvalDatasetOut])
def list_eval_datasets_route(db: Session = Depends(get_db)):
    return list_eval_datasets(db)


@router.get("/api/v1/eval-datasets/{dataset_id}", response_model=EvalDatasetDetailOut)
def get_eval_dataset_route(dataset_id: str, db: Session = Depends(get_db)):
    try:
        return get_dataset_detail(db, dataset_id)
    except EvaluationError as e:
        raise _evaluation_http_error(e) from e


@router.post("/api/v1/eval-datasets/{dataset_id}/tasks", response_model=EvalTaskOut)
def create_eval_task_route(dataset_id: str, body: EvalTaskCreate, db: Session = Depends(get_db)):
    try:
        return create_eval_task(
            db,
            dataset_id=dataset_id,
            task_id=body.id,
            project_snapshot_id=body.project_snapshot_id,
            target_scope=body.target_scope,
            goal=body.goal,
            expected_capabilities=body.expected_capabilities,
        )
    except EvaluationError as e:
        raise _evaluation_http_error(e) from e


@router.get("/api/v1/eval-datasets/{dataset_id}/tasks", response_model=list[EvalTaskOut])
def list_eval_tasks_route(dataset_id: str, db: Session = Depends(get_db)):
    try:
        return list_dataset_tasks(db, dataset_id)
    except EvaluationError as e:
        raise _evaluation_http_error(e) from e


@router.post("/api/v1/eval-tasks/{task_id}/seeded-bugs", response_model=SeededBugOut)
def create_seeded_bug_route(task_id: str, body: SeededBugCreate, db: Session = Depends(get_db)):
    try:
        return create_seeded_bug(
            db,
            eval_task_id=task_id,
            bug_id=body.id,
            bug_type=body.bug_type,
            description=body.description,
            expected_detection=body.expected_detection,
        )
    except EvaluationError as e:
        raise _evaluation_http_error(e) from e


@router.get("/api/v1/eval-tasks/{task_id}/seeded-bugs", response_model=list[SeededBugOut])
def list_seeded_bugs_route(task_id: str, db: Session = Depends(get_db)):
    try:
        return list_task_seeded_bugs(db, task_id)
    except EvaluationError as e:
        raise _evaluation_http_error(e) from e


@router.post("/api/v1/eval-tasks/{task_id}/mutation-discovery/dry-run", response_model=MutationDiscoveryResultContract)
def dry_run_task_mutation_discovery_route(
    task_id: str,
    body: MutationDiscoveryDryRunRequest | None = None,
    db: Session = Depends(get_db),
):
    body = body or MutationDiscoveryDryRunRequest()
    try:
        return dry_run_task_mutation_discovery(
            db,
            task_id,
            sample_seed=body.sample_seed,
            max_selected=body.max_selected,
            target_scope_override=body.target_scope_override,
        )
    except EvaluationError as e:
        raise _evaluation_http_error(e) from e


@router.post("/api/v1/eval-tasks/{task_id}/mutation-discovery/confirm-selected", response_model=SeededBugDetailOut)
def confirm_selected_mutation_candidate_route(
    task_id: str,
    body: MutationCandidateConfirmRequest,
    db: Session = Depends(get_db),
):
    try:
        return confirm_selected_mutation_candidate(
            db,
            task_id,
            audit_report=body.audit_report,
            candidate_id=body.candidate_id,
            probe=body.probe.model_dump(mode="json"),
            seeded_bug_id=body.seeded_bug_id,
            variant_id=body.variant_id,
            bug_type=body.bug_type,
            description=body.description,
            expected_detection=body.expected_detection,
            variant_name=body.variant_name,
        )
    except EvaluationError as e:
        raise _evaluation_http_error(e) from e


@router.post("/api/v1/seeded-bugs/{seeded_bug_id}/variants", response_model=BugVariantOut)
def create_bug_variant_route(seeded_bug_id: str, body: BugVariantCreate, db: Session = Depends(get_db)):
    try:
        return create_bug_variant(
            db,
            seeded_bug_id=seeded_bug_id,
            variant_id=body.id,
            variant_name=body.variant_name,
            canonical_kind=body.canonical_kind,
            patch=body.patch.model_dump(),
            mutated_snapshot_id=body.mutated_snapshot_id,
            ground_truth=body.ground_truth,
        )
    except EvaluationError as e:
        raise _evaluation_http_error(e) from e


@router.get("/api/v1/seeded-bugs/{seeded_bug_id}/variants", response_model=list[BugVariantOut])
def list_bug_variants_route(seeded_bug_id: str, db: Session = Depends(get_db)):
    try:
        return list_bug_variants(db, seeded_bug_id)
    except EvaluationError as e:
        raise _evaluation_http_error(e) from e
