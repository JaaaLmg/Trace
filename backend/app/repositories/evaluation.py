from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evaluation import BugVariant, EvalDataset, EvalTask, SeededBug


def get_dataset(session: Session, dataset_id: str) -> EvalDataset | None:
    return session.get(EvalDataset, dataset_id)


def get_dataset_by_name_version(session: Session, *, name: str, version: str) -> EvalDataset | None:
    stmt = select(EvalDataset).where(EvalDataset.name == name, EvalDataset.version == version)
    return session.scalar(stmt)


def list_datasets(session: Session) -> list[EvalDataset]:
    stmt = select(EvalDataset).order_by(EvalDataset.created_at.desc(), EvalDataset.name.asc())
    return list(session.scalars(stmt))


def add_dataset(session: Session, dataset: EvalDataset) -> EvalDataset:
    session.add(dataset)
    session.commit()
    session.refresh(dataset)
    return dataset


def get_eval_task(session: Session, task_id: str) -> EvalTask | None:
    return session.get(EvalTask, task_id)


def list_tasks_for_dataset(session: Session, dataset_id: str) -> list[EvalTask]:
    stmt = select(EvalTask).where(EvalTask.dataset_id == dataset_id).order_by(EvalTask.created_at.asc(), EvalTask.id.asc())
    return list(session.scalars(stmt))


def add_eval_task(session: Session, task: EvalTask) -> EvalTask:
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def get_seeded_bug(session: Session, bug_id: str) -> SeededBug | None:
    return session.get(SeededBug, bug_id)


def list_seeded_bugs_for_task(session: Session, task_id: str) -> list[SeededBug]:
    stmt = (
        select(SeededBug)
        .where(SeededBug.eval_task_id == task_id)
        .order_by(SeededBug.created_at.asc(), SeededBug.id.asc())
    )
    return list(session.scalars(stmt))


def list_seeded_bugs_for_tasks(session: Session, task_ids: list[str]) -> list[SeededBug]:
    if not task_ids:
        return []
    stmt = select(SeededBug).where(SeededBug.eval_task_id.in_(task_ids)).order_by(SeededBug.created_at.asc(), SeededBug.id.asc())
    return list(session.scalars(stmt))


def add_seeded_bug(session: Session, bug: SeededBug) -> SeededBug:
    session.add(bug)
    session.commit()
    session.refresh(bug)
    return bug


def get_bug_variant(session: Session, variant_id: str) -> BugVariant | None:
    return session.get(BugVariant, variant_id)


def list_variants_for_bug(session: Session, seeded_bug_id: str) -> list[BugVariant]:
    stmt = (
        select(BugVariant)
        .where(BugVariant.seeded_bug_id == seeded_bug_id)
        .order_by(BugVariant.created_at.asc(), BugVariant.id.asc())
    )
    return list(session.scalars(stmt))


def list_variants_for_bugs(session: Session, seeded_bug_ids: list[str]) -> list[BugVariant]:
    if not seeded_bug_ids:
        return []
    stmt = (
        select(BugVariant)
        .where(BugVariant.seeded_bug_id.in_(seeded_bug_ids))
        .order_by(BugVariant.created_at.asc(), BugVariant.id.asc())
    )
    return list(session.scalars(stmt))


def add_bug_variant(session: Session, variant: BugVariant) -> BugVariant:
    session.add(variant)
    session.commit()
    session.refresh(variant)
    return variant
