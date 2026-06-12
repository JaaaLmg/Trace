# TRACE 仓库分析

## 1. 先说结论

这个仓库当前实现的不是完整的 TRACE 平台，而是 **TRACE 的 V1 A 线版本**，也就是：

- 已完成：Agent 核心闭环、工具契约、MockLLM/真实 LLM 适配、一次 Reflection、trace/report、seeded bug 评测 harness。
- 未完成：数据库、正式 FastAPI 管理 API、队列/Worker、前端页面、Docker/Runner 安全隔离、多项目平台化管理。

所以从代码结构上看，仓库现在更像一个“**可运行的 Agent 内核 + 评测系统原型**”，而不是一个已经成型的完整 Web 平台。

这和文档中的定位完全一致：

- `docs/需求分析.md` 说明最终产品边界；
- `docs/系统设计.md` 说明最终形态蓝图；
- `docs/V1实施清单.md` 说明 V1 只做其中一个最小闭环子集；
- `docs/A_HANDOFF.md` 说明当前仓库正是 A 线交付给 B/C 的版本。

---

## 2. 项目整体结构

仓库顶层目前可以分成 5 块：

```text
TRACE/
  assets/    品牌资源
  backend/   Agent 内核、工具层、契约、测试
  docs/      需求/设计/V1范围/交接文档
  eval/      demo 数据集、seeded bug、评测 harness、评测结果
  README.md  项目说明与使用入口
```

### 2.1 这几个目录分别承担什么职责

- `docs/`：定义“TRACE 应该是什么”和“V1 这次真正做什么”。
- `backend/`：实现 Agent 的执行闭环，是当前仓库的主体。
- `eval/`：实现“生成测试后如何评测策略好坏”，这是 TRACE 与普通“会写 pytest 的脚本”最大的区别之一。
- `assets/`：只是 logo 资源，不参与运行逻辑。
- `README.md`：把文档中的定位和当前代码状态重新对外说明一遍。

---

## 3. 文档如何映射到代码

### 3.1 `docs/需求分析.md`

这份文档定义了产品目标：

- TRACE 是一个面向 Python/FastAPI 的测试生成 Agent 平台；
- 核心闭环是“分析项目 -> 生成测试 -> 执行 pytest -> 读取失败 -> 一次 Reflection -> 记录 trace/report -> 评测”；
- 重点不是“生成了多少测试”，而是“这些测试是否真实可运行、可解释、能否抓到已知 bug”。

这份文档对应到代码里，主要落在：

- `backend/app/tools/`：工具边界；
- `backend/app/agents/`：Agent 编排、策略、Reflection、报告；
- `backend/app/schemas/`：结构化结果契约；
- `eval/harness/`：seeded bug capture rate 和 false positive rate 的评测逻辑。

### 3.2 `docs/系统设计.md`

这份文档描述最终蓝图，范围更大，包括：

- control plane；
- execution plane；
- evaluation plane；
- 数据库表；
- Runner API；
- V2/V3 的平台化能力。

当前代码只实现了其中一部分，主要是：

- Agent plane；
- 最简 execution plane（本地 subprocess 跑 pytest）；
- 最简 evaluation plane（脚本式 seeded bug 评测）；
- 数据模型暂时用 Pydantic record/schema 表达，还没有真正落 DB。

### 3.3 `docs/V1实施清单.md`

这是当前实现最关键的“落地裁剪版”文档。它决定了：

- V1 不做 Docker、远程 Runner、评测落库；
- V1 先跑通端到端闭环；
- 工具层必须结构化；
- 策略只做 3 种；
- 执行器是本地 subprocess，不允许夸大为安全沙箱。

当前代码基本就是按这份文档执行的。

### 3.4 `docs/A_HANDOFF.md`

这是“当前代码如何交接给 B/C”的说明书。它清楚说明：

- A 已完成 Agent、工具契约、评测 harness；
- B 后续负责数据库/API/Worker；
- C 后续负责前端展示；
- `execute_run(...)` 是核心入口；
- `RunRecorder` 是最重要的持久化扩展点。

这份文档本质上就是当前仓库代码的“使用说明”和“集成边界说明”。

---

## 4. 当前代码实现的核心架构

当前实现可以理解为四层：

```text
LLM 层
  -> 结构化输出层
    -> Agent 编排层
      -> 工具执行层
        -> pytest 结果结构化层
          -> trace/report 层
            -> eval 重放与指标层
```

### 4.1 一条完整运行链路

一次运行的大致流程如下：

1. `execute_run(...)` 创建/初始化 `TestRunRecord`。
2. 冻结 `strategy_snapshot` 和 `runtime_snapshot`。
3. 根据策略选择 `direct / plan_execute / react_reflection`。
4. 调用 `analyze_project` 分析被测项目。
5. 让 LLM 输出结构化计划或结构化测试文件。
6. 用 `write_test_file` 把测试写入白名单目录。
7. 用 `run_pytest` 启动 subprocess 跑 pytest。
8. 把 pytest 结果解析成：
   - `generated_test_cases`
   - `pytest_case_results`
   - `failures`
   - `collection_errors`
9. 如果策略允许且有必要，则执行一次 Reflection。
10. 生成 Markdown/JSON 报告。
11. 在评测模式下，把最终测试集重放到每个 bug 变体上，计算捕获率。

### 4.2 为什么仓库主体都在 `backend/app/agents`、`backend/app/tools` 和 `eval/harness`

因为当前版本还没有平台层，所以业务主线完全围绕这三部分展开：

- `agents/`：决定 Agent 怎么思考、怎么编排、怎么记录过程；
- `tools/`：决定 Agent 能做什么、能读什么、能写什么、怎么跑 pytest；
- `eval/harness/`：决定生成出来的测试如何被评估。

---

## 5. 顶层文件说明

### `README.md`

作用：

- 对外解释 TRACE 的定位；
- 说明当前仓库只完成了 A 线；
- 给出运行测试和评测的方式；
- 说明真实 LLM 与 MockLLM 的使用方法；
- 明确安全边界：当前 subprocess 执行器不是安全沙箱。

### `.gitignore`

作用：

- 常规忽略文件；
- 避免产物、缓存、环境文件污染仓库。

---

## 6. `docs/` 目录说明

### `docs/需求分析.md`

作用：

- 定义产品边界、核心原则、目标用户、非目标；
- 规定 TRACE 的核心价值是可执行、可追踪、可评测；
- 规定 seeded bug capture rate 是核心指标。

### `docs/系统设计.md`

作用：

- 给出最终系统架构蓝图；
- 定义状态机、数据模型、工具契约、Runner 边界、API 范围；
- 是最终形态的技术设计依据。

### `docs/V1实施清单.md`

作用：

- 把最终蓝图裁剪成 V1 真正要做的子集；
- 明确当前阶段不做哪些东西；
- 指定 V1 的核心交付是端到端闭环和最小 seeded bug 评测。

### `docs/A_HANDOFF.md`

作用：

- 面向 B/C 的交接文档；
- 说明 A 已交付什么、边界在哪里、如何调用现有 Agent 执行入口；
- 说明 recorder、trace、tool contract、策略种子如何接入后续平台层。

---

## 7. `assets/` 目录说明

### `assets/logo.svg`

作用：项目主 logo。

### `assets/logo-icon.svg`

作用：项目图标版本的 logo。

这两个文件不参与业务逻辑。

---

## 8. `backend/` 目录总体说明

`backend/` 是当前仓库最核心的部分，它实现了：

- Agent 工作流；
- 工具调用；
- pytest 执行；
- 结构化 trace；
- 结构化报告；
- 与真实/Mock LLM 的适配；
- 面向 B 线的 record/schema 边界。

目录结构如下：

```text
backend/
  pyproject.toml
  requirements.txt
  app/
    agents/
    core/
    schemas/
    tools/
  tests/
```

### `backend/pyproject.toml`

作用：

- 定义包名、Python 版本和依赖；
- 说明当前 backend 是轻量实现；
- 限定 pytest 默认只扫 `tests/`。

### `backend/requirements.txt`

作用：

- 当前 V1 A 线所需的最小依赖列表；
- 明确还没有加入 SQLAlchemy / Alembic / Redis / Celery 等 B 线依赖。

---

## 9. `backend/app/core/`：底层通用设施

### `backend/app/core/errors.py`

作用：

- 定义全局错误码 `ErrorCode`；
- 定义领域异常 `TraceError`；
- 让运行失败不是“普通异常字符串”，而是带错误码、可落 trace 的结构化失败。

这个文件很关键，因为它把“失败也要可追踪、可分类”落实到了代码层。

### `backend/app/core/ids.py`

作用：

- 统一生成 UUID 字符串 ID；
- 当前作为内存记录和未来数据库主键的统一来源。

---

## 10. `backend/app/schemas/`：契约层

这一层很重要。当前仓库虽然还没有数据库和 API，但已经先把未来系统需要交换的数据形状固定下来了。

### `backend/app/schemas/agent.py`

作用：

- 定义 LLM 输出的结构：
  - `PlanOutput`
  - `GenerationOutput`
  - `ReflectionOutput`
- 保证模型输出必须过 Pydantic 校验。

这是“结构化 Agent”而不是“自由文本 Agent”的核心。

### `backend/app/schemas/records.py`

作用：

- 定义未来要落库的记录体；
- 包括：
  - `TestRunRecord`
  - `RunPlanItemRecord`
  - `RunAttemptRecord`
  - `GeneratedTestFileRecord`
  - `GeneratedTestCaseRecord`
  - `PytestCaseResultRecord`
  - `RunArtifactRecord`
  - `TestReportRecord`

它的角色可以理解为“**数据库模型前的中间契约**”。

### `backend/app/schemas/strategy.py`

作用：

- 定义 V1 的 `StrategyVersionSpec`；
- 描述策略身份、workflow 类型、模型信息、prompt/tool schema 引用等。

当前没有正式 `strategy_versions` 数据表，这个 schema 起到了“策略版本对象”的作用。

### `backend/app/schemas/tools.py`

作用：

- 定义所有工具的输入输出契约：
  - `list_files`
  - `read_file`
  - `analyze_project`
  - `write_test_file`
  - `run_pytest`
- 同时定义 pytest 结果中的 `CaseResult`、`FailureDetail` 等结构。

这是整个工具层的“接口协议书”。

### `backend/app/schemas/trace.py`

作用：

- 定义运行状态、阶段、trace step、run event 的结构；
- 把状态机审计和 Agent 过程审计分开表达。

它直接对应系统设计文档里的 `trace_steps` 和 `run_events`。

### `backend/app/schemas/__init__.py`

作用：包初始化文件，没有业务逻辑。

---

## 11. `backend/app/tools/`：受控工具层

这一层定义“Agent 能做什么，但不能直接乱做什么”。

### `backend/app/tools/base.py`

作用：

- 定义 `ToolContext`；
- 定义 `ToolSpec` 和 `ToolRegistry`；
- 实现路径白名单与 canonical path 校验；
- 统一做工具输入的 Pydantic 校验。

这是工具层的基础设施。

最关键的设计点：

- `root` 是被测项目根目录；
- `test_write_dir` 是唯一允许写生成测试的目录；
- `resolve_read` 和 `resolve_write` 保证 Agent 不能越界读写。

### `backend/app/tools/fs_tools.py`

作用：

- 实现 `list_files`；
- 实现 `read_file`。

特点：

- 只在白名单范围内读；
- 忽略 `.git`、`node_modules`、`.venv` 等无关目录；
- 读文件时限制最大字节数。

### `backend/app/tools/analyze.py`

作用：

- 实现 `analyze_project`；
- 用 AST 静态分析源码；
- 抽取：
  - 文件列表
  - FastAPI 路由
  - 函数
  - Pydantic 模型
  - 已有测试
  - 依赖文件
  - 分析 warning

它贯彻了设计文档中的原则：**不给 LLM 整仓源码，而是先结构化分析项目**。

### `backend/app/tools/write_test.py`

作用：

- 实现 `write_test_file`；
- 只允许把测试文件写到白名单目录；
- 返回写入后的 `file_id`、相对路径、哈希和值大小。

它负责把“生成测试”从文本变成真实文件。

### `backend/app/tools/run_pytest.py`

作用：

- 实现 `run_pytest`；
- 调用执行器启动 pytest；
- 再把原始 pytest 结果解析成结构化输出。

关键设计点：

- 区分系统错误和业务失败；
- 区分 `case_results` 与 `collection_errors`；
- 只把 assertion failure 视为“可能捕获 bug”的失败；
- 给每个 case 计算 `failure_type`。

这是评测可信度的基础文件之一。

### `backend/app/tools/executor.py`

作用：

- 定义执行器协议 `PytestExecutor`；
- 实现当前 V1 的 `LocalSubprocessExecutor`。

当前执行模式：

- 本地 subprocess；
- 独立工作目录；
- 超时控制；
- 自定义 pytest 插件回传结构化 JSON；
- 固定 `--rootdir=work_dir` 保证 nodeid 稳定。

这个文件特别重要，因为它解决了“相同测试在 clean/variant 环境下 nodeid 是否稳定”的问题，这直接影响 replay 对齐是否可靠。

### `backend/app/tools/_trace_pytest_plugin.py`

作用：

- 这是注入到 pytest 子进程里的轻量插件；
- 负责收集每个测试的：
  - outcome
  - duration
  - message
  - exc_type
  - longrepr
  - collect errors
- 最后写成 JSON 报告。

可以把它理解为 `run_pytest` 的“探针”。

### `backend/app/tools/__init__.py`

作用：

- 汇总工具；
- 提供 `default_registry()`；
- 让 Agent 直接拿到标准工具集。

---

## 12. `backend/app/agents/`：Agent 核心

这一层是当前仓库最核心的业务实现。

### `backend/app/agents/orchestrator.py`

作用：

- 提供整个运行入口 `execute_run(...)`；
- 负责：
  - 初始化 run；
  - 冻结策略快照和 runtime 快照；
  - 选择策略；
  - 处理运行完成或失败；
  - 生成最终报告。

这是整个 Agent 闭环的总入口，也是以后 B 线接 API/Worker 时最重要的调用点。

### `backend/app/agents/runtime.py`

作用：

- 定义 `PlanInput`；
- 定义 `AgentContext`。

`AgentContext` 是三种策略共享的运行时环境，负责：

- 切换 stage；
- 写 trace；
- 调用工具；
- 记录 tool call 次数；
- 调用 LLM 并做结构化输出；
- 累积 token。

可以把它理解为“**策略脚本运行在其中的统一执行框架**”。

### `backend/app/agents/recorder.py`

作用：

- 定义持久化端口 `RunRecorder`；
- 提供当前的 `InMemoryRecorder` 实现。

这其实是 A 线与 B 线最关键的解耦点：

- A 先用内存 recorder 跑通闭环；
- B 将来只要实现同名接口，就可以把结果落到 SQLAlchemy/数据库里。

### `backend/app/agents/report.py`

作用：

- 从 recorder 中汇总运行结果；
- 生成 `TestReportRecord`；
- 渲染 Markdown/JSON 报告；
- 回写 `pytest_summary`。

它负责把散落的运行数据变成“人类可读的总结”。

### `backend/app/agents/prompts.py`

作用：

- 集中管理 system prompt、plan prompt、generate prompt、reflect prompt；
- 提供 `prompt_bundle(...)`；
- 在 run 开始时把完整 prompt 冻结进 `strategy_snapshot`。

这个设计很重要，因为它保证以后 prompt 文本变了，历史运行仍可回溯。

### `backend/app/agents/structured.py`

作用：

- 实现“LLM 输出 JSON -> 解析 -> Pydantic 校验 -> 失败重试”；
- 记录每次 attempt 的原始输入、输出、错误。

它把“结构化输出”落到了实处，也让失败时能完整回看模型重试过程。

### `backend/app/agents/llm.py`

作用：

- 定义 `Message`、`LLMResponse`、`LLMClient` 协议；
- 提供 `MockLLM`；
- 提供粗略 token 估算。

MockLLM 是整个仓库的关键解耦器，因为没有它就无法在没有真实模型的情况下稳定跑通端到端流程和评测。

### `backend/app/agents/llm_http.py`

作用：

- 封装真实 LLM HTTP 请求的公共逻辑；
- 处理重试、错误格式化、密钥脱敏、Retry-After 等细节。

### `backend/app/agents/llm_openai.py`

作用：

- 实现官方 OpenAI Responses API adapter；
- 满足 `LLMClient` 协议。

### `backend/app/agents/llm_openai_chat_compat.py`

作用：

- 实现 OpenAI Chat Completions 兼容端点 adapter；
- 用于 DeepSeek/Qwen/企业兼容网关这类接口。

### `backend/app/agents/llm_factory.py`

作用：

- 根据 provider 和 model 参数创建对应的 LLM adapter；
- 统一 provider/model 的选择逻辑。

### `backend/app/agents/seeds.py`

作用：

- 定义 V1 的 3 个策略种子：
  - `Direct v1`
  - `Plan-and-Execute v1`
  - `ReAct+Reflection v1`

这个文件相当于当前版本里的“策略种子表”。

### `backend/app/agents/contract_guard.py`

作用：

- 对 Reflection 结果做静态 AST 审查；
- 拦截：
  - `pytest.skip/xfail`
  - 空洞断言
  - 宽泛 `except`
  - 断言数量减少
  - 测试函数数量减少

这是防止 Reflection 为了“变绿”而作弊的关键安全闸门。

### `backend/app/agents/case_mapping.py`

作用：

- 从生成的测试文件 AST 中登记 `generated_test_cases`；
- 提供 pytest nodeid 与生成用例之间的辅助映射逻辑；
- 处理参数化 nodeid 的归并。

这个文件是后续计算 capture rate、false positive rate 的基础。

### `backend/app/agents/final_attempts.py`

作用：

- 定义“每个 plan item 的最终 attempt 怎么选”；
- 规则是：选择最后一次真正跑出 pytest 结果的 attempt。

它保证 report 和 eval replay 使用同一套最终测试集口径。

### `backend/app/agents/__init__.py`

作用：包初始化文件，没有核心逻辑。

---

## 13. `backend/app/agents/strategies/`：三种策略实现

这部分是“同一个执行框架下，不同编排方式”的实现。

### `backend/app/agents/strategies/base.py`

作用：

- 定义策略基类 `Strategy`；
- 统一 `run(ctx, plan_input)` 接口。

### `backend/app/agents/strategies/common.py`

作用：

- 抽出三种策略共享的执行步骤：
  - `do_analyze`
  - `do_generate`
  - `do_run`
  - `execute_item`
  - `_reflect_once`
  - `_register_cases`
  - `_map_results`

这使得三种策略文件本身很薄，只保留“编排差异”。

### `backend/app/agents/strategies/direct.py`

作用：

- 实现 Direct 策略；
- 单任务；
- 不先规划；
- 不做 Reflection。

### `backend/app/agents/strategies/plan_execute.py`

作用：

- 实现 Plan-and-Execute 策略；
- 先让 LLM 拆任务；
- 再逐个任务生成并执行；
- 不做 Reflection。

### `backend/app/agents/strategies/react_reflection.py`

作用：

- 实现 ReAct + Reflection 策略；
- 单任务生成；
- 首轮失败且预算允许时做一次 Reflection。

### `backend/app/agents/strategies/__init__.py`

作用：

- 提供 `get_strategy(workflow_type)`；
- 作为策略注册表。

---

## 14. `backend/tests/`：测试体系

这部分说明 A 不只是写了代码，还把关键契约、执行链和评测口径都锁进测试了。

### `backend/tests/conftest.py`

作用：

- 调整 `sys.path`；
- 让测试无需 editable install 也能导入 `app` 和 `eval`。

### `backend/tests/test_m1_foundation.py`

作用：

- 测试结构化输出重试；
- 测试 recorder upsert；
- 是 M1 基础能力的单测。

### `backend/tests/test_e2e_mockllm.py`

作用：

- 端到端测试三种策略；
- 覆盖：
  - Direct 成功；
  - Plan-and-Execute 多任务；
  - Reflection 修复成功；
  - Reflection 契约违规；
  - 疑似业务缺陷保留失败；
  - 非法模型输出导致 run failed。

这是当前仓库最重要的集成测试之一。

### `backend/tests/test_analyze.py`

作用：

- 测 `analyze_project` 的 AST 分析行为；
- 包括路由、prefix、include_router warning、existing_tests 等。

### `backend/tests/test_run_pytest.py`

作用：

- 测 `run_pytest` 的结构化解析；
- 验证 passed/failed/import/collection error 的分类口径。

### `backend/tests/test_write_test_file.py`

作用：

- 测试白名单写入；
- 确认不能写业务源码、不能路径越界、`test_write_dir` 必须严格在 root 内。

### `backend/tests/test_contract_guard.py`

作用：

- 测 Reflection 静态闸门；
- 验证削弱断言、skip、broad except、空测试等都能被识别。

### `backend/tests/test_executor_rootdir.py`

作用：

- 验证执行器固定 `--rootdir=work_dir` 后，nodeid 在不同工作目录下仍稳定；
- 这直接服务于 replay 对齐。

### `backend/tests/test_llm_openai.py`

作用：

- 测 OpenAI Responses adapter；
- 覆盖请求形状、鉴权、重试、错误脱敏、模型列表、截断处理等。

### `backend/tests/test_llm_openai_chat_compat.py`

作用：

- 测 Chat Completions 兼容 adapter；
- 覆盖 provider factory、base URL、模型要求、重试和错误处理。

### `backend/tests/test_eval_dataset.py`

作用：

- 测 demo 数据集自身是否有效；
- 确认每个 bug 真正改变行为；
- 防止出现“惰性 bug”。

### `backend/tests/test_eval_harness.py`

作用：

- 端到端测试评测 harness；
- 验证三种策略的 scripted 故事是否如预期映射为 capture/false positive 指标。

---

## 15. `eval/` 目录总体说明

如果说 `backend/` 解决的是“Agent 怎么生成并运行测试”，那么 `eval/` 解决的是“这些测试到底有没有价值”。

这也是 TRACE 与普通代码生成项目最不一样的地方。

`eval/` 目前由三部分组成：

```text
eval/
  demo/      demo 被测项目与 bug 定义
  harness/   评测执行与指标计算
  results/   已生成的评测结果
```

---

## 16. `eval/demo/`：最小被测数据集

### `eval/demo/bugs.py`

作用：

- 定义 6 个 seeded bug 的 ground truth；
- 指定：
  - bug 类型
  - 目标函数/路由
  - patch 替换规则
  - clean 行为
  - buggy 行为
  - 期望检测方式

这个文件是整个评测系统的“标签真值”来源。

### `eval/demo/clean/shop/pricing.py`

作用：

- demo 的纯函数业务模块；
- 包含多个非常适合写断言的函数：
  - `apply_discount`
  - `shipping_fee`
  - `clamp_discount_rate`
  - `is_free_shipping`
  - `loyalty_points`

### `eval/demo/clean/shop/api.py`

作用：

- demo 的 FastAPI 路由模块；
- 提供 `get_price`；
- 用于“错误状态码”这类路由级 bug 的评测。

### `eval/demo/__init__.py`

作用：包初始化。

### `eval/demo/clean/shop/__init__.py`

作用：包初始化。

---

## 17. `eval/harness/`：评测执行框架

### `eval/harness/dataset.py`

作用：

- 加载 bug 定义；
- 物化 clean 副本；
- 物化 bug variant 副本；
- 应用 patch；
- 确保 patch 唯一命中；
- 在 Windows 下做更稳健的目录清理。

它是“污染隔离”的物理基础。

### `eval/harness/authors.py`

作用：

- 提供 scripted `demo_author`；
- 它不是一个真正的推理模型，而是一个“按剧情出牌的 Mock 作者”：
  - Direct/ReAct 首轮写出 5 个函数测试 + 1 个写错状态码的路由测试；
  - Plan-and-Execute 逐目标生成，路由断言写对；
  - ReAct 反思阶段把错误状态码断言修正回来。

它的作用不是模拟真实智能，而是稳定驱动 harness 验证不同策略路径。

### `eval/harness/runner.py`

作用：

- 负责单次 clean run；
- 然后对每个 bug variant 做 replay；
- 记录：
  - clean 是否通过
  - 哪些测试通过
  - 哪些 bug 被捕获

### `eval/harness/replay.py`

作用：

- 把 clean 阶段已经定型的测试文件原样写入目标目录；
- 重新运行 pytest；
- 不再调用 LLM、不再重新生成测试。

这是污染隔离的核心。

### `eval/harness/final_set.py`

作用：

- 从一次 clean run 中提取“最终测试集”；
- 规则与 report 一致：每个 item 取最终有效 attempt。

### `eval/harness/metrics.py`

作用：

- 聚合评测指标；
- 计算：
  - `seeded_bug_capture_rate`
  - `clean_false_positive_rate`
  - `cost_per_captured_bug`
  - 平均 tokens
  - 平均工具调用数
- 渲染 Markdown 对比表和捕获矩阵。

### `eval/harness/run_eval.py`

作用：

- 评测入口脚本；
- 可以跑：
  - MockLLM 评测；
  - 真实 LLM smoke；
  - 真实 LLM 全量评测；
- 产出 `comparison.md/json` 或 `comparison_real.md/json`。

这是 `eval/` 最重要的执行入口。

### `eval/harness/__init__.py`

作用：包初始化。

---

## 18. `eval/results/`：评测产物

### `eval/results/comparison.json`

作用：

- 保存评测结果的结构化 JSON；
- 很适合给前端或可视化直接消费。

### `eval/results/comparison.md`

作用：

- 保存评测结果的 Markdown 摘要；
- 用于 README、汇报或人工阅读。

---

## 19. 当前仓库最重要的设计特点

### 19.1 它不是“让 LLM 直接输出测试文本”那么简单

中间多了几层非常关键的工程化设计：

- 项目分析先结构化，再喂给 LLM；
- 所有模型输出过 Pydantic；
- 工具调用严格白名单；
- pytest 结果结构化而不是只看 stdout；
- Reflection 有静态契约闸门；
- 最终报告和评测共享统一的 final attempt 口径。

### 19.2 它把“评测”当成第一公民

很多 Agent 项目只做到“跑起来”，但这个仓库已经额外实现了：

- clean 生成；
- variant 重放；
- capture matrix；
- false positive 统计；
- 成本统计。

这正是文档一直强调的 TRACE 核心价值。

### 19.3 它已经为后续数据库/API 做了很强的预留

虽然还没有 SQLAlchemy/FastAPI 管理 API，但代码里已经有：

- `records.py`：未来数据库记录体；
- `trace.py`：未来前端展示的 timeline 数据；
- `RunRecorder`：未来 SQLAlchemy 落库端口；
- `StrategyVersionSpec`：未来策略表的对象形状。

所以这不是“一次性脚本”，而是有明确平台化方向的 V1 内核。

---

## 20. 当前实现边界与缺失部分

根据文档和代码，当前仓库明确还缺少以下部分：

### 20.1 平台层缺失

- 没有正式 FastAPI 管理 API；
- 没有数据库；
- 没有 Alembic；
- 没有队列和异步 Worker；
- 没有项目、计划、运行的持久化管理页面。

### 20.2 执行隔离仍是 V1 最简版本

- 当前只用本地 subprocess；
- 没有 Docker；
- 没有真正禁网；
- 没有容器级资源隔离；
- 明确不能当作安全沙箱。

### 20.3 评测目前还是脚本式

- 没有 experiments API；
- 没有评测数据库表；
- 没有多项目数据集管理；
- 只有一个 demo 项目和 6 个 bug 变体。

### 20.4 前端未实现

- 目前没有 `frontend/`；
- `A_HANDOFF.md` 中提到的 trace/report 页面属于后续 C 线工作。

---

## 21. 如何理解这份仓库的“整体结构”

如果用一句话概括当前代码结构，我会这样描述：

> 这个仓库把 TRACE 的最终蓝图切出了一个最重要、最能体现 Agent 工程价值的核心子系统：  
> 一个面向 Python/FastAPI 项目的测试生成 Agent 内核，它能够在受控工具边界中分析项目、生成并执行 pytest、进行一次受约束 Reflection、记录完整 trace/report，并用 seeded bug replay 的方式评测策略效果。

换句话说：

- `docs/` 负责定义目标；
- `backend/app/` 负责把目标最小化落地；
- `backend/tests/` 负责证明这套核心链路可信；
- `eval/` 负责证明“生成出来的测试有评测意义”。

这就是当前仓库的真实结构。

---

## 22. 推荐的阅读顺序

如果要继续理解或接手这个项目，最推荐的阅读顺序是：

1. `README.md`
2. `docs/需求分析.md`
3. `docs/系统设计.md`
4. `docs/V1实施清单.md`
5. `docs/A_HANDOFF.md`
6. `backend/app/agents/orchestrator.py`
7. `backend/app/agents/runtime.py`
8. `backend/app/agents/strategies/common.py`
9. `backend/app/tools/run_pytest.py`
10. `backend/app/tools/executor.py`
11. `backend/app/agents/report.py`
12. `eval/harness/run_eval.py`
13. `backend/tests/test_e2e_mockllm.py`
14. `backend/tests/test_eval_harness.py`

按这个顺序读，会最容易从“产品目标”过渡到“代码实现”和“评测逻辑”。
