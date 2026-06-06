# Agent 结构化输出契约：LLM 的每一类输出都过 Pydantic 校验 + 重试
# 这些是「模型必须吐成这个形状」的约束，不是 DB 表
from typing import Literal, Optional

from pydantic import BaseModel, Field

TargetType = Literal["route", "function", "module", "file", "goal"]


class PlanItemDraft(BaseModel):
    """Plan-and-Execute 拆出的单个任务，落库成 run_plan_items"""

    index: int
    target_type: TargetType
    target_ref: str
    goal: str
    planned_assertions: list[str] = Field(default_factory=list)


class PlanOutput(BaseModel):
    items: list[PlanItemDraft] = Field(default_factory=list)


class GeneratedCaseDraft(BaseModel):
    """LLM 声明它写了哪些用例；真实用例边界以生成文件的 AST 解析为准"""

    test_name: str
    target_route: Optional[str] = None
    target_function: Optional[str] = None
    assertion_summary: str


class GenerationOutput(BaseModel):
    # 路径由系统强制写到受控目录，模型给不给都忽略，故可选（与 prompt「test_file_path 可省略」一致）
    test_file_path: Optional[str] = None
    test_file_content: str
    cases: list[GeneratedCaseDraft] = Field(default_factory=list)
    coverage_notes: Optional[str] = None
    risks: Optional[str] = None


class ReflectionOutput(BaseModel):
    """Reflection 契约（系统设计.md §7）：只修测试，禁削弱断言。

    若不削弱断言就无法通过，必须停手并把 suspected_code_bug 置 True。
    """

    fixed_content: str
    fix_reason: str
    changed_points: list[str] = Field(default_factory=list)
    lowered_assertion_strength: bool = False
    suspected_code_bug: bool = False
