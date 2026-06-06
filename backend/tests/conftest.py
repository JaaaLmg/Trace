# 让 tests 不依赖 editable install 也能 import app；同时让 eval.harness 可被 import
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
_TRACE_ROOT = _BACKEND.parent
for p in (str(_BACKEND), str(_TRACE_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)
