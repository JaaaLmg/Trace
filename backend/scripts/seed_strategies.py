from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.services.strategies import seed_strategy_versions


def main() -> None:
    with Session(get_engine()) as session:
        seed_strategy_versions(session)
    print("strategy seeds ready")


if __name__ == "__main__":
    main()
