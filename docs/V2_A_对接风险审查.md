# TRACE V2.2 A 线对接风险审查

审查日期：2026-06-20

审查范围：只验证 A 线合并后的对接风险，不开启 B 线新功能，不修改业务代码、配置文件或密钥文件。

参考文档：

- `docs/V2_A_对接文档.md`
- `docs/V2.2-A线执行平台说明.md`
- `docs/V2实施清单.md`
- `docs/评测与项目理解.md`

## 总结

本次审查发现 3 个需要反馈给 A 线负责人的问题，另有 1 个展示口径建议：

1. `env_template` 当前会持久化 value，并注入 Docker，和“只存 key/模板，不存 secret value”的文档口径不一致。
2. Dataset scoped runtime profile API 当前按首个 task 推导 project，系统又没有强制 dataset 单项目，存在多项目 dataset 误选 runtime profile 的风险。
3. A 对接文档仍包含旧本地绝对路径 `D:\17524\MyCode\Trace`，需要做路径卫生。
4. `false_positive_rate > 0` 且 `metric_status=ok` 是当前合同允许的，但前端展示容易误导，建议 A 线先补 warning，不改底层捕获定义。

## 1. `env_template` 可能误存 secret value

级别：P1

结论：风险成立。

文档声称 `env_template` “只存 key/模板，不存 secret value”，但当前实现并没有阻止 value 被持久化、冻结进 runtime snapshot、再注入 Docker。

证据：

- `backend/app/schemas/api_runtime_profile.py`
  - `RuntimeProfileCreate.env_template` 和 `RuntimeProfileUpdate.env_template` 都是普通 `dict`，schema 层不限制 value 形态。
- `backend/app/services/runtime_profiles.py`
  - `_SECRET_ENV_TOKENS = ("api_key", "apikey", "secret", "token", "password", "authorization")`
  - `_reject_secret_env()` 只检查 key 名，不检查 value。
  - `create_runtime_profile()` 会保存原始 `env_template`。
- `backend/app/services/test_runs.py`
  - `_runtime_snapshot()` 会把完整 `env_template` 写入 runtime snapshot，同时另存 `env_keys`。
- `backend/app/tools/executor.py`
  - `executor_from_runtime_snapshot()` 从 snapshot 读取完整 `env_template`。
  - `DockerPytestExecutor._docker_run_cmd()` 对每个非空 value 生成 `-e key=value`。

实测验证：

```text
SERVICE_URL=sk-live-secret-value
```

这种“key 名不敏感，但 value 疑似 secret”的 payload 会通过当前校验，并生成 Docker 环境变量参数：

```text
['SERVICE_URL=sk-live-secret-value']
```

现有测试覆盖不足：

- `backend/tests/test_stage1_versioning_runtime_profiles.py::test_runtime_profile_rejects_secret_env_key`
  - 已覆盖 `API_TOKEN` 这类 key 名拒绝。
  - 未覆盖安全 key 下的疑似 secret value。
  - 未覆盖 value 不应进入 DB/runtime snapshot/Docker command。

建议最小修复方向：

1. 首选把持久化合同改成 `env_keys` 或引用格式，不保存真实 value。
2. 如果保留 `env_template` dict，则 value 只允许：
   - `null`
   - 空字符串
   - 明确占位符，例如 `${SERVICE_URL}` 或 `<SERVICE_URL>`
3. Docker executor 不应从 `env_template` 直接取真实 value 注入；如果后续需要运行时注入，应从安全运行时 secret provider 或当前进程环境按白名单 key 解析，且不能写回 DB/snapshot/evidence。

建议补测试：

- API 创建/更新 profile 时，`{"SERVICE_URL": "sk-live-secret-value"}`、`{"FOO": "Bearer xxx"}`、`{"BAR": "ghp_xxx"}` 等疑似 secret value 应拒绝。
- `api_key`、`token`、`password`、`authorization` 等 key 继续拒绝。
- 成功 profile 的 DB 记录和 runtime snapshot 不包含真实 secret value。
- Docker command 不出现真实 secret value。

## 2. Dataset runtime profile API 静默取首个 task

级别：P1

结论：风险成立。

`GET/POST /api/v1/eval-datasets/{dataset_id}/runtime-profiles` 当前按 dataset 首个 task 的 project snapshot 推导 project。这个做法只有在 dataset 被严格限制为单项目时才成立，但当前代码没有这个硬约束。

证据：

- `backend/app/api/routes/runtime_profiles.py`
  - `_project_id_for_dataset()` 查询 `EvalTask.project_snapshot_id`，按 `created_at/id` 排序后取第一个。
- `backend/app/models/evaluation.py`
  - `EvalDataset.project_snapshot_ids` 是 list。
  - `EvalTask` 各自持有 `project_snapshot_id`。
- `backend/app/services/evaluation.py`
  - `create_eval_task()` 只检查 task snapshot 是否在 dataset 的 `project_snapshot_ids` 中，没有检查所有 snapshot 是否属于同一 project。
- `backend/app/services/experiments.py`
  - `create_experiment()` 构造 `dataset_project_ids` 集合，并只要求 selected runtime profile 的 project 在这个集合里。

这说明系统事实上允许 dataset 覆盖多个 project。此时 dataset scoped runtime profile API 静默取第一个 task，会导致：

- 列表接口只返回第一个 project 的 runtime profiles。
- 创建接口会把新 profile 写到第一个 project。
- 如果用户期望为同一 dataset 中另一个 project 选择 profile，API 表现会误导。

现有测试覆盖不足：

- `backend/tests/test_stage1_versioning_runtime_profiles.py::test_dataset_scoped_runtime_profile_create_targets_dataset_project`
  - 只覆盖 demo 单项目 dataset happy path。
- `backend/tests/test_stage1_versioning_runtime_profiles.py::test_experiment_rejects_runtime_profile_from_other_project`
  - 覆盖 profile 完全不属于 dataset project 集合时拒绝。
  - 未覆盖 dataset 内多 project 时 dataset scoped runtime profile API 的行为。

建议最小修复方向：

1. A 线先定义最小合同：dataset scoped runtime profile API 只支持单 project dataset。
2. `_project_id_for_dataset()` 应查询 dataset 下所有 task 对应的 project_id。
3. 如果 project_id 集合为空，返回现有“dataset has no eval tasks”错误。
4. 如果 project_id 集合大小大于 1，返回清晰 400/409，例如：

```text
dataset spans multiple projects; project-scoped runtime profile selection is ambiguous
```

5. 不要静默取第一个 task。

建议补测试：

- 单项目 dataset：list/create runtime profile 正常。
- 多项目 dataset：list/create dataset runtime profiles 返回明确错误。
- 错误信息说明 dataset 多项目导致 runtime profile project 不明确。

## 3. A 对接文档路径卫生

级别：P2

结论：问题成立。

`docs/V2_A_对接文档.md` 仍包含旧本地路径：

```text
D:\17524\MyCode\Trace
```

当前 workspace 是：

```text
D:\GitRepo\专业实训\TRACE
```

命中位置包括：

- 联调步骤根目录说明。
- 启动依赖、初始化数据库、启动 API、启动 Worker、启动前端。
- 测试命令。
- Docker runner 复盘中的构建和 `--basetemp` 示例。

建议最小修复方向：

- 只做文档卫生，把旧绝对路径替换为 `<TRACE_ROOT>`。
- 不要扩大成重写文档。
- Windows 示例可保留 PowerShell 风格，例如：

```powershell
cd <TRACE_ROOT>
cd <TRACE_ROOT>\backend
cd <TRACE_ROOT>\frontend
```

## 4. `false_positive_rate > 0` 但 `metric_status=ok` 的展示口径

级别：P2

结论：当前后端合同允许这种状态，但展示上需要 warning。

当前 metrics 口径是：

- invalid / flaky / setup failure / collection error 等不可评价问题进入 `invalid_test_set`。
- 可评价但 0 捕获进入 `evaluable_zero_capture`。
- 只要存在 captured bug，`metric_status` 必须是 `ok`，即使 `false_positive_rate > 0`。

证据：

- `eval/harness/metrics.py`
  - 聚合逻辑先按 invalid/evaluable 判断状态。
  - total captured 为 0 时才转成 `evaluable_zero_capture`。
  - `false_positive_rate` 是独立字段。
- `backend/app/schemas/evaluation.py`
  - `MetricStatus = "ok" | "invalid_test_set" | "evaluable_zero_capture"`。
  - `ExperimentMetricRow` validator 要求 captured metric rows 使用 `ok`。
- `frontend/src/components/experiment/ExperimentMetricsTable.vue`
  - 表格显示 `false_positive_rate`，但 `metric_status=ok` 仍显示可评价。
- `frontend/src/pages/ComparisonPage.vue`
  - comparison 页同样显示 false positive 数字，但没有 warning badge。

建议处理方向：

1. 不要把 false positive 混进 `invalid_test_set`。
2. 不要改变 captured bug 定义。
3. 暂不扩展 `metric_status` 枚举，除非 A 线愿意同步做 schema、API、前端和兼容测试。
4. 最小可行方案是增加展示层 warning：
   - 当 `metric_status=ok` 且 `false_positive_rate > 0` 时，显示“clean baseline failure contaminates capture rate”一类提示。
   - 可在 metrics row 增加派生字段，例如 `metric_warning` / `has_false_positive_warning`，或先纯前端计算。

建议补测试：

- 前端或 schema 层覆盖：`metric_status=ok` 且 `false_positive_rate > 0` 时显示 warning。
- 确认 `invalid_test_set` 口径不被 false positive 改写。
- 确认 captured bug 计算仍只来自 clean passed + variant assertion failure same nodeid。

## 已执行验证

关键 runtime profile / Docker / dataset 单项目测试：

```powershell
conda run -n trace pytest `
  backend/tests/test_stage1_versioning_runtime_profiles.py::test_runtime_profile_rejects_secret_env_key `
  backend/tests/test_stage1_versioning_runtime_profiles.py::test_dataset_scoped_runtime_profile_create_targets_dataset_project `
  backend/tests/test_stage1_versioning_runtime_profiles.py::test_experiment_rejects_runtime_profile_from_other_project `
  backend/tests/test_executor_runtime_command.py::test_executor_factory_requires_docker_image `
  backend/tests/test_executor_runtime_command.py::test_executor_capabilities_from_docker_snapshot `
  -q
```

结果：

```text
5 passed, 1 warning
```

指标口径相关测试：

```powershell
conda run -n trace pytest `
  backend/tests/test_eval_harness.py::test_aggregate_repeat_stats `
  backend/tests/test_eval_harness.py::test_comparison_table_marks_invalid_test_set `
  backend/tests/test_eval_harness.py::test_failed_clean_run_is_not_evaluable_zero_capture `
  backend/tests/test_stage4_experiment_runner.py::test_experiment_runner_creates_clean_runs_replays_and_db_metrics `
  backend/tests/test_stage4_experiment_runner.py::test_experiment_metrics_use_null_cost_when_no_bug_is_captured `
  backend/tests/test_stage4_experiment_runner.py::test_clean_setup_failure_marks_invalid_test_set `
  backend/tests/test_v2_phase0_contracts.py::test_metric_row_separates_invalid_test_set_from_zero_capture `
  -q
```

结果：

```text
7 passed, 1 warning
```

额外手工验证：

- 当前校验接受 `{"SERVICE_URL": "sk-live-secret-value"}`。
- 当前 Docker command 会包含 `SERVICE_URL=sk-live-secret-value`。

## 未做事项

- 未修改代码。
- 未修改现有 A 线文档。
- 未修改 `backend/llm.config.json`、`.env.local` 或任何密钥文件。
- 未开启 B 线 source context / Contract Guard 新功能。
