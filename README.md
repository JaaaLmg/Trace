<p align="center">
  <img src="assets/logo.svg" alt="TRACE logo" width="450">
</p>

TRACE 是一个面向 Python/FastAPI 后端项目的测试生成 Agent 原型。它把“模型生成 pytest 文本”推进成一条可执行、可追踪、可评测的工程闭环：

```text
分析项目 -> 生成测试 -> 执行 pytest -> 读取结构化失败 -> 一次受约束 Reflection -> 生成报告 -> seeded bug 评测
```

当前仓库完成的是 **A 分工：Agent + 工具契约 + 评测 harness**。数据库、正式 API、队列、前端页面属于 B/C 后续接入范围。

## 当前状态

- M0：工具契约、路径白名单、pytest 结构化执行已完成。
- M1：MockLLM、三策略 Agent loop、Reflection 契约、trace/report 已完成。
- M2：demo seeded bugs、污染隔离评测 harness、策略对比表已完成。
- 真实 LLM：已接入官方 OpenAI Responses 与 OpenAI Chat Completions 兼容入口；具体中转站私有适配不写进主线。
- 当前测试：`72/72 passed`。
- 评测产物：`eval/results/comparison.md`、`eval/results/comparison.json`。

本项目以 `需求分析.md`、`系统设计.md`、`V1实施清单.md` 为技术依据。`初步构想.md` 是旧草稿，不作为当前实现依据。

## 目录结构

```text
TRACE/
  backend/
    app/
      core/       # 错误码、ID
      schemas/    # 工具、trace、agent、record、strategy 契约
      tools/      # list/read/analyze/write/run_pytest + subprocess executor
      agents/     # MockLLM、三策略、orchestrator、report、contract guard
    tests/        # 单元/集成测试
  eval/
    demo/clean/   # demo 被测项目：shop 定价函数 + FastAPI 路由
    demo/bugs.py  # 6 个 seeded bug ground truth
    harness/      # 干净生成 + 变体重放 + 指标聚合
    results/      # comparison.md/json
```

## 快速开始

建议使用 Python 3.11。Windows 上如果系统 `python` 是 Microsoft Store 占位符，请直接使用实际解释器路径。

```bash
cd TRACE
pip install -r backend/requirements.txt
```

运行测试：

```bash
python -m pytest backend/tests -q --rootdir backend -p no:cacheprovider
```

如果本机临时目录有权限问题，可指定仓库外或可写临时目录：

```bash
python -m pytest backend/tests -q --rootdir backend -p no:cacheprovider -o tmp_path_retention_policy=none --basetemp="D:/tmpdir/Temp/trace_pytest"
```

运行评测：

```bash
python eval/harness/run_eval.py
```

评测会生成：

```text
eval/results/comparison.md
eval/results/comparison.json
```

接入真实 LLM API：

```powershell
$env:TRACE_LLM_API_KEY="你的 OpenAI API key"
python eval/harness/run_eval.py --provider openai --list-models
python eval/harness/run_eval.py --real --provider openai --model gpt-5 --smoke
```

真实 API 只通过环境变量读取 key；最好不要把 key 写进命令、README、`.env` 示例或提交记录。`--list-models` 可验证当前 key 能访问哪些模型，`--smoke` 只跑 1 个策略 × 1 次重复，用来确认真实调用能走通。

OpenAI Chat Completions 兼容端点（如 DeepSeek/Qwen/企业兼容网关）走 `openai_chat_compat`，必须显式给 base URL 和模型：

```powershell
$env:TRACE_LLM_API_KEY="你的兼容端点 key"
python eval/harness/run_eval.py --provider openai_chat_compat --base-url "https://api.deepseek.com/v1" --list-models
python eval/harness/run_eval.py --real --provider openai_chat_compat --base-url "https://api.deepseek.com/v1" --model "deepseek-chat" --smoke
```

确认冒烟跑通后，再跑全量真实评测：

```powershell
python eval/harness/run_eval.py --real --provider openai --model gpt-5 --repeats 3
```

`~/.codex/config.toml` 和 `~/.codex/auth.json` 是 Codex CLI 的个人配置；TRACE 不依赖也不读取其中的 key。运行评测时优先用上面的环境变量，避免把个人凭据和项目代码绑定。

如果未来要接企业网关或其它官方兼容的 Responses 端点，只给 `openai` 覆盖 base URL：

```powershell
python eval/harness/run_eval.py --real --provider openai --base-url "https://api.example.com/v1" --model "模型id" --smoke
```

## 核心能力

### 工具层

Agent 只能通过白名单工具访问项目：

- `list_files`
- `read_file`
- `analyze_project`
- `write_test_file`
- `run_pytest`

`write_test_file` 和 `run_pytest` 都做 canonical path 校验，生成测试只能写入受控目录。`run_pytest` 通过自定义 pytest 插件返回结构化结果，包括 `case_results`、`failures`、`collection_errors` 和 `failure_type`。

### Agent 策略

当前实现三种策略：

- Direct：单任务生成并执行，不做规划，不做 Reflection。
- Plan-and-Execute：先拆分多个测试目标，再逐个生成和执行，不做 Reflection。
- ReAct + Reflection：单任务生成和执行，失败后允许一次受约束 Reflection。

Reflection 的红线：

- 不修改业务代码。
- 不删除核心断言。
- 不用 `pytest.skip` / `xfail` 掩盖失败。
- 不把具体断言改成空洞断言。
- 如果无法在不削弱断言的前提下变绿，应保留失败并标记疑似业务缺陷。

系统用静态 contract guard 辅助拦截常见“为了变绿而削弱测试”的行为。

### Trace 与报告

运行过程会记录：

- stage/status 变化；
- 工具调用和观察；
- LLM 结构化输出及重试日志；
- pytest 用例级结果；
- Reflection 结果；
- 最终 Markdown/JSON 报告。

评测和报告共享同一套 final attempt 选择逻辑，避免报告口径和重放口径分叉。

## 评测方法

M2 评测遵循污染隔离：

1. 在干净 demo 项目上运行 Agent，生成最终测试集。
2. 如果策略允许 Reflection，只在干净代码上进行一次修复。
3. 保存最终测试内容。
4. 为每个 seeded bug 物化独立变体目录。
5. 把干净期定型的同一批测试重放到变体目录。
6. 只有“同一 nodeid 在干净代码通过、在变体上发生 assertion failure”才算捕获。

核心指标：

- `seeded_bug_capture_rate`
- `clean_false_positive_rate`
- `cost_per_captured_bug`
- `avg_tokens`
- `avg_tool_calls`

`eval/demo/bugs.py` 中定义了 6 个 seeded bug，覆盖比较符翻转、边界错误、漏校验、错状态码四类。

## 当前评测结果

数据来自 scripted MockLLM 作者：它刻意建模三种策略的典型行为，用来验证 harness 能否区分捕获、漏判、假阳性和 Reflection 修复路径。

| 策略                | 捕获率      | 假阳性率 | 反思 | 平均 token | 平均工具调用 |
| ------------------- | ----------- | -------- | ---- | ---------- | ------------ |
| Direct v1           | 0.83（5/6） | 1.00     | 否   | 610        | 3            |
| Plan-and-Execute v1 | 1.00（6/6） | 0.00     | 否   | 2293       | 13           |
| ReAct+Reflection v1 | 1.00（6/6） | 0.00     | 是   | 1342       | 5            |

这张表能说明：

- harness 的污染隔离、nodeid 对齐、捕获率和假阳性计算可运行；
- 三种策略的控制流差异能反映到工具调用成本上；
- scripted MockLLM 可以覆盖 Direct 漏判、Plan 全覆盖、ReAct 反思修复等路径。

这张表不能说明：

- ReAct 在真实 LLM 下必然优于 Direct 或 Plan；
- 当前 token/cost 是真实模型成本；
- demo bug 捕获率可以直接外推到真实项目。

换成真实 LLM 后，指标口径不变，但捕获率、假阳性率和成本需要重新测。

## 安全边界

V1 使用本地 subprocess 执行 pytest。它提供独立工作目录、路径白名单和硬超时，但 **不是安全沙箱**。

生成测试本质上仍是 Python 代码。不能把当前执行器当作隔离恶意代码的安全边界。真正的容器隔离、禁网、资源限制和 Runner 加固属于后续版本。

## 已知边界

- 当前只覆盖 Python/FastAPI + pytest。
- 默认评测使用 MockLLM/scripted author；真实 OpenAI / Chat Compat API 结果需要另跑 `--real`。
- 当前不落数据库，不提供正式 FastAPI 管理 API。
- 当前评测走脚本，不落评测表。
- 弱断言识别仍有边界，例如 `assert x == x`、`assert result is not None`、断言藏在永不执行分支等。

## 后续建议

短期优先级：

1. B 线接入数据库、API 和状态机持久化。
2. C 线基于 report/trace/comparison JSON 做页面展示。
3. A 线用真实 OpenAI 或 Chat Compat API 跑一轮 smoke，再决定是否跑全量真实评测。

真实 LLM 已通过 `LLMClient` adapter 接入，现有工具契约、trace、Reflection contract 和 eval harness 不需要改。
