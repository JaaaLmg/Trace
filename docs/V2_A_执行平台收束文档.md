# TRACE V2.2 A 线执行平台收束文档

更新时间：2026-06-20

本文是 V2.2 A 线执行平台的收束事实源，整合以下文档的最终口径：

- `docs/V2_A_对接文档.md`
- `docs/V2.2-A线执行平台说明.md`
- `docs/V2_A_对接风险审查.md`
- `docs/V2_A_对接风险修复汇总.md`

旧文档保留作过程记录；后续对接、验收和排障优先看本文。

## 1. 当前结论

V2.2 A 线执行平台已完成当前阶段目标：runtime profile 执行合同、Docker executor MVP、setup/install stage、workspace/artifact/cleanup policy、replay scheduler、incremental replay cache、runtime evidence、EvaluationEvent 扩展和前端证据展示均已落地。

当前验收口径：

- A 线执行平台能力：通过。
- Docker runner 联调：通过。
- 真实 API 端到端链路：通过。
- 策略效果结论：仅作 smoke/evidence，不作正式横向排名。

A 线负责评测尺子与执行平台，不负责 Prompt 文本、Source Context 深度检索、Dataset 完整编辑器或 auto mutation 算子扩展。后续 B 线工作不得反向改变 A 线评测有效性口径。

## 2. A 线交付范围

已交付能力：

- Runtime profile 执行合同：executor、Docker image、working dir、install/test command、timeout、network/resource policy、artifact/cleanup policy 会冻结到 run/replay evidence。
- Executor 抽象：支持 `local_subprocess` 与 `docker`，并记录 executor capability evidence。
- Docker executor MVP：检查 Docker CLI/daemon/image，构造受控 workspace mount，收集 pytest JSON/JUnit/stdout/stderr/container metadata。
- Setup/install stage：安装步骤是 first-class execution step；setup failure 进入 `setup_failed` EvaluationEvent，不算 0 捕获。
- Workspace/artifact/cleanup policy：记录 workspace manifest、artifact hash、artifact roles；cleanup 支持 dry-run，并限制在 TRACE 实验工作目录内。
- Replay scheduler：variant replay 可按配置并发；clean replay 与 flaky gate 仍先于同 clean unit 的 variant replay。
- Incremental replay cache：记录 cache key、hit/miss/stale、source replay id 和 invalidation reasons。
- Metrics/Event evidence：metrics 和 EvaluationEvent 展示 executor、runtime、setup、cache、cleanup、parallel replay 证据。
- 前端产品面：Experiment 列表/详情、Replay evidence panel、Runtime profile 管理页已接入 A 线证据。
- 国际化：Runtime 页面接入中英文切换；API 枚举值保留原文。

## 3. 稳定合同与关键口径

- `local_subprocess` 是本机进程执行，不是安全沙箱。它有固定 workdir、超时、pytest 插件和路径约束，但不能宣称 enforce 网络或资源隔离。
- `docker` 是可选执行器。Docker 不可用、daemon 不可达或 image 不满足要求时，应报告 `executor_unavailable`，不能解释成 0 捕获。
- provider failure、executor failure、setup failure、artifact hash mismatch、invalid/flaky test set 都是评测有效性问题，不能压成 0 捕获。
- replay 不调用 LLM；`llm_calls` 必须为 0。
- runtime snapshot、strategy snapshot 和 generated test set artifact 是历史运行解释依据；profile 后续更新不能改变已完成 run/replay 的证据。
- `.env.local` 和 `backend/llm.config.json` 可能包含真实密钥，不能入库、进文档、进日志或进 evidence。
- `false_positive_rate > 0` 是测试质量 warning，不是不可评价状态；不要把 false positive 混进 `invalid_test_set`。

## 4. Runtime Profile 与 Executor

Runtime profile 关键字段：

- `executor`: `local_subprocess | docker`
- `image`: Docker executor 必填，local 可为空。
- `working_dir`: 容器内或执行 workspace 的工作目录。
- `install_command`: setup/install stage 命令，可为空。
- `test_command`: pytest 命令。
- `network_policy`: `default | disabled | install_only`
- `timeout_seconds`: 正整数。
- `resource_limits`: 内存、CPU 等限制；local subprocess 不 enforce。
- `env_template`: 只存 key/模板，不存 secret value。
- `artifact_policy` / `cleanup_policy`: 产物保留和清理策略。

`env_template` 当前合同：

- 新写入数据不允许保存真实 secret value。
- key 命中 `api_key`、`apikey`、`secret`、`token`、`password`、`authorization` 等敏感词会被拒绝。
- value 只允许 `null`、空字符串、`${NAME}` 占位符或 `<NAME>` 占位符。
- 旧数据中的非法 value 会在迁移、API 输出、runtime snapshot 构造和 metrics 合同层被替换为 `<REDACTED>`。
- 旧数据中的敏感 key 会从输出和 snapshot 中移除。
- Docker executor 只按 `env_template` key 从宿主进程环境读取，并使用 `docker -e KEY` 形式透传，不把 value 写入 command/evidence。
- `<REDACTED>` 只表示历史数据曾包含不可接受 value，不会被 executor 当作真实环境变量值注入。

相关实现索引：

- `backend/app/core/env_templates.py`
- `backend/app/services/runtime_profiles.py`
- `backend/app/services/test_runs.py`
- `backend/app/schemas/api_runtime_profile.py`
- `backend/app/schemas/api_run.py`
- `backend/app/schemas/api_evaluation.py`
- `backend/app/schemas/evaluation.py`
- `backend/app/tools/executor.py`
- `backend/alembic/versions/20260620_0007_sanitize_env_templates.py`

## 5. Dataset Runtime Profile 约束

Dataset scoped runtime profile API 当前只支持单 project dataset。

稳定口径：

- `GET /api/v1/eval-datasets/{dataset_id}/runtime-profiles` 会收集 dataset 下所有 task 对应的 `ProjectSnapshot.project_id`。
- dataset 下没有 task 时返回 404：`dataset has no eval tasks`。
- dataset 只对应一个 project 时保持 list/create 行为。
- dataset 跨多个 project 时返回 409：

```text
dataset spans multiple projects; project-scoped runtime profile selection is ambiguous
```

多 project dataset 后续如需支持，应新增显式 project 选择参数或改成 project scoped UI/API，不应再隐式选择首个 task。

## 6. Experiment / Replay / Metrics 证据

每个 clean run 会冻结 runtime profile 到 `runtime_snapshot`，包括：

- executor kind
- Docker image / working dir
- install/test command
- timeout
- network policy
- resource limits
- artifact / cleanup policy
- executor capabilities
- env key names，不包含 secret value

每条 replay 记录：

- `runtime_snapshot`
- `executor_metadata`
- `workspace_manifest`
- `cache_key`
- `cache_status`
- `source_replay_id`

`workspace_manifest` 是 replay 输入/执行证据的轻量索引，包含 source snapshot、generated test set hash、variant、executor、runtime hash 和 workspace root。

Metrics 口径：

- `metric_status=invalid_test_set`：测试集不可评价，例如 setup failed、clean replay collection error、flaky clean replay、artifact hash mismatch 等。
- `metric_status=evaluable_zero_capture`：测试集可评价，但没有捕获 seeded bug。
- `metric_status=ok`：存在 captured bug。若 `false_positive_rate > 0`，前端显示 warning，提醒 clean baseline failure 会污染捕获率。
- captured bug 仍按 clean passed nodeid 在 variant 上 assertion failure 的规则计算。

## 7. API 对接索引

Runtime profile：

- `GET /api/v1/runtime-profiles/executors/status`
- `GET /api/v1/projects/{project_id}/runtime-profiles`
- `POST /api/v1/projects/{project_id}/runtime-profiles`
- `GET /api/v1/eval-datasets/{dataset_id}/runtime-profiles`
- `POST /api/v1/eval-datasets/{dataset_id}/runtime-profiles`
- `GET /api/v1/runtime-profiles/{runtime_profile_id}`
- `PATCH /api/v1/runtime-profiles/{runtime_profile_id}`
- `POST /api/v1/runtime-profiles/{runtime_profile_id}/archive`

Experiment：

- `POST /api/v1/experiments`
- `POST /api/v1/experiments/{experiment_id}/runs`
- `GET /api/v1/experiments/{experiment_id}/metrics`
- `GET /api/v1/experiments/{experiment_id}/clean-runs`
- `GET /api/v1/experiments/{experiment_id}/replay-runs`
- `POST /api/v1/experiments/{experiment_id}/cleanup`

Cleanup 默认 `dry_run=true`。真实删除必须显式传 `dry_run=false`，且路径必须通过 TRACE experiment work root 边界检查。

## 8. 前端展示口径

前端入口：

- 导航栏 `运行环境` / `Runtime`：管理 runtime profile。
- 实验列表页：创建 experiment 时选择 dataset、runtime profile、strategy、repeat、provider/model。
- 实验详情页：查看 metrics、runtime execution summary、EvaluationEvent timeline、clean run、replay evidence。
- Replay evidence panel：展示 executor、runtime snapshot hash、artifact hash、cache status、setup/executor error 等证据。

展示规则：

- `local_subprocess`、`docker`、`default`、`disabled`、`install_only` 是 API 枚举值，前端保留原文。
- `metric_status=ok` 且 `false_positive_rate > 0` 时，前端显示 false positive warning。
- Docker 不可用、setup failure、invalid test set 不得显示成策略 0 捕获。

## 9. 本地联调步骤

以下命令以仓库根目录 `<TRACE_ROOT>` 为例。

启动依赖：

```powershell
cd <TRACE_ROOT>
docker compose up -d
```

初始化数据库和 demo 数据：

```powershell
cd <TRACE_ROOT>\backend
conda activate trace
python scripts/init_db.py
python scripts/seed_strategies.py
python scripts/seed_eval_demo.py
```

启动后端 API：

```powershell
cd <TRACE_ROOT>\backend
conda activate trace
python scripts/run_api.py
```

默认地址：

```text
http://127.0.0.1:8000
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/healthz
```

启动 Worker：

```powershell
cd <TRACE_ROOT>\backend
conda activate trace
python scripts/run_worker.py
```

新建实验或真实 LLM run 必须启动 Worker。只查看历史 metrics 时可以不启动 Worker。

启动前端：

```powershell
cd <TRACE_ROOT>\frontend
npm install
npm run dev
```

默认前端地址：

```text
http://127.0.0.1:5186
```

前端业务流程验证：

1. 打开 `http://127.0.0.1:5186`。
2. 切到中文，进入 `运行环境`，确认 runtime 页面文案为中文。
3. 在 API 模式下检查 executor status。
4. 选择项目，新建或编辑 runtime profile。
5. 进入 `实验`，创建 experiment。
6. 点击运行，等待 queued/running 进入 completed 或 failed。
7. 打开实验详情，核对 metrics、runtime execution summary、clean run drilldown、replay evidence 和 Evaluation Events。
8. 如需验证 cleanup，先调用 dry-run。

Cleanup dry-run 示例：

```powershell
Invoke-RestMethod `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"dry_run": true, "keep_failed": true}' `
  http://127.0.0.1:8000/api/v1/experiments/<experiment_id>/cleanup
```

## 10. 验证命令

后端完整测试：

```powershell
cd <TRACE_ROOT>
conda activate trace
python -m pytest backend/tests -q
```

A 线重点测试：

```powershell
cd <TRACE_ROOT>
conda activate trace
python -m pytest `
  backend/tests/test_stage1_versioning_runtime_profiles.py `
  backend/tests/test_replay_scheduler.py `
  backend/tests/test_artifact_cleanup.py `
  backend/tests/test_executor_runtime_command.py `
  backend/tests/test_stage4_experiment_runner.py `
  -q
```

env/runtime snapshot 安全回归：

```powershell
cd <TRACE_ROOT>
conda activate trace
python -m pytest `
  backend/tests/test_stage1_versioning_runtime_profiles.py `
  backend/tests/test_executor_runtime_command.py::test_docker_executor_env_template_reads_host_environment `
  backend/tests/test_schema_migrations.py `
  backend/tests/test_v2_phase0_contracts.py::test_metrics_runtime_snapshots_sanitize_legacy_env_templates `
  -q
```

Docker 可用时单独跑 Docker integration：

```powershell
cd <TRACE_ROOT>
conda activate trace
python -m pytest `
  backend/tests/test_executor_runtime_command.py::test_docker_executor_runs_pytest_with_local_docker `
  backend/tests/test_executor_runtime_command.py::test_docker_executor_replays_frozen_tests_clean_and_variant `
  -q -rs
```

前端类型检查：

```powershell
cd <TRACE_ROOT>
npm --prefix frontend run typecheck
```

最近针对 A 线风险收口的验证结果：

```text
25 passed, 1 warning
python -m py_compile backend/app/schemas/evaluation.py passed
npm --prefix frontend run typecheck passed
```

## 11. 已关闭风险复盘

### 11.1 env_template secret value

原风险：

- 旧实现只拒绝敏感 key，不拒绝安全 key 下的 secret-looking value。
- `runtime_snapshot` 会冻结完整 `env_template`。
- Docker executor 会把 value 拼进 `docker run -e KEY=value`，导致 secret 进入 command/evidence。

当前状态：

- 新写入 profile 时拒绝敏感 key 和非法 value。
- Docker 只使用 `docker -e KEY` 透传宿主环境变量。
- API 输出、run detail、replay run、metrics 合同层均清洗 runtime snapshot。
- Alembic 迁移清洗既有 `runtime_profiles.env_template`、`test_runs.runtime_snapshot.env_template`、`test_replays.runtime_snapshot.env_template`。
- `RuntimeSnapshotContract` 是最终兜底，任何进入 metrics/clean/replay 合同的 legacy env value 都会被清洗。

### 11.2 Dataset runtime profile 首 task 推导

原风险：

- dataset scoped runtime profile API 静默取第一个 task 的 project，遇到多 project dataset 会误导。

当前状态：

- dataset scoped runtime profile API 明确只支持单 project dataset。
- 多 project dataset 返回 409，不再隐式选择。

### 11.3 文档路径卫生

原风险：

- A 对接文档中存在个人本地绝对路径。

当前状态：

- 对接文档示例路径已统一替换为 `<TRACE_ROOT>`。
- 后续文档示例继续使用 `<TRACE_ROOT>`。

### 11.4 false positive 展示误导

原风险：

- `metric_status=ok` 且 `false_positive_rate > 0` 时，只显示可评价可能误导用户。

当前状态：

- 前端在该组合下展示 warning。
- 后端捕获定义、`MetricStatus` 枚举和 `invalid_test_set` 口径保持不变。

## 12. 常见排障

- Runtime 页面中文仍显示英文：确认浏览器 `trace-locale` 为 `zh`，再刷新。技术枚举值保持英文是预期。
- Experiment 卡在 queued：检查 Redis、Worker 是否启动，以及 Worker 队列是否为 `trace_test_runs`。
- `/healthz` 没有 LLM 信息：检查 `backend/llm.config.json` 或环境变量是否可读。
- Docker profile 运行失败：先看 `GET /api/v1/runtime-profiles/executors/status`，确认 Docker daemon、image 和挂载权限。
- metrics 出现 `invalid_test_set`：这是不可评价测试集，不是 0 捕获。需要看 EvaluationEvent 和 clean replay evidence。
- setup 失败：查看 setup logs artifact 和 `setup_failed` EvaluationEvent。
- cleanup 没有删除文件：默认 dry-run 只列候选；真实删除必须显式传 `dry_run=false`，且路径必须通过安全边界检查。
- 容器一闪而过：优先查看工作目录中的 `.trace_pytest_report.json` 和 `.trace_junit.xml`。
- 出现 `ModuleNotFoundError`：检查 Docker image 是否包含被测项目依赖。
- 出现 `collection_errors > 0`：不要解释为 0 捕获，应归类为测试集不可评价。
- 出现 `false_positive_rate > 0`：说明测试集在 clean 版本上失败，需要优化 prompt/source context 或测试过滤口径。

## 13. 剩余非阻塞事项

- Dataset 完整 task / seeded bug / variant 编辑器属于 B 线或后续产品面。
- Prompt / Tool schema 管理页尚未实现。
- 当前 replay scheduler 是单机并发，不是跨机器分布式调度。
- `experiments.py` 仍保留部分兼容 facade 和 clean-run 逻辑，后续可继续做机械拆分。
- Docker executor MVP 仍需在更多宿主系统和 image 类型上扩展兼容性测试。
- Docker runtime profile 的 `env_template` 不负责保存 secret。后续如需要真实 secret 注入，应设计单独的安全注入机制。
- 多 project dataset 的 runtime profile 交互设计留待后续产品/API 设计处理。
- 如果需要 API 级风险摘要，可在后续增加 `metric_warning` 或 `warnings` 字段；不要在未设计清楚前改变捕获定义。
