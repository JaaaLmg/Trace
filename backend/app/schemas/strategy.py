# 策略身份：最简 strategy_versions（V1实施清单 §3）
# 不建 strategies 父表、不建 prompt/tool schema 版本表；prompt_ref/tool_schema_ref 是临时字符串字段
from typing import Literal

from pydantic import BaseModel, Field

WorkflowType = Literal["direct", "plan_execute", "react_reflection"]


class StrategyVersionSpec(BaseModel):
    id: str
    name: str
    workflow_type: WorkflowType
    model_provider: str = "mock"
    model_name: str = "mock-1"
    model_params: dict = Field(default_factory=dict)
    allow_reflection: bool = False
    max_tool_calls: int = 12
    # 临时字段：记录 prompt / 工具 schema 在仓库里的版本号（如 react_v1）
    # V2 引入版本表后迁移成 prompt_version_id / tool_schema_version_id
    prompt_ref: str = "v1"
    tool_schema_ref: str = "v1"
