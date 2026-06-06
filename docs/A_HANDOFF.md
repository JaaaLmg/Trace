# TRACE A 线对接清单

> 面向 B（数据库/API/Worker）和 C（前端/可视化）的交接文档。  
> 当前 A 线负责范围：Agent + 工具契约 + 评测 harness。B/C 不需要重写 Agent，只需要接稳定端口和展示稳定数据。

## 当前状态

- M0/M1/M2 已完成：工具层、三策略 Agent、Reflection 契约、trace/report、demo seeded bug 评测。
- 当前自动测试：`72/72 passed`。
- 真实 LLM adapter 已有两个 provider：
  - `openai`：官方 OpenAI Responses API。
  - `openai_chat_compat`：OpenAI Chat Completions 兼容端点，如 DeepSeek/Qwen/企业兼容网关。
- Mock 评测产物已生成：
  - `eval/results/comparison.md`
  - `eval/results/comparison.json`
- V1 仍未做：数据库、正式 FastAPI 管理 API、队列、前端页面、安全沙箱、真实项目大规模评估。

## 与 V1实施清单.md 的对照

本清单以 `V1实施清单.md` 为准，不按 `初步构想.md` 的旧 6 表草稿走。

| V1 条目 | 清单要求 | 当前 A 状态 | B/C 对接动作 |
| --- | --- | --- | --- |
| §1 V1 目标 | 端到端闭环 + Agent trace + 用例级结果 + seeded bug 脚本评测 | A 已完成 | B/C 基于现有 trace/report/eval 输出接入 |
| §2 14 张表 | V1 必建 14 表 | A 提供 records/trace/strategy 的 Pydantic 形状，不建 DB | B 建 SQLAlchemy/Alembic 表 |
| §2.3 外键 | `project_snapshot_id`、`strategy_version_id` NOT NULL；`runtime_profile_id` NULL | A 内存 schema 为兼容测试暂可 Optional | B 数据库按 V1 收严，创建 run 前必须有 snapshot 和 strategy |
| §3 策略 | 种 3 条 `strategy_versions`，不建父表/Prompt 表/Tool Schema 表 | A 已有 `seeds.py` 和 `StrategyVersionSpec` | B 种同样 3 条，只读 API 暴露 |
| §4 执行模式 | subprocess + workdir + 白名单 + 超时；不是安全沙箱 | A 已有本地执行器端口 | B 可替换加固执行器，但不能改契约 |
| §5 API 子集 | 只开放 V1 列出的项目/计划/run/trace/report API | A 不做 API | B 按子集实现，不开 experiments/runner API |
| §6 硬边界 | Python/FastAPI + pytest；Reflection 一次；评测脚本；前端优先 trace/report | A 已遵守 | C 页面优先 trace/report，comparison 后置 |
| §9 分工 | A Agent+评测，B 平台，C 前端可视化 | A 已交付可并行边界 | B/C 现在可以并行 |

## 先说红线

- B 不要绕过 `execute_run(...)` 自己拼状态机。Agent 的 stage/event/trace 写入顺序已经在 A 线里处理。
- C 不要把 MockLLM 的策略对比表写成“真实模型实测 ReAct 最优”。那张表只证明 harness 可运行，真实模型结论要另跑 `--real`。
- `LocalSubprocessExecutor` 不是安全沙箱。README、汇报、接口文档都不能宣称已实现隔离恶意代码。
- A 当前执行器是本地 subprocess 端口实现；`V1实施清单.md` 里的独立 venv、尽力禁网是 B 执行器加固目标，不是当前已完成事实。
- key 只走环境变量，别进 `.env` 示例、README、数据库种子、截图和提交记录。
- V1 评测走脚本，不落评测表，不开放 experiments API。

## A 给 B 的稳定边界

### 1. Agent 执行入口

B 做 API/Worker 时，核心调用入口是：

```python
from app.agents.orchestrator import execute_run
```

签名位置：`backend/app/agents/orchestrator.py`

关键参数：

- `tools: ToolContext`：项目根、测试写入目录、执行器等运行上下文。
- `registry: ToolRegistry`：工具注册表。
- `llm: LLMClient`：真实或 mock 模型客户端。
- `recorder: RunRecorder`：B 要实现的持久化端口。
- `strategy_spec: StrategyVersionSpec`：策略版本。
- `plan_input: PlanInput`：目标范围、目标描述、是否允许反思、超时。
- `run: Optional[TestRunRecord]`：可由 B 预先创建，也可让 A 内部创建。
- `artifacts_dir`：报告 Markdown/JSON 输出目录。

返回：

- `RunOutcome.run`
- `RunOutcome.report`

### 2. B 必须实现的持久化端口

端口位置：`backend/app/agents/recorder.py`

B 第一阶段只需要用 SQLAlchemy 实现同名方法，替换 `InMemoryRecorder`：

```text
save_run
add_run_event
add_trace_step
add_plan_item
save_plan_item
add_attempt
save_attempt
add_generated_file
add_generated_cases
add_pytest_results
add_artifact
save_report
```

要求：

- `save_*` 是 upsert。
- `add_*` 是 append/insert。
- 写入顺序由 A 调用方保证，B 不要在 recorder 里偷改状态机。
- `TraceStep.step_index` 在同一个 run 内按 A 生成顺序展示即可。

### 3. B 要落库的核心记录

记录 schema 位置：`backend/app/schemas/records.py`

V1 必建 14 张表，按 `V1实施清单.md` §2：

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

A 已提供 Pydantic 记录形状的表：

- `TestRunRecord`
- `RunPlanItemRecord`
- `RunAttemptRecord`
- `GeneratedTestFileRecord`
- `GeneratedTestCaseRecord`
- `PytestCaseResultRecord`
- `RunArtifactRecord`
- `TestReportRecord`

B 还需要按 V1 自己补数据库模型/API schema：

- `projects`
- `project_snapshots`
- `test_plans`
- `strategy_versions`

特别注意：

- `projects.source_type` V1 基本只有 `local_path`，不要一上来接 GitHub App/OpenAPI。
- 数据库里 `test_runs.project_snapshot_id` 必须是 NOT NULL。A 当前 `TestRunRecord.project_snapshot_id` 是 `Optional`，这是因为 A 线没有项目表/快照表；B 落库时不要照这个 Optional 放松 V1 约束。
- 数据库里 `test_runs.strategy_version_id` 必须是 NOT NULL。
- 数据库里 `test_runs.runtime_profile_id` 可以是 NULL，运行环境写进 `runtime_snapshot` JSON。
- `project_snapshots` V1 最简字段：`id`、`project_id`、`source_kind`、`root_path`、`content_hash` 可空、`created_at`。
- `TestRunRecord.strategy_snapshot` 冻结 prompt 正文和模型参数，不能只存 `prompt_ref`。
- `TestRunRecord.runtime_snapshot` 记录运行时环境，不是 runtime profile 表的替代品，V1 可以 JSON 存。
- `PytestCaseResultRecord.is_collection_error=True` 的记录不算 collected。
- `GeneratedTestFileRecord.content_text` V1 可以直接存库；以后大文件再迁 artifact。

### 4. Trace 与事件

schema 位置：`backend/app/schemas/trace.py`

C 展示 trace，B 负责查询：

- `TraceStep`
- `RunEvent`

字段口径：

- `TraceStep.payload` 存结构化详情，前端详情抽屉主要看这里。
- LLM 步骤的 payload 形状通常是：

```json
{
  "attempt_logs": [
    {
      "attempt": 1,
      "messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}],
      "raw_text": "...",
      "error": null
    }
  ],
  "attempts": 1,
  "value": {}
}
```

- 工具调用 payload 通常是 `{"input": ...}`。
- 工具 observation payload 通常是 `{"output": ...}`。
- `tokens` 可为空；失败 LLM 重试已累计 token。

### 5. 工具和执行器边界

工具契约位置：`backend/app/schemas/tools.py`

A 当前工具：

- `list_files`
- `read_file`
- `analyze_project`
- `write_test_file`
- `run_pytest`

执行器端口位置：`backend/app/tools/executor.py`

B 后续可以替换：

```python
class PytestExecutor(Protocol):
    def run(self, work_dir: Path, test_paths: list[str], timeout_seconds: int) -> RawPytestRun: ...
```

但替换时必须保留：

- 独立 work dir。
- 独立 venv，尽力禁网。
- canonical path 白名单。
- 硬超时。
- 结构化 pytest report。
- `--rootdir=work_dir` 的 nodeid 稳定性口径。
- `-p no:cacheprovider`，避免 Windows 重跑删除 `.work` 崩。

### 6. B 的 V1 API 子集

按 `V1实施清单.md`，V1 只开放这些：

```text
POST   /api/v1/projects
GET    /api/v1/projects
GET    /api/v1/projects/{project_id}
POST   /api/v1/projects/{project_id}/snapshots
GET    /api/v1/projects/{project_id}/snapshots

POST   /api/v1/test-plans
GET    /api/v1/test-plans/{plan_id}
POST   /api/v1/test-plans/{plan_id}/runs
GET    /api/v1/test-runs/{run_id}
POST   /api/v1/test-runs/{run_id}/cancel
POST   /api/v1/test-runs/{run_id}/retry

GET    /api/v1/test-runs/{run_id}/trace-steps
GET    /api/v1/test-runs/{run_id}/events
GET    /api/v1/test-runs/{run_id}/attempts
GET    /api/v1/test-runs/{run_id}/pytest-results
GET    /api/v1/test-runs/{run_id}/artifacts
GET    /api/v1/test-runs/{run_id}/report
PATCH  /api/v1/generated-test-cases/{case_id}/adoption

GET    /api/v1/strategy-versions/{version_id}
```

V1 不开放：

- prompt/tool schema 版本管理 API。
- eval datasets / experiments API。
- runner jobs API。
- 远程 runner API。

### 7. B 的建议实现顺序

1. 起技术底座：FastAPI + SQLAlchemy 2.x + Alembic + PostgreSQL；Redis/Celery 或 RQ 可以先留接口，别先把业务卡住。
2. 建 14 张表，对齐 `V1实施清单.md` §2，尤其三个外键拍板。
3. 实现 SQLAlchemy 版 `RunRecorder`。
4. 做 strategy seed 只读接口，先种 `direct` / `plan_execute` / `react_reflection`。
5. 做 project / snapshot / test plan / run 创建接口。
6. 第一版可以同步或本机后台调用 `execute_run(...)`；随后再接 Celery/RQ 异步编排。
7. 做 run 查询、trace 查询、report 查询。
8. 最后再做 cancel/retry。cancel 在 V1 第一版可以先标状态，不强行杀子进程；retry 必须建新 run，并写 `retry_of_run_id`。

别一上来做远程 runner、复杂权限、完整版本管理表。那些不是 V1。

## A 给 C 的稳定边界

### 1. C 可以先不用等 B

C 可以直接用这些文件 mock：

- `eval/results/comparison.json`
- `eval/results/comparison.md`
- A 运行后生成的 report JSON/Markdown artifact。
- `TraceStep` / `RunEvent` / `TestRunRecord` 的假数据。

前端先把页面做顺，B API 后面只是换数据源。

### 2. V1 最值得做的页面

严格按 `V1实施清单.md`，C 的 V1 第一屏优先 trace + report。建议优先级：

1. Project List：能看到项目并进入。
2. Run Detail + Trace Timeline：状态、阶段、策略、模型、tokens、tool calls、错误；按 `step_index` 展示 plan/tool/generation/reflection/report。
3. Report View：展示 Markdown 报告 + metrics。
4. Pytest Results：用例级 passed/failed/error/skipped、failure_type、message。
5. Comparison View：展示 `comparison.json` 的 rows 和 capture_matrix。
6. Test Plan 页面：V1 可以简陋，能创建和跳转即可。

进度紧张时砍 4-6，别砍 trace/report。

### 3. C 的数据口径

Run summary 主要来自：

- `TestRunRecord.status`
- `TestRunRecord.stage`
- `TestRunRecord.total_tokens`
- `TestRunRecord.tool_call_count`
- `TestRunRecord.pytest_summary`
- `TestRunRecord.error_code`
- `TestRunRecord.error_message`

Trace timeline 来自：

- `TraceStep.step_index`
- `TraceStep.step_type`
- `TraceStep.name`
- `TraceStep.status`
- `TraceStep.tool_name`
- `TraceStep.tokens`
- `TraceStep.duration_ms`
- `TraceStep.input_summary`
- `TraceStep.output_summary`
- `TraceStep.payload`
- `TraceStep.error`

Report 来自：

- `TestReportRecord.summary`
- `TestReportRecord.metrics`
- `TestReportRecord.risk_notes`
- `TestReportRecord.markdown_uri`
- `TestReportRecord.json_uri`

Comparison 来自：

- `comparison.json.rows`
- `comparison.json.capture_matrix`

### 4. C 展示时别乱讲

可以说：

- TRACE 能记录完整 Agent trace。
- TRACE 能展示生成、执行、反思、报告过程。
- Mock 评测证明 harness 能区分捕获、漏判、假阳性。

不能说：

- ReAct 真实效果一定优于 Direct/Plan。
- 当前 token 是真实模型成本。
- 当前 subprocess 是安全沙箱。
- 当前 demo 捕获率能外推到真实项目。

## A 线还剩什么

对接前非阻塞：

- 真实 LLM smoke：用本机 key 跑 `openai` 和一个 `openai_chat_compat`。
- 真实 LLM `--repeats 1` 小评测：确认真实模型下 JSON/schema 稳定性。
- 进度文档整理：`PROGRESS.md` 仍保留大量审查历史，后面可压缩。

V1 可暂缓：

- 弱断言识别增强，如 `assert x == x`、`assert result is not None`、断言藏在永不执行分支。
- 真实安全沙箱。
- 多项目大型评估集。
- 评测入库和 experiments API。
- Anthropic/Claude adapter。

## 真实 LLM 使用方式

官方 OpenAI：

```powershell
$env:TRACE_LLM_API_KEY="你的 key"
python eval/harness/run_eval.py --provider openai --list-models
python eval/harness/run_eval.py --real --provider openai --model gpt-5 --smoke
```

OpenAI Chat Completions 兼容端点：

```powershell
$env:TRACE_LLM_API_KEY="你的兼容端点 key"
python eval/harness/run_eval.py --provider openai_chat_compat --base-url "https://api.deepseek.com/v1" --list-models
python eval/harness/run_eval.py --real --provider openai_chat_compat --base-url "https://api.deepseek.com/v1" --model "deepseek-chat" --smoke
```

全量真实评测建议先跑 1 次重复：

```powershell
python eval/harness/run_eval.py --real --provider openai --model gpt-5 --repeats 1
```

确认稳定后再跑：

```powershell
python eval/harness/run_eval.py --real --provider openai --model gpt-5 --repeats 3
```

## 当前可验证命令

跑 A 全量测试：

```powershell
python -m pytest backend/tests -q --rootdir backend -p no:cacheprovider
```

跑 Mock 评测：

```powershell
python eval/harness/run_eval.py
```

跑 Mock smoke：

```powershell
python eval/harness/run_eval.py --smoke
```

## 对接验收标准

B 第一轮算过关：

- 能创建 test plan。
- 能触发一次 run。
- run 数据落库。
- trace steps/events/attempts/pytest results/report 都能通过 API 查到。
- 失败 run 不悬空，`status=failed` 且有 `error_code/error_message`。

C 第一轮算过关：

- 能展示一个 run 的 timeline。
- 能展开 LLM attempt_logs。
- 能展示 pytest 用例结果和失败类型。
- 能展示 report。
- 能展示 comparison 表和逐 bug 捕获矩阵。

联合验收：

- B 用 MockLLM 跑出一个 run。
- C 通过 B API 展示这个 run。
- 不需要真实 LLM。
- 不需要数据库里有评测 experiment。
- 不需要安全沙箱。

## 文件索引

- `backend/app/agents/orchestrator.py`：Agent 执行入口。
- `backend/app/agents/recorder.py`：B 要实现的持久化端口。
- `backend/app/agents/report.py`：report 生成逻辑。
- `backend/app/agents/llm_factory.py`：真实 LLM provider 工厂。
- `backend/app/schemas/records.py`：B 落库主记录。
- `backend/app/schemas/trace.py`：C trace 展示主数据。
- `backend/app/schemas/tools.py`：工具 I/O 契约。
- `backend/app/schemas/agent.py`：LLM 结构化输出契约。
- `backend/app/schemas/strategy.py`：策略版本契约。
- `backend/app/tools/executor.py`：pytest 执行器端口。
- `eval/harness/run_eval.py`：评测入口。
- `eval/results/comparison.json`：C 可直接 mock 的评测数据。
