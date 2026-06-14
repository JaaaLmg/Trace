# TRACE C 线前端设计方案

> 第一版讨论稿。依据 `需求分析.md`、`系统设计.md`、`V1实施清单.md`、`A_HANDOFF.md` 和 `B_HANDOFF.md` 整理。  
> 目标不是做一个漂亮壳子，而是把 TRACE 的核心能力 `Agent trace + report + pytest result` 讲清楚、跑顺、展示准。

## 1. 设计判断

TRACE 前端的第一原则：**trace 是主角，report 是结论，project/plan/run 只是入口。**

参考图的价值不在油滴动效，而在这几件事：

- 用纸面网格、轻边框、低饱和色，把复杂系统做成“可审计的档案”。
- 用编号章节拆组件，让视觉规范和业务界面保持同一种语言。
- 用 Topic tabs、Message paper、Task Board 这类结构，把信息分层，而不是堆卡片。
- 用小标签、细分割线、等宽文本，让技术细节看起来稳定可信。

TRACE 应该吸收这套气质，但必须更工程化。不要把 Agent 做成聊天机器人，也不要把首页做成营销页。用户打开前端后，第一眼就应该看到一次测试运行的状态、过程和结果。

## 2. V1 范围

### 必做

1. Project List
   - 展示被测项目。
   - 能进入项目最近一次 run 或创建测试计划入口。

2. Run Console
   - 展示 run 主状态、阶段、策略、模型、tokens、tool calls、pytest summary。
   - 展示 Agent trace timeline。
   - 点击 trace step 后展示结构化详情。

3. Report View
   - 展示最终报告摘要、metrics、risk notes。
   - 明确区分“run 失败”和“pytest 用例失败”。

4. Pytest Results
   - 展示用例级结果。
   - 支持按 `passed`、`failed`、`error`、`skipped`、`unmatched` 过滤。

### 可后置

1. Comparison View
   - 读取 `eval/results/comparison.json`。
   - 展示策略对比、捕获率、假阳性、token、耗时。

2. Test Plan Editor
   - V1 可以很薄，只要能输入目标、选择 snapshot 和 strategy，并触发 run。

3. Demo 应用骨架展示
   - 可以放在 README 或后续 demo 页面，不抢 V1 主屏。

### 明确不做

- 不做 Docker/Runner 管理界面。
- 不做 Prompt/Tool Schema 版本管理界面。
- 不做 eval datasets/experiments 正式管理界面。
- 不宣称 subprocess 是安全沙箱。
- 不把当前 MockLLM token 当真实模型成本展示。
- 不做油滴动画作为 V1 必要项。

## 3. 信息架构

V1 推荐路由：

```text
/projects
/projects/:projectId
/runs/:runId
/runs/:runId/report
/runs/:runId/pytest
/comparison        # 后置
```

第一版可以把 `report` 和 `pytest` 做成 Run Console 内部 tabs，不一定拆成独立页面。更建议的结构：

```text
Run Console
  Overview
  Trace
  Report
  Pytest
  Artifacts
```

理由很简单：一次 run 才是 V1 的核心对象。围绕 run 聚合信息，用户不需要在多个页面里找上下文。

## 4. 第一屏设计

第一屏命名为 **Run Console**。

### 布局

桌面端默认使用“摘要栏 + 主内容 + 可覆盖抽屉”，不要做死三栏等分。

```text
┌──────────────────────────────────────────────────────────────┐
│ Top Bar: TRACE / Project / Snapshot / Strategy / Run actions  │
├───────────────┬─────────────────────────────┬────────────────┤
│ Run Summary   │ Trace Timeline              │ Step Detail     │
│ Project       │ plan                         │ payload JSON    │
│ Status        │ tool_call                    │ input/output    │
│ Stage         │ generation                   │ error/details   │
│ Metrics       │ reflection                   │ related result  │
│ Actions       │ report                       │                │
└───────────────┴─────────────────────────────┴────────────────┘
```

其中左侧 Run Summary 只能是窄粘性栏，或在中等屏幕下提升为增强 Top Bar。右侧 Step Detail 必须优先采用 Drawer：点击 Timeline 节点后从右侧滑出，覆盖部分 Timeline，而不是强行挤出第三栏。

硬约束：

- 1440px 宽度下，Trace Timeline 不能低于 560px。
- Step Detail 展开时，可读宽度不能低于 520px。
- JSON/code 区域允许横向滚动，但不能导致整页横向滚动。
- 1200px 以下直接收起左侧摘要栏，用顶部摘要条 + 右侧 Drawer。
- 900px 以下进入移动端上下结构。
- Drawer 右上角必须有关闭按钮。
- 点击 Drawer 外部的 Overlay 必须关闭 Drawer。
- Drawer 边缘使用 `1px solid var(--border)`，并加向左弥散阴影，确保它从纸面背景中浮起来。

移动端使用上下结构：

```text
Top Bar
Run Summary
Tabs: Trace / Report / Pytest / Artifacts
Selected detail drawer
```

### 首屏重点

- 当前 run 是否还在运行。
- 当前 stage 到哪一步。
- 有多少 trace steps。
- pytest 是通过、失败，还是系统没有跑到 pytest。
- report 是否已经生成。
- 如果失败，失败是系统错误还是测试用例失败。

## 5. 视觉语言

### 整体风格

关键词：

- 纸面
- 审计
- 克制
- 工程化
- 可追踪

页面应该像一份运行档案，而不是一个 SaaS 营销后台。

### 背景

- 页面底色：暖白纸面。
- 背景加很淡的网格线，表达系统蓝图感。
- 主内容区域不要做大面积渐变。
- 不使用装饰性圆球、光斑、漂浮 blob。
- V1 明确拒绝暗黑模式。TRACE 当前视觉隐喻是纸面档案，强行反转会破坏产品气质，也会放大状态色和代码块对比问题。

### 字体

字体分工必须明确，告别圆体：

- 内容文字：`Source Han Serif SC` / `思源宋体`，英文内容可用 `EB Garamond` 兜底，用于报告正文、说明段落、Markdown 内容。
- UI 外壳：`Inter`，用于导航、按钮、表格标签、状态 badge、表单和工具栏。
- 代码/工具：`JetBrains Mono`，用于 payload、nodeid、路径、ID、trace index、代码块。
- 不使用圆体、手写体或过度装饰字体。
- 内容行高必须不低于 1.6，Report 正文建议 1.7 左右。
- 数字指标、耗时、token、pytest 表格中的数字列必须启用等宽数字：`font-feature-settings: "tnum" 1;`。

示例：

```css
--font-serif: "Source Han Serif SC", "Noto Serif CJK SC", "EB Garamond", Georgia, serif;
--font-ui: Inter, ui-sans-serif, system-ui, sans-serif;
--font-mono: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
```

### 色彩

不能照搬参考图的全暖色，否则 TRACE 会像文艺模板。建议保留纸感，同时加入工程状态色。

| Token | Hex | 用途 |
| --- | --- | --- |
| `paper` | `#fbfaf7` | 页面底色 |
| `panel` | `#ffffff` | 面板底色 |
| `border` | `#e5e0d8` | 分割线和边框 |
| `ink` | `#252422` | 主文字 |
| `muted` | `#77716a` | 次级文字 |
| `amber` | `#d7a44c` | running / reflection |
| `sage` | `#7f9b83` | passed / completed |
| `red` | `#b86b5d` | failed / error |
| `blue` | `#6f8ea8` | tool_call / system |
| `violet` | `#8b7aa8` | generation / model |
| `code` | `#f3f1ed` | code/payload 背景 |

### 圆角和阴影

- 卡片圆角最大 8px。
- 工具按钮用 6px 或圆形图标按钮。
- 阴影只用于层级，不做发光。
- 卡片不能套卡片。页面区块是全宽布局，卡片只用于 repeated item、modal、详情面板。

## 6. 核心组件

### 6.1 Top Bar

内容：

- TRACE 标识。
- 当前 project。
- 当前 snapshot。
- 当前 strategy。
- API/mock 数据源状态。
- Run / Retry / Cancel 按钮。

交互：

- Run 按钮触发 `POST /api/v1/test-plans/{plan_id}/runs`。
- Retry 按钮触发 `POST /api/v1/test-runs/{run_id}/retry`。
- Cancel 按钮触发 `POST /api/v1/test-runs/{run_id}/cancel`。

按钮建议用 lucide icons：

- Run: `Play`
- Retry: `RotateCcw`
- Cancel: `Square`
- Refresh: `RefreshCw`

### 6.2 Run Summary Panel

展示字段：

- `status`
- `stage`
- `strategy_version_id`
- `runtime_snapshot`
- `strategy_snapshot`
- `total_tokens`
- `total_cost`
- `tool_call_count`
- `pytest_summary`
- `error_code`
- `error_message`

注意：

- `failed` 是运行流程失败，不等于 pytest 有失败用例。
- run `completed` 但 pytest failed 是正常情况，报告里解释测试结果。
- `stage` 只在 `status = running` 时作为主进度展示。

### 6.3 Stage Rail

固定阶段只用于展示主干生命周期：

```text
queued -> preparing -> analyzing -> planning -> generating -> executing -> reflecting -> reexecuting -> summarizing -> completed
```

表现：

- 已完成阶段用细实线。
- 当前阶段用 amber 小圆点。
- 跳过阶段保持浅灰。
- 失败阶段用 red。

不要把它做成花哨进度条。它是状态机的可视化，不是加载动画。

Stage Rail 不能假设 Agent 永远线性前进。虽然 V1 文档要求 Reflection 只允许一次，UI 仍要能兜住异常数据或未来扩展：

- 主干阶段保持一行。
- 如果出现重复阶段，使用角标，例如 `reexecuting x2`。
- 如果 trace 中出现循环，不拉长主进度条，改在 Trace Timeline 中体现真实顺序。
- 如果未来支持多轮 Reflection，再引入 Git Graph 式分支视图；V1 不提前复杂化。

### 6.4 Trace Timeline

数据来源：

```text
GET /api/v1/test-runs/{run_id}/trace-steps
```

排序：

```text
step_index ASC
```

每个 step 展示：

- `step_index`
- `step_type`
- `name`
- `status`
- `tool_name`
- `tokens`
- `duration_ms`
- `input_summary`
- `output_summary`

`step_type` 颜色建议：

| step_type | 表现 |
| --- | --- |
| `plan` | amber |
| `tool_call` | blue |
| `observation` | sage 或 red |
| `generation` | violet |
| `reflection` | amber + 虚线 |
| `report` | ink |
| `system` | muted |

点击 step 后，右侧 Step Detail 展示：

- `payload`
- `error`
- 原始 input/output summary
- 关联 attempt
- 关联 pytest failure

`payload` 必须使用 JSON viewer 或格式化 code block，不能直接塞一坨文本。

JSON Viewer 是 V1 体验重点，最低要求：

- 支持层级折叠。
- 默认折叠第二级以下内容。
- 对数组显示 item count。
- 悬浮显示 Copy 按钮。
- 复制目标包括当前节点 JSON 和完整 payload。
- 超过 600px 高度时内部滚动，不挤压整个页面。
- 层级超过 10 层时必须截断深层渲染，显示 `depth limit reached`。
- 单个数组超过 50 项时，默认只渲染前 50 项，底部显示 `[... N more items]`。
- 如果后续需要展示超大 payload，再引入虚拟滚动；V1 至少要有截断兜底。

### 6.5 Topic Tabs

借鉴参考图的 Topic tab，但替换为 TRACE 的对象：

```text
Overview | Trace | Report | Pytest | Artifacts
```

规则：

- tab 顶部轻圆角，底部无边框，像贴在纸面上的档案标签。
- 当前 tab 左侧有 6px 小圆点。
- 不使用厚重高亮块。

### 6.6 Report Paper

数据来源：

```text
GET /api/v1/test-runs/{run_id}/report
```

展示：

- `summary`
- `metrics`
- `risk_notes`
- `markdown_uri`
- `json_uri`

Markdown 展示风格：

- 放在同一张纸面内。
- 标题、引用、列表、表格、代码块保持轻量附录感。
- 表格允许横向滚动，不做厚重表格卡片。
- code block 使用浅灰背景，保留复制按钮位置。
- Metrics 禁止直接暴露 API 字段名。`final_passed`、`tool_call_count` 这类 snake_case 只能存在于类型和接口层，界面必须映射为 `通过用例`、`工具调用` 等用户可读文案。

### 6.7 Pytest Results Table

数据来源：

```text
GET /api/v1/test-runs/{run_id}/pytest-results
```

列：

- `nodeid`
- `mapping_status`
- `status`
- `duration_ms`
- `failure_type`
- `failure_message`
- `traceback_hash`

交互：

- 状态筛选。
- 搜索 nodeid。
- 点击失败行展开 `stdout_excerpt`、`stderr_excerpt`、`failure_message`。

表格设计：

- 紧凑。
- 行高稳定。
- 失败行只做左边细红线，不整行大红底。
- `nodeid` 用 monospace。

### 6.8 Artifacts List

数据来源：

```text
GET /api/v1/test-runs/{run_id}/artifacts
```

展示：

- `artifact_type`
- `uri`
- `content_hash`
- `size_bytes`
- `metadata`

V1 只做列表和复制路径。后续再做文件预览。

## 7. 数据接入策略

前期先 mock，后期切真实 API。

### Mock 数据来源

- `eval/results/comparison.json`
- `eval/results/comparison.md`
- A 运行生成的 report JSON/Markdown artifact
- `TraceStep`、`RunEvent`、`TestRunRecord` 假数据

### API 数据来源

| 页面区域 | API |
| --- | --- |
| Project List | `GET /api/v1/projects` |
| Project Detail | `GET /api/v1/projects/{project_id}` |
| Snapshots | `GET /api/v1/projects/{project_id}/snapshots` |
| Test Plan | `GET /api/v1/test-plans/{plan_id}` |
| Run Summary | `GET /api/v1/test-runs/{run_id}` |
| Trace Timeline | `GET /api/v1/test-runs/{run_id}/trace-steps` |
| Events | `GET /api/v1/test-runs/{run_id}/events` |
| Attempts | `GET /api/v1/test-runs/{run_id}/attempts` |
| Pytest Results | `GET /api/v1/test-runs/{run_id}/pytest-results` |
| Artifacts | `GET /api/v1/test-runs/{run_id}/artifacts` |
| Report | `GET /api/v1/test-runs/{run_id}/report` |
| Strategy | `GET /api/v1/strategy-versions/{version_id}` |

### 轮询

V1 没有 WebSocket 要求。Run Console 对 `queued` 和 `running` 状态做轮询即可。

建议：

- `queued/running`：每 1500ms 轮询 run summary、trace、events。
- `completed/failed/cancelled`：停止轮询。
- 手动 refresh 按钮始终可用。

轮询必须避免视觉抽搐：

- 新增 trace step 用 200ms 内的轻微 fade-in + slide-up。
- 已存在 step 更新时只更新局部字段，不整块重挂。
- 列表 key 必须使用 `trace_step.id` 或稳定的 `step_index`。
- 不允许刷新时出现整页闪白。
- running 状态允许一个极慢 amber pulse，这是 V1 唯一允许的状态动效。

Retry 触发新 run 时必须使用 Stale Data UX：

- 旧 run 的 Timeline、Report 和 Pytest Results 不要瞬间清空。
- 旧内容加 `opacity: 0.5` 和 `pointer-events: none`，表示正在被新 run 替换。
- 顶部出现极细加载进度条。
- 等新 run 返回第一个 `queued` 状态后，再无缝替换为新 run 数据。
- 如果 retry 创建失败，恢复旧数据并显示错误提示。

## 8. 页面文案口径

可以说：

- TRACE records the full Agent trace.
- TRACE shows generation, execution, reflection and report stages.
- Pytest failures are preserved as structured case results.
- Mock evaluation demonstrates that the harness can distinguish capture, miss and false positive.

不要说：

- ReAct 一定优于 Direct 或 Plan-and-Execute。
- 当前 token 就是真实模型成本。
- 当前 subprocess 是安全沙箱。
- Demo 捕获率能外推到真实项目。

中文界面推荐文案：

- `运行档案`
- `过程轨迹`
- `结构化失败`
- `反思修复`
- `最终报告`
- `产物`
- `系统错误`
- `测试失败`

## 9. HTML 预览方向

后续 `c_frontend_preview.html` 建议做成静态视觉稿，不接 API。

预览结构：

```text
01 / VISUAL SPEC
  色板、字体、状态点

02 / RUN CONSOLE
  三栏布局 mock

03 / TRACE TIMELINE
  step 列表 + detail panel

04 / REPORT PAPER
  summary + metrics + markdown section

05 / PYTEST RESULTS
  compact table
```

静态示例 run：

```text
project: async_demo_project
strategy: ReAct + Reflection
model: MockLLM
status: completed
pytest: 4 passed, 1 failed
tokens: 2384
tool calls: 5
duration: 8.4s
```

示例 trace：

```text
01 system        run_enqueued
02 tool_call     analyze_project
03 generation    generate pytest file
04 tool_call     write_test_file
05 tool_call     run_pytest
06 reflection    fix import and assertion direction
07 tool_call     run_pytest
08 report        build final report
```

## 10. 实现建议

技术栈按 V1 文档：

```text
Vue 3 + TypeScript + Vite
```

建议目录：

```text
frontend/
  src/
    api/
      client.ts
      runs.ts
      projects.ts
    components/
      AppShell.vue
      TopicTabs.vue
      StatusDot.vue
      StageRail.vue
      TraceTimeline.vue
      TraceStepDetail.vue
      ReportPaper.vue
      PytestResultsTable.vue
    mock/
      run.ts
      traceSteps.ts
      report.ts
      pytestResults.ts
    pages/
      ProjectListPage.vue
      RunConsolePage.vue
    styles/
      tokens.css
      base.css
    types/
      api.ts
```

优先级：

1. 先做静态 mock 页面。
2. 再抽组件。
3. 再接 API client。
4. 最后补空状态、错误态、加载态。

不要一上来引入复杂状态管理。V1 的页面围绕单个 run 展示，简单 composable 足够。

## 11. 验收标准

### 视觉验收

- 第一屏能看出这是 TRACE，不是 Oil 模板换皮。
- 页面气质接近纸面档案，但状态色足够清楚。
- trace timeline 是视觉重心。
- Report 和 Pytest Results 能自然接在 trace 后面。
- 没有卡片套卡片。
- 移动端文字不溢出，表格可横向滚动。

### 功能验收

- 能从项目进入 run。
- 能看到 run 当前 `status/stage`。
- 能按 `step_index` 展示 trace。
- 能展开 trace payload。
- 能展示 report metrics 和 risk notes。
- 能展示 pytest 用例级结果。
- run 运行中能轮询刷新。
- run 结束后停止轮询。

### 口径验收

- 不把 pytest failure 误判成系统 run failed。
- 不声称安全沙箱。
- 不声称 MockLLM 成本是真实成本。
- 不把 Comparison 做成 V1 必需主线。

## 12. 防翻车硬约束

这些约束来自静态视觉稿和真实开发之间最容易翻车的地方，后续实现时必须单独验收。

### 12.1 Worst Case Layout

必须专门做满载态：

- JSON payload 很长。
- 嵌套层级至少 4 层。
- 有失败 step。
- 有长 traceback。
- Pytest 表格中存在很长 nodeid。

验收点：

- 页面不横向溢出。
- Drawer 展开后 JSON 至少有 520px 可读宽度。
- Trace Timeline 不被挤到只剩标题。
- 代码块横向滚动只发生在代码块内部。

### 12.2 Stage Rail 退化策略

Stage Rail 只表达主干状态，不表达完整 Agent 行为。完整行为以 Trace Timeline 为准。

验收点：

- 重复阶段显示角标，不把主进度条拉爆。
- skipped 阶段用浅灰，不依赖颜色单独传达含义。
- failed 阶段同时使用红色、图标和文字，不只靠红点。

### 12.3 色彩可访问性

低饱和背景可以保留，状态指示必须拉高对比。

验收点：

- 状态文本和背景满足 WCAG 2.1 AA。
- 小圆点不能作为唯一状态信号。
- Badge 使用“文字 + 图标/形状 + 15% 同色背景”。
- passed、failed、running、skipped 在色弱模式下仍能区分。

建议状态色：

| 状态 | 前景 | 背景 |
| --- | --- | --- |
| `completed/passed` | `#2f6b3f` | `rgba(47, 107, 63, 0.14)` |
| `running/reflection` | `#8a5a00` | `rgba(215, 164, 76, 0.18)` |
| `failed/error` | `#9f3a2f` | `rgba(159, 58, 47, 0.14)` |
| `tool/system` | `#315f7d` | `rgba(49, 95, 125, 0.14)` |
| `skipped/muted` | `#5f5a52` | `rgba(95, 90, 82, 0.12)` |

V1 固定 Light Mode，不做 Dark Mode。后续如果要做暗色主题，必须重新定义整套隐喻和 token，不允许简单颜色反转。

### 12.4 JSON Viewer

JSON Viewer 不能只是语法高亮。

验收点：

- 默认折叠第二级以下。
- 每个对象/数组节点可以展开收起。
- hover 有 Copy。
- 大 payload 在详情面板内部滚动。
- 复制动作有轻量反馈。
- 深度超过 10 层时截断。
- 数组超过 50 项时只渲染前 50 项，并显示剩余数量提示。

### 12.5 轮询与动效

运行中的页面要有生命感，但不能吵。

验收点：

- 新 step 进入时 200ms 内轻微过渡。
- running 小圆点极慢 pulse。
- 数据刷新不闪白。
- 不使用大面积 loading skeleton 覆盖已有结果。
- retry 新 run 时旧数据进入 stale 态，等待新 run `queued` 后再替换。

### 12.6 Report Typography

Report 是展示给人看的结论页，排版要单独验收。

验收点：

- 标题和正文使用 Source Han Serif / EB Garamond，但不压过数据层级。
- 正文行高至少 1.6，建议 1.7。
- 列表缩进稳定。
- blockquote、table、code block 都像轻量附录，不像另一套组件库。
- 表格可以横向滚动。
- 数字指标和表格数字列开启 tabular numbers。

## 13. 当前结论

C 线不要从“大而全后台”开始。正确路线是：

```text
先把 Run Console 做准 -> 再把 Report 做漂亮 -> 再补 Pytest Results -> 最后做 Comparison
```

这个顺序最符合 V1 文档，也最能展示项目价值。TRACE 的强点不是表单 CRUD，而是一次 AI 测试生成运行能被完整追踪、解释和复盘。
