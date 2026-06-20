# TRACE V2.2 A 线对接风险修复汇总

修复日期：2026-06-20

对应审查文档：`docs/V2_A_对接风险审查.md`

本文记录对风险审查中 4 个问题的复核结论、修复内容、涉及文件和验证结果。目标是给后续对接、验收和继续优化提供一个简洁的变更索引。

## 1. env_template 可能误存 secret value

审查结论：属实。

风险摘要：

- 原实现只拒绝敏感 key，例如 `API_TOKEN`。
- 普通 key 下的疑似 secret value，例如 `SERVICE_URL=sk-live-secret-value`，可以被保存到 DB。
- runtime snapshot 会冻结完整 `env_template`。
- Docker executor 会把 value 拼进 `docker run -e KEY=value`，导致 secret 进入 command/evidence。

修复内容：

- `env_template` value 现在只允许：
  - `null`
  - 空字符串
  - `${NAME}` 占位符
  - `<NAME>` 占位符
- 继续拒绝敏感 key：`api_key`、`apikey`、`secret`、`token`、`password`、`authorization`。
- 新增疑似 secret value 检测，例如 `bearer `、`sk-`、`ghp_`、`github_pat_`、`xoxb-`、`xoxp-`、`eyj`。
- Docker executor 不再从 runtime snapshot 的 value 注入环境变量。
- Docker executor 现在只按 `env_template` 的 key 从宿主进程环境读取，并使用 `docker -e KEY` 形式透传，避免 value 出现在 command/evidence 中。
- 针对后续审查发现的历史数据风险，新增统一清洗逻辑：
  - `sanitize_env_template()` 会保留 `null`、空字符串、`${NAME}`、`<NAME>`。
  - 旧库中已存在的非法 value 会在输出和快照构造时替换为 `<REDACTED>`。
  - 旧库中已存在的敏感 key，例如 `API_TOKEN`，会从输出和快照中移除。
- runtime profile API 输出现在统一清洗 `env_template`。
- 创建 run 时，`runtime_snapshot.env_template` 和 `runtime_snapshot.env_keys` 统一基于清洗后的模板生成。
- 读取历史 run 时，`TestRunOut.runtime_snapshot.env_template` 也会在响应层清洗，避免旧 snapshot 继续经 API 泄露。
- 读取 experiment replay runs 时，`TestReplayOut.runtime_snapshot.env_template` 也会在响应层清洗。
- 新增 Alembic 迁移 `20260620_0007_sanitize_env_templates.py`，用于清洗既有：
  - `runtime_profiles.env_template`
  - `test_runs.runtime_snapshot.env_template`
  - `test_replays.runtime_snapshot.env_template`

涉及文件：

- `backend/app/core/env_templates.py`
- `backend/app/services/runtime_profiles.py`
- `backend/app/services/test_runs.py`
- `backend/app/schemas/api_runtime_profile.py`
- `backend/app/schemas/api_run.py`
- `backend/app/schemas/api_evaluation.py`
- `backend/app/tools/executor.py`
- `backend/alembic/versions/20260620_0007_sanitize_env_templates.py`
- `backend/tests/test_stage1_versioning_runtime_profiles.py`
- `backend/tests/test_executor_runtime_command.py`

新增/更新测试：

- `test_runtime_profile_rejects_secret_env_key`
- `test_runtime_profile_rejects_secret_like_env_value`
- `test_runtime_profile_api_redacts_legacy_secret_env_value`
- `test_create_run_sanitizes_legacy_runtime_profile_snapshot`
- `test_run_detail_redacts_legacy_frozen_runtime_snapshot`
- `test_docker_executor_env_template_reads_host_environment`

当前合同：

- `env_template` 是“允许注入哪些环境变量”的模板，不是 secret 存储。
- 新写入数据不允许保存真实 secret value。
- 旧数据在迁移后会被持久清洗；即使未执行迁移，API 输出和新建 run 的 runtime snapshot 也会清洗。
- runtime snapshot、executor metadata、API response 中不应出现真实 secret value。
- `<REDACTED>` 只表示历史数据曾包含不可接受 value，不会被 executor 当作真实环境变量值注入。
- 如后续需要更完整的运行时 secret 注入，应接入单独 secret provider，而不是扩展 `env_template` 保存真实值。

## 2. Dataset scoped runtime profile API 静默取首个 task

审查结论：属实。

风险摘要：

- 原 `_project_id_for_dataset()` 按 dataset 的首个 task 推导 project。
- 当前模型允许 dataset 包含多个 `project_snapshot_id`。
- experiment 创建逻辑也按 dataset project 集合判断 profile 是否属于 dataset。
- 因此 dataset scoped runtime profile API 静默取第一个 task 会在多项目 dataset 下产生误导。

修复内容：

- `_project_id_for_dataset()` 改为收集 dataset 下所有 task 对应的 `ProjectSnapshot.project_id`。
- 如果 dataset 下没有 task，继续返回 404：`dataset has no eval tasks`。
- 如果 dataset 只对应一个 project，保持原 list/create 行为。
- 如果 dataset 跨多个 project，返回 409：

```text
dataset spans multiple projects; project-scoped runtime profile selection is ambiguous
```

涉及文件：

- `backend/app/api/routes/runtime_profiles.py`
- `backend/tests/test_stage1_versioning_runtime_profiles.py`

新增/更新测试：

- `test_dataset_scoped_runtime_profile_create_targets_dataset_project`
- `test_dataset_scoped_runtime_profiles_reject_multi_project_dataset`
- `test_experiment_rejects_runtime_profile_from_other_project`

当前合同：

- Dataset scoped runtime profile API 只支持单 project dataset。
- 多 project dataset 后续如需支持，应新增显式 project 选择参数或改成 project scoped UI/API，不应再隐式选择首个 task。

## 3. A 对接文档路径卫生

审查结论：属实。

风险摘要：

- `docs/V2_A_对接文档.md` 中存在个人本地绝对路径 `D:\17524\MyCode\Trace`。
- 对接文档应能被其他成员直接复用，不应绑定某台机器路径。

修复内容：

- 将 `docs/V2_A_对接文档.md` 中的个人绝对路径统一替换为 `<TRACE_ROOT>`。
- 保留 PowerShell 命令风格，例如：

```powershell
cd <TRACE_ROOT>
cd <TRACE_ROOT>\backend
cd <TRACE_ROOT>\frontend
```

涉及文件：

- `docs/V2_A_对接文档.md`

验证：

- 已确认文档中不再命中：
  - `D:\17524`
  - `MyCode\Trace`
  - `D:/17524`

当前合同：

- 后续文档示例统一使用 `<TRACE_ROOT>` 表示仓库根目录。
- 如必须举具体路径，应明确为“示例路径”，不要写成默认路径。

## 4. false_positive_rate > 0 且 metric_status=ok 的展示口径

审查结论：属实。

风险摘要：

- 后端合同允许 `metric_status=ok` 且 `false_positive_rate > 0`。
- 这代表测试集可评价，但 clean baseline 上存在失败。
- 如果前端只显示“可评价”和捕获率，用户可能误以为捕获率完全可信。

修复内容：

- 不修改后端捕获定义。
- 不修改 `MetricStatus` 枚举。
- 不把 false positive 混入 `invalid_test_set`。
- 在前端展示层新增 warning：
  - 当 `metric_status === "ok"` 且 `false_positive_rate > 0` 时显示提示。
  - 中文文案：`Clean baseline 失败会污染捕获率`
  - 英文文案：`Clean baseline failure contaminates capture rate`

涉及文件：

- `frontend/src/components/experiment/ExperimentMetricsTable.vue`
- `frontend/src/pages/ComparisonPage.vue`
- `frontend/src/i18n.ts`

验证：

- 前端类型检查通过。
- 后端指标合同测试通过，确认 `invalid_test_set`、`evaluable_zero_capture`、`ok` 口径未被 false positive warning 改写。

当前合同：

- `false_positive_rate > 0` 是质量 warning，不是不可评价状态。
- 捕获率仍按 clean passed nodeid 在 variant 上 assertion failure 的规则计算。
- 后续可考虑增加 `metric_warning` 字段或更细的 UI 风险等级，但不应在未设计清楚前改变捕获定义。

## 5. 验证结果

已执行后端针对性回归：

```powershell
python -m pytest --basetemp <TRACE_ROOT>\.pytest_tmp_codex `
  backend/tests/test_stage1_versioning_runtime_profiles.py `
  backend/tests/test_executor_runtime_command.py::test_docker_executor_env_template_reads_host_environment `
  backend/tests/test_executor_runtime_command.py::test_executor_factory_requires_docker_image `
  backend/tests/test_executor_runtime_command.py::test_executor_capabilities_from_docker_snapshot `
  backend/tests/test_eval_harness.py::test_aggregate_repeat_stats `
  backend/tests/test_eval_harness.py::test_comparison_table_marks_invalid_test_set `
  backend/tests/test_eval_harness.py::test_failed_clean_run_is_not_evaluable_zero_capture `
  backend/tests/test_v2_phase0_contracts.py::test_metric_row_separates_invalid_test_set_from_zero_capture `
  backend/tests/test_v2_phase0_contracts.py::test_invalid_clean_replay_collection_error_is_not_false_positive_contract_failure `
  -q
```

结果：

```text
20 passed
```

本轮针对历史 `env_template` secret value 遗留风险追加执行：

```powershell
python -m pytest --basetemp <TRACE_ROOT>\.pytest_tmp_codex backend/tests/test_stage1_versioning_runtime_profiles.py -q
python -m pytest --basetemp <TRACE_ROOT>\.pytest_tmp_codex backend/tests/test_executor_runtime_command.py::test_docker_executor_env_template_reads_host_environment -q
```

结果：

```text
15 passed
1 passed
```

已执行前端类型检查：

```powershell
npm --prefix frontend run typecheck
```

结果：

```text
vue-tsc --noEmit passed
```

已执行格式检查：

```powershell
git diff --check
```

结果：

```text
passed
```

## 6. 剩余注意事项

- `docs/V2_A_对接风险审查.md` 是审查输入文档，本次未修改。
- Docker runtime profile 的 `env_template` 现在不负责保存 secret。后续如需要真实 secret 注入，应设计单独的安全注入机制。
- 本次迁移不可逆恢复 secret-looking value；downgrade 不会还原已经被 `<REDACTED>` 替换或被移除的历史敏感 key。
- Dataset scoped runtime profile API 当前明确只支持单 project dataset。多 project dataset 的交互设计应留到后续产品/API 设计中处理。
- false positive warning 目前是前端派生展示；后续如果需要 API 级风险摘要，可以再加 `metric_warning` 或 `warnings` 字段。
