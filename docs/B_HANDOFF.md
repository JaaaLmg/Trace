# TRACE B 线对接清单

> 面向后续继续迭代 B 线的同学，以及需要接入 B 线 API 的 C 线前端。  
> 当前 B 线负责范围：PostgreSQL 持久化、FastAPI 管理 API、Celery + Redis 异步执行、A 线 Agent 的后端封装与查询能力。

## 当前状态

- B 线 V1 已经完成数据库层、核心 API、异步执行主链路。
- PostgreSQL `trace` 库已验证可用，14 张 V1 表已建立。
- Redis 已接通，Celery worker 可以真实消费 `POST /runs` 提交的任务。
- A 线 `execute_run(...)` 已通过 `SQLAlchemyRunRecorder` 接入数据库落库。
- 当前已验证真实异步 smoke：`queued -> completed`，并成功写入：
  - `test_runs`
  - `run_plan_items`
  - `run_attempts`
  - `trace_steps`
  - `run_events`
  - `generated_test_files`
  - `generated_test_cases`
  - `pytest_case_results`
  - `run_artifacts`
  - `test_reports`

## B 线已经接住了什么

### 1. 接住了 A 线的执行入口

B 线真正调用 A 线的入口仍然是：

```python
from app.agents.orchestrator import execute_run
```

B 没有重写 Agent，只是在 [backend/app/services/test_runs.py](/D:/17524/MyCode/Trace/backend/app/services/test_runs.py) 里补齐了：

- run 创建
- strategy/snapshot/project 回库查询
- `ToolContext` 构造
- `SQLAlchemyRunRecorder` 注入
- artifacts 目录管理
- Celery 异步调度

也就是说，A 线仍负责：

- 策略循环
- 工具调用顺序
- trace/report 生产
- reflection 约束

B 线负责：

- 生命周期管理
- 数据库存储
- API 暴露
- 后台执行

### 2. 接住了 A 线的 recorder 端口

核心适配文件：

- [backend/app/recorders/sqlalchemy_recorder.py](/D:/17524/MyCode/Trace/backend/app/recorders/sqlalchemy_recorder.py)

它实现了 A 线 `RunRecorder` 协议里的所有关键方法，包括：

- `save_run`
- `add_run_event`
- `add_trace_step`
- `add_plan_item`
- `save_plan_item`
- `add_attempt`
- `save_attempt`
- `add_generated_file`
- `add_generated_cases`
- `add_pytest_results`
- `add_artifact`
- `save_report`

当前策略是：

- `save_*` 做 upsert/update
- `add_*` 做 append/insert
- 默认每次写入立即 commit，优先保证调试和联调时数据可见

## B 线的数据模型

### V1 已建 14 张表

对应模型文件：

- [backend/app/models/project.py](/D:/17524/MyCode/Trace/backend/app/models/project.py)
- [backend/app/models/strategy.py](/D:/17524/MyCode/Trace/backend/app/models/strategy.py)
- [backend/app/models/test_plan.py](/D:/17524/MyCode/Trace/backend/app/models/test_plan.py)
- [backend/app/models/test_run.py](/D:/17524/MyCode/Trace/backend/app/models/test_run.py)
- [backend/app/models/artifacts.py](/D:/17524/MyCode/Trace/backend/app/models/artifacts.py)
- [backend/app/models/trace.py](/D:/17524/MyCode/Trace/backend/app/models/trace.py)

14 张表如下：

```text
projects
project_snapshots
strategy_versions
test_plans
test_runs
run_plan_items
run_attempts
generated_test_files
generated_test_cases
pytest_case_results
trace_steps
run_events
run_artifacts
test_reports
```

### 关键约束

- `test_runs.project_snapshot_id` 非空
- `test_runs.strategy_version_id` 非空
- `test_runs.runtime_profile_id` 可空
- `run_plan_items` 在同一 run 内 `index` 唯一
- `run_attempts` 在同一计划项内 `(run_plan_item_id, attempt_no)` 唯一
- `trace_steps` 在同一 run 内 `step_index` 唯一
- `test_reports.run_id` 唯一

## B 线提供给 C 线的 API 子集

### 项目与快照

```text
POST /api/v1/projects
GET  /api/v1/projects
GET  /api/v1/projects/{project_id}
POST /api/v1/projects/{project_id}/snapshots
GET  /api/v1/projects/{project_id}/snapshots
```

### 测试计划

```text
POST /api/v1/test-plans
GET  /api/v1/test-plans/{plan_id}
```

### 运行控制

```text
POST /api/v1/test-plans/{plan_id}/runs
GET  /api/v1/test-runs/{run_id}
POST /api/v1/test-runs/{run_id}/cancel
POST /api/v1/test-runs/{run_id}/retry
```

### 运行查询

```text
GET /api/v1/test-runs/{run_id}/trace-steps
GET /api/v1/test-runs/{run_id}/events
GET /api/v1/test-runs/{run_id}/attempts
GET /api/v1/test-runs/{run_id}/pytest-results
GET /api/v1/test-runs/{run_id}/artifacts
GET /api/v1/test-runs/{run_id}/report
```

### 策略与人工采纳

```text
GET   /api/v1/strategy-versions
GET   /api/v1/strategy-versions/{version_id}
PATCH /api/v1/generated-test-cases/{case_id}/adoption
```

关键路由文件：

- [backend/app/api/routes/projects.py](/D:/17524/MyCode/Trace/backend/app/api/routes/projects.py)
- [backend/app/api/routes/test_plans.py](/D:/17524/MyCode/Trace/backend/app/api/routes/test_plans.py)
- [backend/app/api/routes/test_runs.py](/D:/17524/MyCode/Trace/backend/app/api/routes/test_runs.py)
- [backend/app/api/routes/strategy_versions.py](/D:/17524/MyCode/Trace/backend/app/api/routes/strategy_versions.py)

## 当前后端逻辑链条

这是 B 线最核心的一段，建议后续所有人都先按这条链路理解系统。

### 1. 创建项目

用户先创建 `projects` 记录，告诉系统：

- 这是哪个被测项目
- 本地代码根目录在哪里

### 2. 创建快照

然后创建 `project_snapshots`。

V1 里快照不是真正 copy 一份代码，而是：

- 固化一次 `root_path`
- 让 run 不直接依赖“当前项目路径”这种隐式状态

### 3. 创建测试计划

测试计划 `test_plans` 保存的是：

- 要测什么
- 预算如何限制
- 默认采用哪个策略

它是“执行模板”，不是一次执行本身。

### 4. 创建 run

当前入口：

- `POST /api/v1/test-plans/{plan_id}/runs`

这一步在 [backend/app/services/test_runs.py](/D:/17524/MyCode/Trace/backend/app/services/test_runs.py) 的 `create_run(...)` 中完成，主要做：

- 校验 plan 是否存在
- 校验 snapshot 是否存在
- 解析最终 strategy_version_id
- 创建一条 `status=queued` 的 `test_runs` 记录

### 5. run 入队

随后 `enqueue_run(...)` 会：

- 追加一条 `run_enqueued` 到 `run_events`
- 调用 Celery 任务 `trace.execute_run`

此时 API 可以快速返回，不阻塞 HTTP 请求。

### 6. worker 消费任务

Celery 相关文件：

- [backend/app/workers/celery_app.py](/D:/17524/MyCode/Trace/backend/app/workers/celery_app.py)
- [backend/app/workers/tasks.py](/D:/17524/MyCode/Trace/backend/app/workers/tasks.py)

worker 从 Redis 队列 `trace_test_runs` 拉到任务后，会执行：

```python
execute_run_sync(session, run_id=..., budget_override=...)
```

### 7. execute_run_sync 组装 A 线运行上下文

`execute_run_sync(...)` 是 B 线真正的“运行装配器”。

它会：

1. 回库查 `test_runs`
2. 回库查 `test_plans`
3. 回库查 `project_snapshots`
4. 回库查 `strategy_versions`
5. 回库查 `projects`
6. 构造 `ToolContext`
7. 创建 `tests/generated/`
8. 创建 `SQLAlchemyRunRecorder`
9. 组装 `StrategyVersionSpec`
10. 计算预算覆盖
11. 调用 A 线 `execute_run(...)`

### 8. Agent 执行过程中持续落库

A 线每推进一步，都会通过 recorder 回写数据库。

大致顺序是：

1. 更新 `test_runs`
2. 写 `run_events`
3. 写 `trace_steps`
4. 写 `run_plan_items`
5. 写 `run_attempts`
6. 写 `generated_test_files`
7. 写 `generated_test_cases`
8. 写 `pytest_case_results`
9. 写 `run_artifacts`
10. 写 `test_reports`

### 9. 前端/调用方查询结果

C 线或调试者随后通过查询接口读取：

- run 主状态
- trace 时间线
- 事件流
- attempt 列表
- pytest 用例结果
- 报告摘要
- 报告文件地址

## B 线当前运行模式

### 当前是本地执行模式

当前运行依赖：

- PostgreSQL
- Redis
- 本地 Python
- 本地项目路径

当前不是：

- Docker 隔离执行
- 远程 runner
- 安全沙箱

这点在对外描述时一定要谨慎。

### 当前默认还是 MockLLM

虽然 A 线已经有真实 LLM adapter，但 B 线 `execute_run_sync(...)` 里当前还是：

- `_mock_llm()`

也就是说，B 线的后端链路已经通了，但“通过 API 驱动真实模型跑 Agent”这一步还没正式接上配置层。

## 当前可直接使用的本地脚本

### 启动 API

- [backend/scripts/run_api.py](/D:/17524/MyCode/Trace/backend/scripts/run_api.py)

```powershell
cd backend
python scripts/run_api.py
```

### 启动 worker

- [backend/scripts/run_worker.py](/D:/17524/MyCode/Trace/backend/scripts/run_worker.py)

```powershell
cd backend
python scripts/run_worker.py
```

Windows 下当前 worker 强制使用 `--pool=solo`，这是为了提升本地稳定性。

### 同时拉起开发服务

- [backend/scripts/spawn_dev_services.py](/D:/17524/MyCode/Trace/backend/scripts/spawn_dev_services.py)

### 做一次真实异步 smoke

- [backend/scripts/smoke_async_run.py](/D:/17524/MyCode/Trace/backend/scripts/smoke_async_run.py)

这个脚本会自动：

1. 创建项目
2. 创建 snapshot
3. 创建 test plan
4. 触发 `POST /runs`
5. 轮询直到 run 完成
6. 读取 events 和 report

## 当前已知边界

- `cancel` 只是软取消，不会终止已启动的子进程。
- API 目前很多地方直接返回 ORM 对象，response schema 还不够干净。
- `execute_run_sync(...)` 当前默认走 MockLLM。
- `runtime_profile_id` 还只是预留，没有真正的 runtime profile 模型。
- `project_snapshots` 当前是路径快照，不是代码内容拷贝。

## 后续建议优先级

### 优先级 1

- 给 API 增加显式 response schema
- 把真实 LLM 的配置接入到 B 线执行链路
- 梳理 session/事务边界，减少 recorder 每步提交的粗粒度开销

### 优先级 2

- 增强 `cancel`，支持尽量终止运行中的任务
- 把 report/query 聚合逻辑进一步下沉到 repository/service
- 验证一轮干净数据库上的 `alembic upgrade head`

### 优先级 3

- 考虑 runner 抽象
- 考虑远程执行
- 考虑更强的执行隔离与安全沙箱

## 对接验收标准

### B 自己的第一轮验收

- 能创建 project
- 能创建 snapshot
- 能创建 test plan
- 能通过 API 触发 run
- run 能入队并被 worker 消费
- run 完成后能查到 trace / events / attempts / pytest-results / report

### 给 C 的验收口径

C 线接入时，至少应能展示：

- run 基本状态
- trace timeline
- pytest result 列表
- report 摘要和链接
- strategy 信息

## 文件索引

- [backend/app/services/test_runs.py](/D:/17524/MyCode/Trace/backend/app/services/test_runs.py)：B 线运行编排核心
- [backend/app/recorders/sqlalchemy_recorder.py](/D:/17524/MyCode/Trace/backend/app/recorders/sqlalchemy_recorder.py)：A/B 适配核心
- [backend/app/workers/tasks.py](/D:/17524/MyCode/Trace/backend/app/workers/tasks.py)：Celery 消费入口
- [backend/app/api/routes/test_runs.py](/D:/17524/MyCode/Trace/backend/app/api/routes/test_runs.py)：run 控制与查询 API
- [backend/app/models/](/D:/17524/MyCode/Trace/backend/app/models)：14 张 V1 表定义
- [backend/scripts/smoke_async_run.py](/D:/17524/MyCode/Trace/backend/scripts/smoke_async_run.py)：真实异步链路 smoke 验证脚本
