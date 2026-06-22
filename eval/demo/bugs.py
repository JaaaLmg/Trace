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
SHOP_TASK_ID = "task-demo-shop-pricing-v2"
INVENTORY_TASK_ID = "task-demo-inventory-stock-v1"
ACCOUNTS_TASK_ID = "task-demo-accounts-policy-v1"


@dataclass(frozen=True)
class DemoTask:
    id: str
    name: str
    targets: list[str]
    goal: str
    expected_capabilities: list[str]


TASKS: dict[str, DemoTask] = {
    SHOP_TASK_ID: DemoTask(
        id=SHOP_TASK_ID,
        name="Shop pricing and API contracts",
        targets=["apply_discount", "is_free_shipping", "shipping_fee", "loyalty_points", "clamp_discount_rate", "get_price"],
        goal="Generate tests that characterize demo shop pricing and price API behavior.",
        expected_capabilities=["boundary_value", "comparison_logic", "input_validation", "http_status_contract"],
    ),
    INVENTORY_TASK_ID: DemoTask(
        id=INVENTORY_TASK_ID,
        name="Inventory stock and SKU contracts",
        targets=["has_stock", "reorder_quantity", "clamp_quantity", "pack_count", "get_sku"],
        goal="Generate tests that characterize inventory stock calculations and SKU API behavior.",
        expected_capabilities=["boundary_value", "comparison_logic", "input_validation", "rounding_behavior", "http_status_contract"],
    ),
    ACCOUNTS_TASK_ID: DemoTask(
        id=ACCOUNTS_TASK_ID,
        name="Account policy calculations",
        targets=["can_withdraw", "overdraft_fee", "clamp_interest_rate", "risk_tier"],
        goal="Generate tests that characterize account policy threshold and classification behavior.",
        expected_capabilities=["boundary_value", "comparison_logic", "input_validation", "classification_logic"],
    ),
}


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
    task_id: str = SHOP_TASK_ID


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
    SeededBug(
        id="inventory-cmp-stock-threshold",
        bug_type="comparison_flip",
        target="has_stock",
        kind="function",
        file="inventory/stock.py",
        old="return available >= requested",
        new="return available > requested",
        description="库存恰好等于请求量时应可满足，>= 被翻成 > 后错误拒绝",
        expected_detection="断言 has_stock(5, 5) is True",
        probe="has_stock(5, 5)",
        clean_value=True,
        buggy_value=False,
        task_id=INVENTORY_TASK_ID,
    ),
    SeededBug(
        id="inventory-boundary-reorder",
        bug_type="boundary",
        target="reorder_quantity",
        kind="function",
        file="inventory/stock.py",
        old="if current <= threshold:",
        new="if current < threshold:",
        description="库存等于补货阈值时应补货，<= 被改成 < 后漏补",
        expected_detection="断言 reorder_quantity(10, 10, 25) == 15",
        probe="reorder_quantity(10, 10, 25)",
        clean_value=15,
        buggy_value=0,
        task_id=INVENTORY_TASK_ID,
    ),
    SeededBug(
        id="inventory-missing-clamp",
        bug_type="missing_validation",
        target="clamp_quantity",
        kind="function",
        file="inventory/stock.py",
        old="    if quantity < 0:\n        return 0\n",
        new="",
        description="漏掉库存数量下界夹紧，负数库存直接返回",
        expected_detection="断言 clamp_quantity(-3) == 0",
        probe="clamp_quantity(-3)",
        clean_value=0,
        buggy_value=-3,
        task_id=INVENTORY_TASK_ID,
    ),
    SeededBug(
        id="inventory-boundary-pack-count",
        bug_type="boundary",
        target="pack_count",
        kind="function",
        file="inventory/stock.py",
        old="return math.ceil(items / pack_size)",
        new="return int(items / pack_size)",
        description="包装数量应向上取整，改成向下截断后少算一箱",
        expected_detection="断言 pack_count(11, 5) == 3",
        probe="pack_count(11, 5)",
        clean_value=3,
        buggy_value=2,
        task_id=INVENTORY_TASK_ID,
    ),
    SeededBug(
        id="inventory-wrong-status",
        bug_type="wrong_status_code",
        target="get_sku",
        kind="route",
        file="inventory/api.py",
        old="status_code=404",
        new="status_code=200",
        description="SKU 不存在时错用 200，破坏 404 契约",
        expected_detection="断言 GET /sku/missing 的状态码 == 404",
        probe="/sku/missing",
        clean_value=404,
        buggy_value=200,
        task_id=INVENTORY_TASK_ID,
    ),
    SeededBug(
        id="accounts-cmp-withdraw-threshold",
        bug_type="comparison_flip",
        target="can_withdraw",
        kind="function",
        file="accounts/policy.py",
        old="return balance >= amount",
        new="return balance > amount",
        description="余额恰好等于支取金额时应允许，>= 被翻成 > 后错误拒绝",
        expected_detection="断言 can_withdraw(100, 100) is True",
        probe="can_withdraw(100, 100)",
        clean_value=True,
        buggy_value=False,
        task_id=ACCOUNTS_TASK_ID,
    ),
    SeededBug(
        id="accounts-boundary-overdraft-fee",
        bug_type="boundary",
        target="overdraft_fee",
        kind="function",
        file="accounts/policy.py",
        old="if days_late <= 3:",
        new="if days_late < 3:",
        description="逾期 3 天仍应收 10 元，<= 被改成 < 后跳到 25 元",
        expected_detection="断言 overdraft_fee(3) == 10",
        probe="overdraft_fee(3)",
        clean_value=10,
        buggy_value=25,
        task_id=ACCOUNTS_TASK_ID,
    ),
    SeededBug(
        id="accounts-missing-rate-clamp",
        bug_type="missing_validation",
        target="clamp_interest_rate",
        kind="function",
        file="accounts/policy.py",
        old="    if rate > 0.35:\n        return 0.35\n",
        new="",
        description="漏掉利率上界夹紧，过高利率直接返回",
        expected_detection="断言 clamp_interest_rate(0.5) == 0.35",
        probe="clamp_interest_rate(0.5)",
        clean_value=0.35,
        buggy_value=0.5,
        task_id=ACCOUNTS_TASK_ID,
    ),
    SeededBug(
        id="accounts-boundary-risk-tier",
        bug_type="boundary",
        target="risk_tier",
        kind="function",
        file="accounts/policy.py",
        old='if score >= 700:\n        return "low"',
        new='if score > 700:\n        return "low"',
        description="信用分 700 应归入 low，>= 被改成 > 后降到 medium",
        expected_detection='断言 risk_tier(700) == "low"',
        probe="risk_tier(700)",
        clean_value="low",
        buggy_value="medium",
        task_id=ACCOUNTS_TASK_ID,
    ),
    SeededBug(
        id="accounts-boundary-zero-fee",
        bug_type="boundary",
        target="overdraft_fee",
        kind="function",
        file="accounts/policy.py",
        old="if days_late <= 0:",
        new="if days_late < 0:",
        description="未逾期 0 天应免手续费，<= 被改成 < 后误收 10 元",
        expected_detection="断言 overdraft_fee(0) == 0",
        probe="overdraft_fee(0)",
        clean_value=0,
        buggy_value=10,
        task_id=ACCOUNTS_TASK_ID,
    ),
]


def ground_truth() -> list[dict]:
    """JSON-able ground truth，供 harness 写 ground_truth.json / 报告引用。"""
    return [asdict(b) for b in BUGS]
