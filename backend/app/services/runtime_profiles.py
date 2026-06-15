from __future__ import annotations

import platform

from app.core.ids import new_id
from app.models.runtime_profile import RuntimeProfile
from app.repositories.runtime_profiles import add_runtime_profile, list_runtime_profiles_for_project
from sqlalchemy.orm import Session


def _default_test_command() -> str:
    return "python -m pytest tests -q --rootdir . -p no:cacheprovider"


def ensure_default_runtime_profile(session: Session, *, project_id: str) -> RuntimeProfile:
    existing = list_runtime_profiles_for_project(session, project_id)
    if existing:
        return existing[0]
    profile = RuntimeProfile(
        id=new_id(),
        project_id=project_id,
        name="Default Local Subprocess",
        python_version=platform.python_version(),
        install_command=None,
        test_command=_default_test_command(),
        env_template={},
        resource_limits={"enforced": False},
        network_policy="default",
    )
    return add_runtime_profile(session, profile)
