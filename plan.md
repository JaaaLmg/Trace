# TRACE 角色 B V1 实施计划

## 1. 目标与范围

本计划面向 TRACE 的角色 B，也就是后端/平台工程部分的 V1 落地。目标不是重写 A 线 Agent，而是在现有 A 线可运行内核之上，补齐：

- PostgreSQL 持久化；
- SQLAlchemy + Alembic 数据层；
- FastAPI 管理 API；
- Redis 队列/异步编排；
- 基于 `RunRecorder` 的数据库落库；
- 运行状态机与查询接口；
- V1 口径下的本地执行器接入与产物保存。

严格遵循：

- [系统设计.md](D:\17524\MyCode\Trace\docs\系统设计.md)
- [V1实施清单.md](D:\17524\MyCode\Trace\docs\V1实施清单.md)

本次只做 V1：

- 不做 Docker / 远程 Runner；
- 不做评测表；
- 不做 prompt/tool schema 版本表；
- 不做多 Runner 调度；
- 不做前端；
- 不改变 A 线的工具契约和 Agent 闭环语义。

---

## 2. 当前仓库现状与 B 线缺口

### 2.1 已有能力

当前仓库已经具备：

- A 线 Agent 核心闭环；
- 三种策略 `direct / plan_execute / react_reflection`；
- 结构化工具契约；
- `RunRecorder` 持久化协议；
- `InMemoryRecorder` 内存实现；
- pytest 结构化执行与 trace/report；
- MockLLM 与真实 LLM adapter；
- 脚本式 seeded bug 评测。

### 2.2 当前缺失

当前 B 线要补的核心缺口是：

- 没有 `app/api/`；
- 没有 `app/db/`；
- 没有 `app/models/`；
- 没有真正的 SQLAlchemy 持久化；
- 没有 Alembic 迁移；
- 没有项目/快照/计划/run 的数据库表；
- 没有运行查询 API；
- 没有 Redis 队列与后台执行；
- 没有正式的配置管理；
- 没有 API 启动入口。

因此，B 线的本质任务是：**把 A 线“内存运行的 Agent 内核”封装成一个可管理、可查询、可重试的后端系统。**

---

## 3. 设计原则

### 3.1 不破坏 A 线边界

优先复用 A 线已经稳定的接口，不改它们的语义：

- `execute_run(...)`
- `RunRecorder`
- `ToolContext`
- `PlanInput`
- `StrategyVersionSpec`
- `schemas.records`
- `schemas.trace`

### 3.2 先打通闭环，再逐步异步化

建议采用“两段式落地”：

1. 第一阶段先实现数据库与 API，并允许“同步执行 run”以打通端到端。
2. 第二阶段再接 Redis + RQ/Celery，把 `POST /runs` 改为后台异步执行。

这样可以尽快完成最小闭环，降低一次性引入过多复杂度的风险。

### 3.3 记录先于状态

严格沿用系统设计文档要求：

1. 先写 `run_events` / `trace_steps`；
2. 再写结构化结果；
3. 再更新 run/attempt 状态。

### 3.4 数据形状以现有 Pydantic record 为主

数据库模型要尽量与：

- [backend/app/schemas/records.py](D:\17524\MyCode\Trace\backend\app\schemas\records.py)
- [backend/app/schemas/trace.py](D:\17524\MyCode\Trace\backend\app\schemas\trace.py)

保持一一对应，降低 A/B 集成摩擦。

---

## 4. 目标代码架构

建议在 `backend/app/` 下新增如下分层：

```text
backend/app/
  api/
    __init__.py
    deps.py
    router.py
    routes/
      projects.py
      test_plans.py
      test_runs.py
      strategy_versions.py
  db/
    __init__.py
    base.py
    session.py
    settings.py
  models/
    __init__.py
    project.py
    strategy.py
    test_plan.py
    test_run.py
    trace.py
    artifacts.py
  repositories/
    __init__.py
    projects.py
    strategies.py
    test_plans.py
    test_runs.py
    traces.py
  services/
    __init__.py
    projects.py
    snapshots.py
    test_plans.py
    test_runs.py
    reports.py
  workers/
    __init__.py
    queue.py
    tasks.py
  recorders/
    __init__.py
    sqlalchemy_recorder.py
  schemas/
    api_project.py
    api_plan.py
    api_run.py
  main.py
```

### 4.1 各层职责

#### `api/`

作用：

- 暴露 HTTP 接口；
- 做请求/响应 schema 校验；
- 只负责资源管理与查询，不直接写复杂业务。

#### `db/`

作用：

- 管理数据库配置；
- 提供 SQLAlchemy `Base`、engine、session；
- 统一事务边界。

#### `models/`

作用：

- 定义 14 张 V1 表；
- 体现数据库外键、索引、约束；
- 是 Alembic 迁移的基础。

#### `repositories/`

作用：

- 封装数据库 CRUD；
- 避免把 ORM 查询散落到 API 和 service 中。

#### `services/`

作用：

- 承担业务规则；
- 例如创建项目快照、创建 run、重试 run、取消 run、组装查询结果。

#### `workers/`

作用：

- 管理 Redis 队列与后台任务；
- 异步执行 `execute_run(...)`；
- 保持 API 与执行平面解耦。

#### `recorders/`

作用：

- 提供 SQLAlchemy 版本 `RunRecorder`；
- 把 A 线输出的 record 落到 14 张表。

#### `schemas/api_*`

作用：

- 只负责 API 层请求/响应对象；
- 与 `schemas.records` 分工明确：
  - `records` 给 Agent 内核；
  - `api_*` 给 HTTP 接口。

---

## 5. 数据库架构设计

V1 必建 14 张表，按 `V1实施清单.md` 执行。

---

## 6. 表设计总览

### 6.1 `projects`

用途：

- 记录被测项目元数据。

建议字段：

- `id` `uuid / string`
- `name`
- `description`
- `source_type`，V1 固定为 `local_path`
- `repo_url` nullable
- `local_path`
- `default_branch` nullable
- `language` 默认 `python`
- `framework` 默认 `fastapi`
- `status` 默认 `active`
- `created_at`
- `updated_at`

建议索引：

- `idx_projects_name`

### 6.2 `project_snapshots`

用途：

- 记录某次运行绑定的代码根。

V1 最简字段：

- `id`
- `project_id` FK -> `projects.id`
- `source_kind`
- `root_path`
- `content_hash` nullable
- `created_at`

建议索引：

- `idx_project_snapshots_project_id`

### 6.3 `strategy_versions`

用途：

- 保存三种策略版本身份。

V1 字段：

- `id`
- `name`
- `workflow_type`
- `model_provider`
- `model_name`
- `model_params` JSON
- `allow_reflection`
- `max_tool_calls`
- `prompt_ref`
- `tool_schema_ref`
- `created_at`

备注：

- 这张表在 V1 是只读种子表；
- 数据应与 [backend/app/agents/seeds.py](D:\17524\MyCode\Trace\backend\app\agents\seeds.py) 保持一致。

### 6.4 `test_plans`

用途：

- 保存用户定义的测试目标。

建议字段：

- `id`
- `project_id` FK
- `name`
- `target_scope` JSON
- `goal`
- `budget` JSON
- `output_options` JSON
- `default_strategy_version_id` FK -> `strategy_versions.id`
- `status`
- `created_at`
- `updated_at`

建议 `budget` 示例：

```json
{
  "max_tool_calls": 12,
  "timeout_seconds": 300,
  "allow_reflection": true
}
```

### 6.5 `test_runs`

用途：

- 一次实际运行的核心主表。

建议字段：

- `id`
- `test_plan_id` FK
- `retry_of_run_id` nullable self FK
- `project_snapshot_id` NOT NULL FK
- `runtime_profile_id` nullable
- `strategy_version_id` NOT NULL FK
- `runtime_snapshot` JSON
- `strategy_snapshot` JSON
- `status`
- `stage` nullable
- `started_at`
- `finished_at`
- `total_tokens`
- `total_cost` nullable numeric
- `tool_call_count`
- `pytest_summary` JSON
- `error_code`
- `error_message`
- `created_at`

关键约束：

- `project_snapshot_id` NOT NULL
- `strategy_version_id` NOT NULL
- `runtime_profile_id` nullable

### 6.6 `run_plan_items`

用途：

- 某次运行拆出的计划项。

字段：

- `id`
- `run_id` FK
- `index`
- `target_type`
- `target_ref`
- `goal`
- `planned_assertions` JSON
- `status`

建议约束：

- 同一 run 内 `index` 唯一

### 6.7 `run_attempts`

用途：

- 某个 plan item 的一次生成与执行尝试。

字段：

- `id`
- `run_plan_item_id` FK
- `attempt_no`
- `kind` (`initial` / `reflection`)
- `status`
- `started_at` nullable
- `finished_at` nullable
- `pytest_exit_code`
- `error_code`
- `reflection_reason`

建议约束：

- `(run_plan_item_id, attempt_no)` 唯一

### 6.8 `generated_test_files`

用途：

- 保存生成或修复后的测试文件版本。

字段：

- `id`
- `attempt_id` FK
- `path`
- `content_text`
- `content_hash`
- `artifact_id` nullable
- `previous_file_id` nullable self FK
- `diff_artifact_id` nullable
- `generation_reason`
- `created_at`

### 6.9 `generated_test_cases`

用途：

- 存 AST 解析出来的用例逻辑单元。

字段：

- `id`
- `file_id` FK
- `nodeid` nullable
- `test_name`
- `start_line`
- `end_line`
- `target_route` nullable
- `target_function` nullable
- `assertion_summary` nullable
- `source_strategy_version_id` nullable
- `adoption_status`
- `human_meaningfulness_score` nullable
- `rule_flags` JSON

### 6.10 `pytest_case_results`

用途：

- 保存 pytest 单用例结果。

字段：

- `id`
- `attempt_id` FK
- `generated_test_case_id` nullable FK
- `nodeid`
- `mapping_status`
- `status`
- `duration_ms`
- `failure_type`
- `failure_message`
- `traceback_hash`
- `stdout_excerpt` nullable
- `stderr_excerpt` nullable
- `is_collection_error` boolean

建议索引：

- `idx_pytest_case_results_attempt_id`
- `idx_pytest_case_results_nodeid`

### 6.11 `trace_steps`

用途：

- 保存 Agent 和系统的过程轨迹。

字段：

- `id`
- `run_id` FK
- `attempt_id` nullable FK
- `step_index`
- `step_type`
- `name`
- `input_summary`
- `output_summary`
- `tool_name`
- `payload` JSON
- `tokens` nullable
- `duration_ms` nullable
- `status`
- `error`
- `created_at`

建议约束：

- `(run_id, step_index)` 唯一

### 6.12 `run_events`

用途：

- 记录状态机事件。

字段：

- `id`
- `run_id` FK
- `stage`
- `event_type`
- `status_before`
- `status_after`
- `message`
- `created_at`

### 6.13 `run_artifacts`

用途：

- 保存大文件产物元数据。

字段：

- `id`
- `run_id` FK
- `attempt_id` nullable FK
- `runner_job_id` nullable
- `artifact_type`
- `uri`
- `content_hash`
- `size_bytes`
- `metadata` JSON
- `created_at`

V1 里 `uri` 就存本地路径。

### 6.14 `test_reports`

用途：

- 保存最终报告摘要和链接。

字段：

- `id`
- `run_id` FK unique
- `summary`
- `metrics` JSON
- `risk_notes`
- `markdown_artifact_id` nullable
- `json_artifact_id` nullable
- `markdown_uri` nullable
- `json_uri` nullable
- `created_at`

备注：

- A 线当前 `TestReportRecord` 用的是 `markdown_uri/json_uri`；
- 为减少改动，V1 可以先直接存 URI 字段；
- `markdown_artifact_id/json_artifact_id` 可以先 nullable。

---

## 7. SQLAlchemy 模型设计策略

### 7.1 ORM 与 record 的映射

建议策略：

- ORM 层用 SQLAlchemy model；
- Agent 层继续使用现有 Pydantic record；
- `SQLAlchemyRunRecorder` 负责把 record 转成 ORM 插入/更新。

这样可以最大限度保持 A 线代码不变。

### 7.2 JSON 字段

以下字段建议用 PostgreSQL `JSONB`：

- `test_plans.target_scope`
- `test_plans.budget`
- `test_plans.output_options`
- `strategy_versions.model_params`
- `test_runs.runtime_snapshot`
- `test_runs.strategy_snapshot`
- `test_runs.pytest_summary`
- `generated_test_cases.rule_flags`
- `trace_steps.payload`
- `run_artifacts.metadata`
- `test_reports.metrics`

### 7.3 时间字段

统一使用：

- `TIMESTAMP WITH TIME ZONE`

与 A 线 `datetime.now(timezone.utc).isoformat()` 保持一致。

---

## 8. `RunRecorder` 的数据库实现计划

新增：

- [backend/app/recorders/sqlalchemy_recorder.py](D:\17524\MyCode\Trace\backend\app\recorders\sqlalchemy_recorder.py)

实现接口：

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

### 8.1 实现原则

- `save_*` 做 upsert/update；
- `add_*` 做 append/insert；
- 不在 recorder 内部偷改状态机；
- 事务边界交给 service 或 worker 控制；
- 遇到唯一键冲突时优先按幂等更新。

### 8.2 额外建议

为了便于 report 查询，补一些 repository 查询方法：

- `list_steps_by_run(run_id)`
- `list_events_by_run(run_id)`
- `list_attempts_by_run(run_id)`
- `list_pytest_results_by_run(run_id)`
- `get_report_by_run(run_id)`

---

## 9. API 架构设计

V1 只实现 `V1实施清单.md` 里要求的子集。

### 9.1 `projects` API

实现：

- `POST /api/v1/projects`
- `GET /api/v1/projects`
- `GET /api/v1/projects/{project_id}`
- `POST /api/v1/projects/{project_id}/snapshots`
- `GET /api/v1/projects/{project_id}/snapshots`

请求建议：

- 创建项目时提供 `name/local_path/description`
- 创建 snapshot 时默认从 `project.local_path` 生成 `root_path`

### 9.2 `test_plans` API

实现：

- `POST /api/v1/test-plans`
- `GET /api/v1/test-plans/{plan_id}`

### 9.3 `test_runs` API

实现：

- `POST /api/v1/test-plans/{plan_id}/runs`
- `GET /api/v1/test-runs/{run_id}`
- `POST /api/v1/test-runs/{run_id}/cancel`
- `POST /api/v1/test-runs/{run_id}/retry`

### 9.4 查询 API

实现：

- `GET /api/v1/test-runs/{run_id}/trace-steps`
- `GET /api/v1/test-runs/{run_id}/events`
- `GET /api/v1/test-runs/{run_id}/attempts`
- `GET /api/v1/test-runs/{run_id}/pytest-results`
- `GET /api/v1/test-runs/{run_id}/artifacts`
- `GET /api/v1/test-runs/{run_id}/report`

### 9.5 策略 API

实现：

- `GET /api/v1/strategy-versions/{version_id}`

可选补充：

- `GET /api/v1/strategy-versions`

虽然清单里没强制，但前端做下拉选择会更方便。

### 9.6 adoption API

实现：

- `PATCH /api/v1/generated-test-cases/{case_id}/adoption`

用途：

- 更新 `adoption_status`
- 可选附带 `human_meaningfulness_score`

---

## 10. 运行编排设计

### 10.1 推荐分层

建议新增 `TestRunService`，职责如下：

- 校验 `plan_id / snapshot_id / strategy_version_id`
- 合成 run 级 `runtime_snapshot` 和 `strategy_snapshot`
- 创建 `test_runs` 初始记录
- 选择同步执行或投递异步任务

### 10.2 执行路径

#### 同步模式（第一阶段）

API 创建 run 后，直接调用：

```python
execute_run(...)
```

优点：

- 便于先打通。

缺点：

- API 阻塞。

#### 异步模式（第二阶段）

API 创建 run 后，把 `run_id` 投递到 Redis 队列，由 worker 拉起执行。

worker 内部再做：

- 加载 run、plan、snapshot、strategy
- 创建 `ToolContext`
- 创建 `SQLAlchemyRunRecorder`
- 调用 `execute_run(...)`

这是更符合文档设计的 V1 形态。

### 10.3 取消与重试

#### 取消

V1 第一版建议：

- 只支持把尚未开始执行的 `queued/running` run 标记为 `cancelled`
- 如后台任务已进入 subprocess，可先做软取消标记

第二阶段再考虑进程级终止。

#### 重试

必须严格按文档：

- 创建新的 `test_runs`
- 新 run 的 `retry_of_run_id` 指向旧 run
- 不能在旧 run 下追加 attempt

---

## 11. Redis 与队列设计

### 11.1 选型建议

V1 推荐优先用 `celery`，原因：

团队已经更熟 Celery。

### 11.2 队列结构

建议：

- 队列名：`trace:test-runs`
- payload：只传 `run_id`

worker 拿到 `run_id` 后再去 DB 查询上下文，避免队列里塞大对象。

### 11.3 任务函数

建议新增：

- `workers/tasks.py::execute_test_run_task(run_id: str)`

职责：

- 打开 DB session
- 读取 run 及相关实体
- 构造 `ToolContext`
- 调用 `execute_run(...)`
- 捕获异常并写 `run_events` 与 `failed` 状态

---

## 12. 执行器与工作目录方案

虽然 A 线已有 `LocalSubprocessExecutor`，B 线仍应补足运行环境管理层。

### 12.1 V1 建议

短期先复用 A 线执行器，不马上改 `run_pytest` 契约。

### 12.2 可以新增的 B 线包装

建议新增一个轻量运行上下文服务，例如：

- `services/test_runs.py::build_tool_context(snapshot, run_id)`

职责：

- 读取 snapshot 的 `root_path`
- 为该 run 生成独立 artifacts 目录
- 确保 `tests/generated` 存在
- 构造 `ToolContext`

### 12.3 产物目录建议

建议统一落到：

```text
backend/artifacts/{run_id}/
```

其中包含：

- `report.md`
- `report.json`
- 未来可扩展的 junit / copied test files

---

## 13. 配置管理设计

建议新增配置层：

- `db/settings.py`

核心配置：

- `TRACE_DB_URL`
- `TRACE_REDIS_URL`
- `TRACE_ARTIFACTS_DIR`
- `TRACE_API_HOST`
- `TRACE_API_PORT`
- `TRACE_SYNC_RUNS`（阶段一可选）

推荐本地默认：

```text
TRACE_DB_URL=postgresql+psycopg://postgres:密码@127.0.0.1:5432/trace
TRACE_REDIS_URL=redis://127.0.0.1:6379/0
TRACE_ARTIFACTS_DIR=backend/artifacts
```

---

## 14. Python 依赖补充计划

当前 [backend/requirements.txt](D:\17524\MyCode\Trace\backend\requirements.txt) 还不够支撑 B 线。

建议新增：

- `sqlalchemy`
- `alembic`
- `psycopg[binary]` 或 `psycopg2-binary`
- `redis`
- `rq`
- `uvicorn`
- 可选：`python-dotenv`

如坚持 Celery，则改为：

- `celery`
- `redis`

但不建议同时上 `rq` 和 `celery`。

---

## 15. Alembic 迁移计划

### 15.1 初始化

建议在 `backend/` 下初始化 Alembic。

目标：

- `backend/alembic.ini`
- `backend/alembic/`
- `backend/alembic/versions/`

### 15.2 首个迁移

第一版迁移只做 14 张表。

### 15.3 种子数据迁移

建议单独做策略种子初始化：

- 方案 A：Alembic migration 插入 3 条 `strategy_versions`
- 方案 B：独立 `seed_strategies.py`

推荐：

- 开发阶段用 `seed_strategies.py`
- 避免频繁改 migration

---

## 16. 实施阶段拆分

### 阶段 0：基础准备

- 增加依赖
- 增加 `db/`
- 增加配置层
- 初始化 Alembic

交付物：

- engine/session
- `Base`
- 迁移骨架

### 阶段 1：建模与迁移

- 建 14 张表 ORM
- 生成首个 Alembic migration
- 写种子脚本插入 3 条策略

交付物：

- 可创建数据库 schema
- 可初始化策略数据

### 阶段 2：持久化适配

- 实现 `SQLAlchemyRunRecorder`
- 实现 repositories
- 让 Agent 输出可真正落库

交付物：

- 内存 recorder -> SQLAlchemy recorder 替换成功

### 阶段 3：核心 API

- 项目 API
- snapshot API
- test plan API
- run 创建/查询 API
- trace/report 查询 API

交付物：

- FastAPI 可启动
- 可通过 API 创建 run 并查询结果

### 阶段 4：同步闭环打通

- 先用同步执行把 `POST /runs` 跑通
- 确认 DB 能完整记录：
  - run
  - steps
  - events
  - attempts
  - pytest results
  - report

交付物：

- 真正的 DB 版端到端闭环

### 阶段 5：Redis 异步化

- 接入 Celery + Redis
- API 创建 run 改为入队
- worker 执行 `execute_run(...)`

交付物：

- API 非阻塞
- worker 独立执行 run

### 阶段 6：取消/重试与收尾

- `cancel`
- `retry`
- adoption patch
- 文档与脚本完善

---

## 17. 推荐的具体开发顺序

建议按下面顺序逐步实现：

1. 建 `db/`、`models/`、`main.py`
2. 加依赖并初始化 Alembic
3. 先完成 14 张表和 migration
4. 完成 `SQLAlchemyRunRecorder`
5. 写策略种子脚本
6. 写 project / snapshot / plan / strategy 查询 API
7. 写 `POST /runs` 同步版本
8. 跑通一次 DB 版 `execute_run(...)`
9. 再补 trace/report/attempt/result 查询 API
10. 最后接 Redis + worker

---

## 18. 环境与外部工具检查结果

我已经在当前环境里做了实际检查。

### 18.1 PostgreSQL

检查结果：

- `psql` 存在：`D:\PostgreSQL\18\bin\psql.exe`
- `pg_isready` 返回：`127.0.0.1:5432 - accepting connections`
- 说明 PostgreSQL 服务正在监听并接受连接

当前仍有一个未确认项：

- **数据库认证信息没有在当前 shell 配置，所以我没有实际完成一次登录查询**

我执行到的结论是：

- TCP 层可连
- PostgreSQL 进程在工作
- 但当前没有 `PGPASSWORD`，因此尚未验证用户名/密码是否正确

你可以用下面命令自行验证：

```powershell
$env:PGPASSWORD="你的密码"
& "D:\PostgreSQL\18\bin\psql.exe" -h 127.0.0.1 -p 5432 -U postgres -d postgres -w -c "select version();"
```

如果想为 TRACE 单独建库，建议：

```powershell
$env:PGPASSWORD="你的密码"
& "D:\PostgreSQL\18\bin\psql.exe" -h 127.0.0.1 -p 5432 -U postgres -d postgres -w -c "create database trace;"
```

### 18.2 Redis

检查结果：

- `127.0.0.1:6379` 端口可连
- 原始协议 `PING` 返回 `+PONG`

这说明：

- Redis 当前是可访问、可工作的

额外说明：

- 当前 shell 里 `redis-cli` 不在 PATH
- 但 Redis 服务本身是好的

如果你想自己验证，并且知道 `redis-cli.exe` 的路径，可以执行：

```powershell
& "你的redis-cli路径\redis-cli.exe" -h 127.0.0.1 -p 6379 ping
```

期望输出：

```text
PONG
```

---

## 19. 还需要哪些外部开发软件

### 19.1 必需

目前从 B 线 V1 来看，必需的软件已经基本具备：

- Python 3.12
- PostgreSQL
- Redis

还需要的是 Python 依赖，而不是额外大型软件。

### 19.2 强烈建议补充

为了开发体验更好，建议补充：

- `redis-cli`
  作用：调试 Redis 队列和连接更方便
- `pgAdmin` 或者任意 PostgreSQL GUI
  作用：看表、看数据、看迁移结果更直观

### 19.3 可选

- `Redis Insight`
  作用：可视化查看 Redis key/queue

### 19.4 当前不需要

以下内容不是 B 线 V1 的必需前置：

- Docker Desktop
- MinIO
- 消息中间件以外的额外服务
- 远程 Runner 工具

---

## 20. 当前实施状态（2026-06-12）

截至 2026-06-12，本计划的实际落地状态如下：

### 已完成

- 阶段 0：基础准备
- 阶段 1：建模与迁移
- 阶段 2：持久化适配
- 阶段 3：核心 API
- 阶段 4：同步闭环打通
- 阶段 5：Celery + Redis 异步化
- 阶段 6 的基础收尾：
  - `cancel`
  - `retry`
  - adoption patch
  - 本地启动脚本
  - Alembic baseline
  - 真实异步 smoke 验证

### 已完成的关键交付物

- `backend/app/db/`
- `backend/app/models/`
- `backend/app/repositories/`
- `backend/app/services/`
- `backend/app/api/`
- `backend/app/workers/`
- `backend/app/recorders/sqlalchemy_recorder.py`
- `backend/alembic/`
- `backend/sql/init_v1.sql`
- `backend/scripts/run_api.py`
- `backend/scripts/run_worker.py`
- `backend/scripts/seed_strategies.py`
- `backend/scripts/spawn_dev_services.py`
- `backend/scripts/smoke_async_run.py`

### 当前仍建议继续推进的方向

1. 给 API 增加显式 response schema，避免直接暴露 ORM 对象。
2. 把 report 聚合和 run 查询逐步下沉到更清晰的 repository/service 边界。
3. 强化运行中取消，后续再考虑子进程级终止。
4. 视需要补充“干净数据库 + alembic upgrade head”的迁移验证。
5. 继续把 MockLLM 执行路径替换为真实 LLM 驱动的后端运行配置。
