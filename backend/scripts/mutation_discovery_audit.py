from __future__ import annotations

import argparse
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
from app.services.evaluation import build_task_mutation_discovery_audit_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Export auto mutation discovery dry-run audit report")
    parser.add_argument("task_id", help="Evaluation task id")
    parser.add_argument("--sample-seed", type=int, default=0)
    parser.add_argument("--max-selected", type=int, default=20)
    parser.add_argument("--target", action="append", default=None, help="Override target scope; may be repeated")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON output path")
    args = parser.parse_args()

    target_scope = {"targets": args.target} if args.target else None
    with Session(get_engine()) as session:
        report = build_task_mutation_discovery_audit_report(
            session,
            args.task_id,
            sample_seed=args.sample_seed,
            max_selected=args.max_selected,
            target_scope_override=target_scope,
        )

    payload = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, indent=2)
    if args.output is None:
        print(payload)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
