from __future__ import annotations

from app.db.base import Base
from app.db.session import get_engine
from app.models import load_all_models


def create_schema() -> None:
    load_all_models()
    Base.metadata.create_all(bind=get_engine())


if __name__ == "__main__":
    create_schema()
