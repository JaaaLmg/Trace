# TRACE 策略评测对比（真实模型 deepseek-v4-flash）

> provider=openai_chat_compat　model=deepseek-v4-flash　temperature=None　reasoning_effort=None　repeats=1　生成于 2026-06-17 16:11:11
> experiment_id=exp-7b93cad4-2d84-4b5c-a035-d46800a39758
> 数据来自 `eval/harness/run_eval.py --real`：3 策略 × 1 重复，干净代码生成 → 6 个 bug 变体重放。
> 与 MockLLM 的 comparison.md 并存：本表是真实测量，捕获/假阳性/反思/token 皆来自真模型，逐次可能不同。

## 策略对比

| 策略 | 状态 | 捕获率(均值±std) | 假阳性率 | 反思 | 平均 token | 平均工具调用 | cost/captured |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Direct v1 | 可评价 | 1.00 ± 0.00（6.0/6） | 0.00 | 否 | 4140 | 3.0 | 690.0 |
| Plan-and-Execute v1 | 不可评价 | 0.00 ± 0.00（0.0/6） | 0.00 | 否 | 0 | 0.0 | no_bug_captured |
| ReAct+Reflection v1 | 可评价 | 1.00 ± 0.00（6.0/6） | 0.00 | 否 | 4991 | 3.0 | 831.8 |

## 逐 bug 捕获矩阵

| bug | 类型 | Direct v1 | Plan-and-Execute v1 | ReAct+Reflection v1 |
| --- | --- | --- | --- | --- |
| variant-cmp-flip-discount | variant-cmp-flip-discount | ✓ | ✗ | ✓ |
| variant-boundary-loyalty | variant-boundary-loyalty | ✓ | ✗ | ✓ |
| variant-boundary-shipping | variant-boundary-shipping | ✓ | ✗ | ✓ |
| variant-cmp-flip-freeship | variant-cmp-flip-freeship | ✓ | ✗ | ✓ |
| variant-missing-clamp | variant-missing-clamp | ✓ | ✗ | ✓ |
| variant-wrong-status | variant-wrong-status | ✓ | ✗ | ✓ |
