# TRACE 策略评测对比（demo seeded bugs）

> 数据来自 `eval/harness/run_eval.py`：3 策略 × 3 重复，干净代码生成 → 6 个 bug 变体重放。
> demo 用 scripted MockLLM 作者建模三种策略的典型行为；harness 与指标计算与 LLM 无关。

## 策略对比

| 策略 | 捕获率(均值±std) | 假阳性率 | 反思 | 平均 token | 平均工具调用 | cost/captured |
| --- | --- | --- | --- | --- | --- | --- |
| Direct v1 | 0.83 ± 0.00（5.0/6） | 1.00 | 否 | 610 | 3.0 | 122.0 |
| Plan-and-Execute v1 | 1.00 ± 0.00（6.0/6） | 0.00 | 否 | 2293 | 13.0 | 382.2 |
| ReAct+Reflection v1 | 1.00 ± 0.00（6.0/6） | 0.00 | 是 | 1342 | 5.0 | 223.7 |

## 逐 bug 捕获矩阵

| bug | 类型 | Direct v1 | Plan-and-Execute v1 | ReAct+Reflection v1 |
| --- | --- | --- | --- | --- |
| cmp-flip-discount | comparison_flip | ✓ | ✓ | ✓ |
| cmp-flip-freeship | comparison_flip | ✓ | ✓ | ✓ |
| boundary-shipping | boundary | ✓ | ✓ | ✓ |
| boundary-loyalty | boundary | ✓ | ✓ | ✓ |
| missing-clamp | missing_validation | ✓ | ✓ | ✓ |
| wrong-status | wrong_status_code | ✗ | ✓ | ✓ |
