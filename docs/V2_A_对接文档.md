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

## 10. Docker runner 真实联调问题复盘与可用性评估

本节记录 2026-06-20 使用本地 Docker runner 与真实大模型 API 进行前后端联调时暴露的问题、修复过程、验证结果和当前可用性边界。后续优化 Docker runtime、prompt/source context 或指标口径时，应优先参考本节。

### 10.1 初始现象：Docker 实验全部 0% 捕获

现象：

- 前端实验详情页中，Direct、Plan-and-Execute、ReAct+Reflection 三个策略捕获率均显示 `0% (0/6)`。
- 三个策略状态均为 `不可评价 (1)`，单捕获成本显示 `不可评价`。
- Runtime execution summary 显示 executor 为 `docker`，setup 为 `skipped`，replay cache 为 `miss`。
- 本机可观察到 `trace-pytest` 容器每次启动不到 1 秒即停止。

结论：

- 容器短时间启动后退出本身不一定异常。当前 Docker executor 使用 `docker run --rm`，pytest 执行完成后容器会自动删除。
- 真正需要判断的是 pytest 在容器退出前是正常跑完、测试失败、collection error，还是 executor failure。
- 初始 0% 的根因不是策略没有捕获 bug，而是 clean baseline 阶段 pytest collection 失败，导致测试集被评为 `invalid_test_set`。

### 10.2 根因：默认 Docker 镜像缺少被测项目依赖

定位证据：

- `exp-real-api` 的 clean/replay 工作目录中，`.trace_pytest_report.json` 和 `.trace_junit.xml` 均显示：

```text
ModuleNotFoundError: No module named 'fastapi'
```

- 生成测试中包含：

```python
from fastapi.testclient import TestClient
```

- Runtime profile 配置为：

```text
executor = docker
image = trace-pytest:3.12
network_policy = disabled
install_command = None
artifact_policy.image_pull_policy = never
```

- 当时 `backend/tests/fixtures/docker/pytest.Dockerfile` 只安装了 pytest：

```dockerfile
FROM python:3.12-slim

RUN pip install --no-cache-dir pytest
```

因此，Docker 容器能够启动，但容器内 Python 环境缺少 FastAPI/httpx/starlette。pytest 在收集测试文件时 import 失败，clean replay 无法形成可评价测试集，前端最终显示 `不可评价` 与 `0%`。

### 10.3 修复：补齐默认 pytest 镜像依赖

已完成修复：

- 更新 `backend/tests/fixtures/docker/pytest.Dockerfile`，默认 `trace-pytest:3.12` 镜像安装 `pytest fastapi httpx`。

当前内容：

```dockerfile
FROM python:3.12-slim

RUN pip install --no-cache-dir pytest fastapi httpx
```

本地重新构建镜像：

```powershell
cd D:\17524\MyCode\Trace
docker build -f backend\tests\fixtures\docker\pytest.Dockerfile -t trace-pytest:3.12 .
```

验证结果：

- 容器内 `pytest`、`fastapi`、`httpx`、`starlette` 均可 import。
- 后端 Docker executor integration 测试通过：

```powershell
python -m pytest --basetemp D:\17524\MyCode\Trace\.pytest_tmp_codex `
  backend/tests/test_executor_runtime_command.py::test_docker_executor_runs_pytest_with_local_docker `
  backend/tests/test_executor_runtime_command.py::test_docker_executor_replays_frozen_tests_clean_and_variant `
  -q -rs
```

结果：

```text
2 passed
```

### 10.4 修复后的第一次复验：环境问题消失，但旧生成测试仍有质量问题

在同一个旧失败目录中手动复跑 Docker pytest 后：

- 不再出现 `No module named 'fastapi'`。
- pytest 能正常 collection 并执行测试。
- 旧测试仍出现 clean 版本断言失败，例如测试了不存在或不符合 demo clean 数据的 `/price/apple`、`/price/laptop`、`/price/widget/`。

这说明修复后问题从“Docker 环境不可运行”变成了“LLM 生成测试质量不稳定”。旧实验的 frozen evidence 不会因镜像修复自动改变，必须重新创建并运行新实验。

### 10.5 最新真实 API 实验评估：工程链路可用，策略质量仍需优化

最新实验：

```text
experiment_id = docker-real-api-2
provider = openai_chat_compat
model = gpt-5.4
dataset = dataset-demo-v2
repeat_count = 1
runtime_profile = Docker pytest 3.12
executor = docker
image = trace-pytest:3.12
network_policy = disabled
```

前端结果：

- Direct v1：捕获率 `100% (6/6)`，状态 `可评价`。
- Plan-and-Execute v1：捕获率 `100% (6/6)`，状态 `可评价`。
- ReAct+Reflection v1：捕获率 `100% (6/6)`，状态 `可评价`。
- replay work 显示 `27 observed / 0 reused`。
- executor summary 显示 `docker: 30`。

后端核对结果：

- 实验状态为 `completed`。
- `ExperimentReplayRun` 为 18 条，即 3 个策略 x 6 个 bug variant。
- `TestReplay` 为 27 条，即每个策略 3 次 clean/flaky replay + 6 次 variant replay，共 3 x 9 = 27。
- 所有 replay 均为 `completed`，`cache_status = miss`，`error_code = None`。
- Docker executor metadata 中记录了 `docker run --rm`、workspace mount、`--network none`、`trace-pytest:3.12`、JUnit/JSON artifact path 等证据。
- replay 不调用 LLM，`llm_calls = 0` 符合契约。

因此，从工程链路看：

- Docker runner 已能被前端 runtime profile 选择并用于真实实验。
- Docker 镜像、workspace mount、pytest plugin、JUnit/JSON report、clean replay、flaky gate、variant replay、metrics 聚合均已跑通。
- 真实大模型 API 生成测试、后端 worker 执行、前端详情展示三者已经完成闭环。

### 10.6 为什么 27 replays 是合理的

该实验选择了 3 个策略，每个策略 repeat 为 1。每个策略对应：

- 1 次 baseline clean replay。
- flaky gate 额外 2 次 clean replay，用于确认 clean 上失败/通过模式是否稳定。
- 6 次 bug variant replay。

所以每个策略产生 9 条 `TestReplay`：

```text
3 clean/flaky replay + 6 variant replay = 9
```

三个策略合计：

```text
3 strategies x 9 replay = 27 TestReplay
```

前端 `27 observed` 是 `TestReplay` 口径；策略矩阵中的 `6/6` 是 `ExperimentReplayRun` 的 bug variant 口径。这两个数字口径不同，但彼此一致。

### 10.7 结果是否合理：可评价但假阳性偏高

最新实验从系统角度是“可评价”的，因为：

- pytest collection 成功率为 100%。
- clean/replay 都有结构化 pytest 报告。
- bug variant replay 都能在 Docker 中执行。
- 每个 variant replay 中都能看到与 seeded bug 对应的 probe/failure，例如：
  - `shipping_fee(5)` 在边界运费变体上失败。
  - `loyalty_points(3)` 在积分边界变体上失败。
  - `clamp_discount_rate(1.5)` 在折扣率 clamp 缺失变体上失败。
  - `/price/unknown` 在错误状态码变体上失败。

但当前结果不适合直接作为“策略质量很高”的结论，因为三个策略的 `false_positive_rate` 均为 `1.0`。含义是：生成测试在 clean 版本上也存在稳定失败。

示例：

- Direct clean replay：`10 collected, 9 passed, 1 failed`。
- ReAct clean replay：`10 collected, 8 passed, 2 failed`。
- 失败主要来自模型臆造了 demo clean 项目不存在的商品或不匹配的路由数据，例如 `/price/laptop`、`/price/apple`。

因此当前结果应这样解读：

- `100% 捕获率`：说明生成测试在 seeded bug replay 上确实触发了失败。
- `100% 假阳性`：说明测试集本身不够干净，clean 项目上也会失败。
- 两者同时存在时，不能直接得出“策略优秀”的结论，只能说明执行链路完整且能产出证据。

### 10.8 当前可用性结论

当前状态：

- Docker 执行容器功能：可用。
- 前端选择 Docker runtime profile：可用。
- 真实大模型 API 端到端实验：可用。
- metrics/replay evidence 展示：可用。
- seeded bug 捕获链路：可用。
- 作为严肃策略对比评测：暂不充分，主要受 clean false positive 影响。

建议验收口径：

```text
A 线执行平台能力：通过。
Docker runner 联调：通过。
真实 API 端到端跑通：通过。
策略效果结论：仅作 smoke/evidence，不作正式横向排名。
```

### 10.9 后续优化建议

优先级较高：

- Prompt/source context 应显式暴露 demo clean 项目的合法商品、路由和业务常量，降低 `/price/apple`、`/price/laptop` 这类臆造测试。
- 在 prompt 中强调：生成测试必须先基于源码可见事实，不得编造不存在的 fixture、商品、路由或状态码。
- metrics 页面应更醒目展示 `false_positive_rate`，当其大于 0 时，应提示“捕获率受 clean baseline failure 污染”。
- 策略对比表可以增加“clean failed / clean total”列，避免用户只看到 `100% (6/6)`。
- 对 `metric_status = ok` 但 `false_positive_rate > 0` 的情况，考虑引入 `warning` 级状态，而不是仅显示 `可评价`。

中期优化：

- 为 demo dataset 提供一个更强的 source context 摘要，包含 `_PRICES = {"book": 30.0, "pen": 2.5}` 等关键事实。
- 在 clean replay 后，对 false positive 节点做自动剔除或单独标记，再计算“净捕获率”。该能力需要谨慎设计，避免掩盖真实策略问题。
- Docker runtime profile UI 增加镜像依赖提示：默认 `trace-pytest:3.12` 适用于当前 demo FastAPI 数据集；真实项目应使用包含项目依赖的镜像或配置 `install_command`。
- 当 `network_policy = disabled` 且 `install_command` 非空时，前端和后端均应提示安装命令无法访问网络，除非依赖来自本地 wheel/cache。

排障建议：

- 若前端显示 `不可评价`，优先查看 clean run 的 `clean_metrics.invalid_reason`。
- 若容器一闪而过，优先查看工作目录中的 `.trace_pytest_report.json` 和 `.trace_junit.xml`。
- 若出现 `ModuleNotFoundError`，检查 Docker image 是否包含被测项目依赖。
- 若出现 `collection_errors > 0`，不要将其解释为 0 捕获，应归类为测试集不可评价。
- 若出现 `false_positive_rate > 0`，说明测试集在 clean 版本上失败，需要优化 prompt/source context 或测试过滤口径。
