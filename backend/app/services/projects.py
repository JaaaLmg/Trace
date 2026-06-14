from __future__ import annotations

from pathlib import Path

from app.core.ids import new_id
from app.models.project import Project, ProjectSnapshot
from app.repositories.projects import add_project, add_snapshot, get_project, list_projects as repo_list_projects, list_snapshots
from app.services.path_policy import is_trace_internal_tmp_path, is_valid_project_root, validate_project_root, validate_snapshot_root
from sqlalchemy.orm import Session


def _is_visible_project(project: Project) -> bool:
    try:
        if is_trace_internal_tmp_path(project.local_path):
            return False
    except ValueError:
        return False
    return is_valid_project_root(project.local_path)


def create_project(session: Session, *, name: str, local_path: str, description: str | None = None) -> Project:
    # 把用户输入的本地目录注册成一个被测项目。
    # 这里暂不做复杂探测，只保存最小元数据，后续 run 再围绕它执行。
    root = validate_project_root(local_path)
    project = Project(
        id=new_id(),
        name=name,
        description=description,
        source_type="local_path",
        local_path=str(root),
    )
    return add_project(session, project)


def get_project_or_404(session: Session, project_id: str) -> Project:
    # service 层统一把“查不到”转成 ValueError，交给 API 层映射成 404。
    project = get_project(session, project_id)
    if project is None:
        raise ValueError("project not found")
    return project


def list_projects(session: Session) -> list[Project]:
    return [project for project in repo_list_projects(session) if _is_visible_project(project)]


def create_snapshot(session: Session, *, project_id: str, root_path: str | None = None) -> ProjectSnapshot:
    # 生成一次项目快照。V1 没有真正复制代码，
    # 只是把本次运行要绑定的 root_path 固化下来。
    project = get_project_or_404(session, project_id)
    root = validate_snapshot_root(root_path or project.local_path, project_root=project.local_path)
    snapshot = ProjectSnapshot(
        id=new_id(),
        project_id=project.id,
        source_kind="local_path",
        root_path=str(root),
    )
    return add_snapshot(session, snapshot)


__all__ = ["create_project", "create_snapshot", "get_project_or_404", "list_projects", "list_snapshots"]
