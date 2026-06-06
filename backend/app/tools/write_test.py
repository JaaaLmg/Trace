from __future__ import annotations

import hashlib

from app.core.ids import new_id
from app.schemas.tools import WriteTestFileInput, WriteTestFileOutput
from app.tools.base import ToolContext


def write_test_file(ctx: ToolContext, inp: WriteTestFileInput) -> WriteTestFileOutput:
    # resolve_write 做 canonical 白名单校验：越界或想写业务源码会抛 TOOL_ARGUMENT_ERROR
    target = ctx.resolve_write(inp.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = inp.content.encode("utf-8")
    target.write_bytes(data)
    return WriteTestFileOutput(
        file_id=new_id(),
        path=ctx.relpath(target),
        content_hash=hashlib.sha256(data).hexdigest(),
        bytes=len(data),
    )
