from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from app.core.errors import ErrorCode, TraceError


@dataclass
class ToolContext:
    """工具运行上下文。

    root           被测项目的工作根目录；读限制在此子树内，pytest 也在这里跑。
    test_write_dir 唯一允许写生成测试的目录（root 的子目录），禁写业务源码。
    executor       run_pytest 用的执行器端口；None 时用本地 subprocess 默认实现。
    """

    root: Path
    test_write_dir: Path
    executor: Any = None

    def __post_init__(self) -> None:
        self.root = Path(self.root).resolve()
        self.test_write_dir = Path(self.test_write_dir).resolve()
        # 不变量：写目录必须是 root 的「严格子目录」——等于 root 都不行。
        # 否则 resolve_write 能写业务源码、run_pytest 空路径会退化成跑整个项目根。
        if self.root not in self.test_write_dir.parents:
            raise TraceError(
                ErrorCode.TOOL_ARGUMENT_ERROR,
                f"test_write_dir {self.test_write_dir} 必须是 root {self.root} 的严格子目录",
            )

    def resolve_read(self, rel: str) -> Path:
        return _safe_resolve(self.root, rel, self.root)

    def resolve_write(self, rel: str) -> Path:
        # 路径按项目根解析，但必须落在 test_write_dir 白名单内
        return _safe_resolve(self.root, rel, self.test_write_dir)

    def relpath(self, p: Path) -> str:
        try:
            return str(Path(p).resolve().relative_to(self.root)).replace("\\", "/")
        except ValueError:
            return str(p).replace("\\", "/")


def _safe_resolve(base_for_join: Path, candidate: str, must_be_within: Path) -> Path:
    p = Path(candidate)
    if not p.is_absolute():
        p = base_for_join / p
    p = p.resolve()
    # canonical path 白名单校验：resolve() 已展开符号链接，越界一律拒绝
    if p != must_be_within and must_be_within not in p.parents:
        raise TraceError(
            ErrorCode.TOOL_ARGUMENT_ERROR,
            f"路径越界：{candidate} 解析到 {p}，不在允许目录 {must_be_within} 内",
        )
    return p


@dataclass
class ToolSpec:
    name: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    fn: Callable[[ToolContext, BaseModel], BaseModel]


class ToolRegistry:
    """工具注册表：统一做入参 Pydantic 校验 + 分发，便于 runtime 包 trace。"""

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._specs[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        if name not in self._specs:
            raise TraceError(ErrorCode.TOOL_ARGUMENT_ERROR, f"未知工具：{name}")
        return self._specs[name]

    def names(self) -> list[str]:
        return list(self._specs)

    def call(self, ctx: ToolContext, name: str, raw_input: dict) -> BaseModel:
        spec = self.get(name)
        try:
            inp = spec.input_model.model_validate(raw_input or {})
        except ValidationError as e:
            raise TraceError(ErrorCode.TOOL_ARGUMENT_ERROR, f"{name} 入参非法：{e}")
        return spec.fn(ctx, inp)
