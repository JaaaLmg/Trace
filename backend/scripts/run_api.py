from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
for path in (str(BACKEND_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


def main() -> None:
    host = os.environ.get("TRACE_API_HOST", "127.0.0.1")
    port = int(os.environ.get("TRACE_API_PORT", "8000"))
    uvicorn.run("app.main:create_app", host=host, port=port, reload=False, factory=True)


if __name__ == "__main__":
    main()
