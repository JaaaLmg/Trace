from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
TRACE_ROOT = BACKEND_ROOT.parent
for path in (BACKEND_ROOT, TRACE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.services.evaluation_seed import seed_demo_dataset


def main() -> None:
    with Session(get_engine()) as session:
        result = seed_demo_dataset(session)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
