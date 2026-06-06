# 种子 bug 的 ground truth（V1 走脚本，不落库）。
# canonical 表示 = patch（file/old/new 字符串替换），由 clean 快照 + patch 现做变体，避免 patch/snapshot 漂移。
# 每个 bug 带一个行为探针（probe + clean_value/buggy_value），数据集自测据此证明「bug 真改变了行为」。
#
# 设计红线：捕获率只认 assertion failure，所以所有 bug 都设计成「返回错值」而非「该抛异常却没抛」。
# 覆盖四类：翻比较符 / 改边界 / 漏校验 / 错状态码。
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

BUG_TYPES = ("comparison_flip", "boundary", "missing_validation", "wrong_status_code")


@dataclass(frozen=True)
class SeededBug:
    id: str
    bug_type: str
    target: str          # 受影响的函数/路由名：in-scope 判定 + 失败相关性
    kind: str            # "function" | "route"
    file: str            # 相对 clean 根
    old: str             # 待替换的唯一片段
    new: str             # 替换后的片段
    description: str
    expected_detection: str  # 什么样的断言能抓到
    probe: str           # function: 调用表达式；route: 请求路径
    clean_value: Any     # probe 在干净代码上的期望结果（function 值 / route 状态码）
    buggy_value: Any     # probe 在变体上的期望结果


BUGS: list[SeededBug] = [
    SeededBug(
        id="cmp-flip-discount",
        bug_type="comparison_flip",
        target="apply_discount",
        kind="function",
        file="shop/pricing.py",
        old="if is_member and total >= 100:",
        new="if is_member and total > 100:",
        description="会员满 100 打折的阈值比较符 >= 被翻成 >，恰好 100 元不再打折",
        expected_detection="断言 apply_discount(100, True) == 90.0",
        probe="apply_discount(100, True)",
        clean_value=90.0,
        buggy_value=100.0,
    ),
    SeededBug(
        id="cmp-flip-freeship",
        bug_type="comparison_flip",
        target="is_free_shipping",
        kind="function",
        file="shop/pricing.py",
        old="return total >= 200",
        new="return total < 200",
        description="包邮判断 >= 被翻成 <，逻辑彻底反向",
        expected_detection="断言 is_free_shipping(250) is True",
        probe="is_free_shipping(250)",
        clean_value=True,
        buggy_value=False,
    ),
    SeededBug(
        id="boundary-shipping",
        bug_type="boundary",
        target="shipping_fee",
        kind="function",
        file="shop/pricing.py",
        old="if weight_kg <= 5:",
        new="if weight_kg < 5:",
        description="运费分档边界 <= 5 改成 < 5，恰好 5kg 多收 10 元",
        expected_detection="断言 shipping_fee(5) == 10",
        probe="shipping_fee(5)",
        clean_value=10,
        buggy_value=20,
    ),
    SeededBug(
        id="boundary-loyalty",
        bug_type="boundary",
        target="loyalty_points",
        kind="function",
        file="shop/pricing.py",
        old="if years >= 3:",
        new="if years >= 4:",
        description="积分门槛 >= 3 改成 >= 4，满 3 年的用户少拿 90 分",
        expected_detection="断言 loyalty_points(3) == 100",
        probe="loyalty_points(3)",
        clean_value=100,
        buggy_value=10,
    ),
    SeededBug(
        id="missing-clamp",
        bug_type="missing_validation",
        target="clamp_discount_rate",
        kind="function",
        file="shop/pricing.py",
        old="    if rate > 1:\n        return 1.0\n",
        new="",
        description="漏掉折扣率上界夹紧，rate>1 时直接返回原值",
        expected_detection="断言 clamp_discount_rate(1.5) == 1.0",
        probe="clamp_discount_rate(1.5)",
        clean_value=1.0,
        buggy_value=1.5,
    ),
    SeededBug(
        id="wrong-status",
        bug_type="wrong_status_code",
        target="get_price",
        kind="route",
        file="shop/api.py",
        old="status_code=404",
        new="status_code=200",
        description="商品不存在时错用 200，破坏 404 契约",
        expected_detection="断言 GET /price/unknown 的状态码 == 404",
        probe="/price/unknown",
        clean_value=404,
        buggy_value=200,
    ),
]


def ground_truth() -> list[dict]:
    """JSON-able ground truth，供 harness 写 ground_truth.json / 报告引用。"""
    return [asdict(b) for b in BUGS]
