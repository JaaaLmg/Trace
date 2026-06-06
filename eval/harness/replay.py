# 变体重放：把干净期定型的测试内容原样写进目标项目（变体或干净），跑 pytest，按 nodeid 返回结果。
# 关键：不重新生成、不调 LLM——测试内容在干净期已定型，重放只换被测代码。这是污染隔离的科学对照。
from __future__ import annotations

from pathlib import Path

from app.schemas.tools import RunPytestInput, RunPytestOutput, WriteTestFileInput
from app.tools.base import ToolContext
from app.tools.run_pytest import run_pytest
from app.tools.write_test import write_test_file


def replay(target_root: Path, files: dict, timeout_seconds: int = 60) -> RunPytestOutput:
    target_root = Path(target_root)
    ctx = ToolContext(root=target_root, test_write_dir=target_root / "tests" / "generated")
    for relpath, content in files.items():
        write_test_file(ctx, WriteTestFileInput(attempt_id="replay", path=relpath, content=content, reason="replay"))
    return run_pytest(ctx, RunPytestInput(attempt_id="replay", test_paths=list(files.keys()), timeout_seconds=timeout_seconds))
