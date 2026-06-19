# TRACE V2.2 A 线对接文档

## 1. 对接范围

本文记录 V2.2 A 线已经完成的执行平台能力，以及前后端、API、配置和测试联调注意事项。A 线负责评测尺子与执行平台，不负责 Prompt 文本、Source Context 深度检索、Dataset 完整编辑器或 auto mutation 算子扩展。

A 线当前已交付：

- Runtime profile 执行合同：把 executor、Docker image、working dir、install/test command、timeout、network/resource policy、artifact/cleanup policy 冻结进 run/replay evidence。
- Executor 抽象：支持 `local_subprocess` 与 `docker`，并记录 executor capability evidence。
- Docker executor MVP：可检查 Docker CLI/daemon/image，构造受控 workspace mount，收集 pytest JSON/JUnit/stdout/stderr/container metadata。
- Setup/install stage：安装步骤成为 first-class execution step；setup failure 进入 `setup_failed` EvaluationEvent，不被算成 0 捕获。
- Workspace/artifact/cleanup policy：记录 workspace manifest、artifact hash、artifact roles；cleanup 支持 dry-run 并限制在 TRACE 实验工作目录内。
- Replay scheduler：variant replay 可按配置并发，clean replay 与 flaky gate 仍先于同 clean unit 的 variant replay。
- Incremental replay cache：记录 cache key、hit/miss/stale、source replay id 和 invalidation reasons。
- Metrics/Event evidence：metrics 和 EvaluationEvent 已展示 executor、runtime、setup、cache、cleanup、parallel replay 证据。
- 前端产品面：Experiment 列表/详情、Replay evidence panel、Runtime profile 管理页已接入 A 线证据。
- 国际化收尾：Runtime 页面已接入中英文切换，保留 API 枚举值原文。

## 2. 关键口径

- `local_subprocess` 是本机进程执行，不是安全沙箱。它有固定 workdir、超时、pytest 插件和路径约束，但不能宣称 enforce 网络或资源隔离。
- `docker` 是可选执行器。Docker 不可用、daemon 不可达或 image 不满足要求时，应报告 `executor_unavailable`，不能解释成 0 捕获。
- provider failure、executor failure、setup failure、artifact hash mismatch、invalid/flaky test set 都是评测有效性问题，不能压成 0 捕获。
- replay 不调用 LLM；`llm_calls` 必须为 0。
- runtime snapshot、strategy snapshot 和 generated test set artifact 是历史运行解释依据，profile 后续更新不能改变已完成 run/replay 的证据。
- `.env.local` 和 `backend/llm.config.json` 可能包含真实密钥，不能入库。

## 3. 后端对接

### 3.1 主要 API

Runtime profile：

- `GET /api/v1/runtime-profiles/executors/status`
  - 返回 `local_subprocess` 和 `docker` 的可用性、隔离级别、网络/资源限制是否可 enforce。
- `GET /api/v1/projects/{project_id}/runtime-profiles`
  - 列出项目下未归档 profile；首次访问会创建默认 profile。
- `POST /api/v1/projects/{project_id}/runtime-profiles`
  - 创建 profile。
- `GET /api/v1/eval-datasets/{dataset_id}/runtime-profiles`
  - 按 dataset 首个 task 的 project snapshot 推导可用 profile，供 experiment 创建页选择。
- `PATCH /api/v1/runtime-profiles/{runtime_profile_id}`
  - 更新 profile。历史 run/replay 使用冻结 snapshot，不受后续更新影响。
- `POST /api/v1/runtime-profiles/{runtime_profile_id}/archive`
  - 归档 profile。

Experiment：

- `POST /api/v1/experiments`
  - 创建实验，可传 `runtime_profile_id`、`strategy_version_ids`、`repeat_count`、`llm_override`。
- `POST /api/v1/experiments/{experiment_id}/runs`
  - 入队运行实验。
- `GET /api/v1/experiments/{experiment_id}/metrics`
  - 返回 metrics、runtime_execution、clean_runs、replay_runs、evaluation_events、artifacts。
- `GET /api/v1/experiments/{experiment_id}/clean-runs`
  - 查看 clean run 列表。
- `GET /api/v1/experiments/{experiment_id}/replay-runs`
  - 查看 replay 列表。
- `POST /api/v1/experiments/{experiment_id}/cleanup`
  - 清理实验 workspace，默认 `dry_run=true`。

### 3.2 Runtime profile 字段

前端和后端对接时重点关注：

- `executor`: `local_subprocess | docker`
- `image`: Docker executor 必填，local 可为空。
- `working_dir`: 容器内或执行 workspace 的工作目录。
- `install_command`: setup/install stage 命令，可为空。
- `test_command`: pytest 命令。
- `network_policy`: `default | disabled | install_only`
- `timeout_seconds`: 正整数。
- `resource_limits`: 例如内存、CPU 限制；local subprocess 不 enforce。
- `env_template`: 只存 key/模板，不存 secret value。
- `artifact_policy` / `cleanup_policy`: 产物保留和清理策略。

## 4. 前端对接

前端入口：

- 导航栏 `运行环境` / `Runtime`：进入 `#/runtime` 管理 runtime profile。
- 实验列表页：创建 experiment 时可选择 dataset、runtime profile、strategy、repeat、provider/model。
- 实验详情页：查看 metrics、runtime execution summary、EvaluationEvent timeline、clean run、replay evidence。
- Replay evidence panel：展示 executor、runtime snapshot hash、artifact hash、cache status、setup/executor error 等证据。

国际化注意事项：

- Runtime 页面已使用 `frontend/src/i18n.ts` 的 `runtime.*` 字典。
- 中文模式下用户可见文案会显示中文。
- `local_subprocess`、`docker`、`default`、`disabled`、`install_only` 是 API 枚举值，前端保留原文，便于排错和与后端合同一致。

## 5. 配置说明

### 5.1 环境变量

根目录 `.env.local` 用于本地联调，常用键：

```text
TRACE_DB_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/trace_test
TRACE_REDIS_URL=redis://127.0.0.1:6379/0
TRACE_API_HOST=127.0.0.1
TRACE_API_PORT=8000
```

前端 dev server 默认代理到 `http://127.0.0.1:8000`。如果后端端口变化：

```powershell
$env:VITE_TRACE_API_PROXY_TARGET="http://127.0.0.1:8001"
```

### 5.2 LLM 配置

`backend/llm.config.json` 用于真实大模型 API。示例：

```json
{
  "provider": "openai_chat_compat",
  "base_url": "https://api.example.com/v1",
  "model": "your-model",
  "api_key": "your-api-key",
  "temperature": 0,
  "max_output_tokens": 8192
}
```

也可以用环境变量覆盖。不要把真实 key 写入文档、日志或 Git。

### 5.3 Docker executor

使用 Docker executor 前需要：

- 本机 Docker CLI 可执行。
- Docker daemon 正常运行。
- runtime profile 中填写可用 image，例如本地已构建的 `trace-pytest:3.12` 或可拉取的 Python image。
- Windows 下注意路径挂载和 Docker Desktop 文件共享权限。

Docker executor 不可用时，后端应返回 `executor_unavailable` 或在 executor status 中显示 unavailable reason。前端不得把该失败解释为策略未捕获 bug。

## 6. 推荐联调步骤

以下命令以仓库根目录 `D:\17524\MyCode\Trace` 为例。

### 6.1 启动依赖

```powershell
cd D:\17524\MyCode\Trace
docker compose up -d
```

### 6.2 初始化数据库和 demo 数据

```powershell
cd D:\17524\MyCode\Trace\backend
conda activate trace
python scripts/init_db.py
python scripts/seed_strategies.py
python scripts/seed_eval_demo.py
```

### 6.3 启动后端 API

```powershell
cd D:\17524\MyCode\Trace\backend
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

### 6.4 启动 Worker

```powershell
cd D:\17524\MyCode\Trace\backend
conda activate trace
python scripts/run_worker.py
```

新建实验或真实 LLM run 必须启动 Worker。只查看历史 metrics 时可以不启动 Worker。

### 6.5 启动前端

```powershell
cd D:\17524\MyCode\Trace\frontend
npm install
npm run dev
```

默认前端地址：

```text
http://127.0.0.1:5186
```

### 6.6 前端业务流程验证

1. 打开 `http://127.0.0.1:5186`。
2. 切到中文，进入 `运行环境`，确认 runtime 页面文案为中文。
3. 在 API 模式下检查 executor status：
   - `local_subprocess` 应 available，但提示不是安全沙箱。
   - `docker` 是否 available 取决于本机 Docker。
4. 选择项目，新建或编辑 runtime profile。
5. 进入 `实验`，创建 experiment：
   - 选择 demo dataset。
   - 选择 runtime profile。
   - 选择 Direct / Plan / ReAct strategy versions。
   - 填写真实 LLM provider/model 或使用默认配置。
6. 点击运行，等待 queued/running 进入 completed 或 failed。
7. 打开实验详情，核对：
   - metrics rows 的 `metric_status`。
   - runtime execution summary。
   - clean run drilldown。
   - replay evidence 的 runtime snapshot、executor metadata、workspace manifest、cache status。
   - Evaluation Events 是否把 setup/executor/cache/invalid 等事件独立展示。
8. 如需验证 cleanup，先调用 dry-run：

```powershell
Invoke-RestMethod `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"dry_run": true, "keep_failed": true}' `
  http://127.0.0.1:8000/api/v1/experiments/<experiment_id>/cleanup
```

确认候选路径都在 TRACE experiment work root 内，再考虑执行非 dry-run。

## 7. 测试命令

后端完整测试：

```powershell
cd D:\17524\MyCode\Trace
conda activate trace
python -m pytest backend/tests -q
```

A 线重点测试：

```powershell
cd D:\17524\MyCode\Trace
conda activate trace
python -m pytest `
  backend/tests/test_stage1_versioning_runtime_profiles.py `
  backend/tests/test_replay_scheduler.py `
  backend/tests/test_artifact_cleanup.py `
  backend/tests/test_executor_runtime_command.py `
  backend/tests/test_stage4_experiment_runner.py `
  -q
```

Docker 可用时可单独跑 Docker integration：

```powershell
cd D:\17524\MyCode\Trace
conda activate trace
python -m pytest `
  backend/tests/test_executor_runtime_command.py::test_docker_executor_runs_pytest_with_local_docker `
  backend/tests/test_executor_runtime_command.py::test_docker_executor_replays_frozen_tests_clean_and_variant `
  -q -rs
```

前端类型检查：

```powershell
cd D:\17524\MyCode\Trace
npm --prefix frontend run typecheck
```

## 8. 常见问题

- Runtime 页面中文仍显示英文：先确认浏览器 `trace-locale` 为 `zh`，再刷新。技术枚举值保持英文是预期。
- Experiment 卡在 queued：检查 Redis、Worker 是否启动，以及 Worker 队列是否为 `trace_test_runs`。
- `/healthz` 没有 LLM 信息：检查 `backend/llm.config.json` 或环境变量是否可读。
- Docker profile 运行失败：先看 `GET /api/v1/runtime-profiles/executors/status`，确认 Docker daemon、image 和挂载权限。
- metrics 出现 `invalid_test_set`：这是不可评价测试集，不是 0 捕获。需要看 EvaluationEvent 和 clean replay evidence。
- setup 失败：查看 setup logs artifact 和 `setup_failed` EvaluationEvent。
- cleanup 没有删除文件：默认 dry-run 只列候选；真实删除必须显式传 `dry_run=false`，且路径必须通过安全边界检查。

## 9. 后续非阻塞增强

- Dataset 完整 task / seeded bug / variant 编辑器属于 B 线或后续产品面。
- Prompt / Tool schema 管理页尚未实现。
- 当前 replay scheduler 是单机并发，不是跨机器分布式调度。
- `experiments.py` 仍保留部分兼容 facade 和 clean-run 逻辑，后续可继续做机械拆分。
- Docker executor MVP 仍需在更多宿主系统和 image 类型上扩展兼容性测试。
