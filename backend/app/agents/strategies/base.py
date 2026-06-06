from __future__ import annotations

from app.agents.runtime import AgentContext, PlanInput


class Strategy:
    """策略基类。run() 跑完一次生成闭环，返回是否判定疑似业务缺陷（写报告用）。"""

    workflow_type: str = ""

    def run(self, ctx: AgentContext, plan_input: PlanInput) -> bool:
        raise NotImplementedError
