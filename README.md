<p align="center">
  <img src="assets/logo.svg" alt="TRACE logo" width="450">
</p>

TRACE（Test-generation Reflective Agent for Comparative Evaluation）是一个面向 Python/FastAPI 项目的测试生成、执行、追踪和评测平台。

它把“让大模型生成 pytest 测试”扩展成一条完整工程链路：分析项目、生成测试、执行 pytest、读取结构化失败、进行受约束反思、记录 trace、生成报告，并用 seeded bug 评测不同策略的效果。

## 项目简介

TRACE 关注三个问题：

- 生成的测试是否能真实运行，而不是只停留在文本层面。
- 测试失败后，Agent 是否能基于结构化 pytest 结果做有限、可追踪的修复。
- 不同测试生成策略在捕获 seeded bug、误报率、工具调用和 token 成本上的差异。

系统当前主要面向 Python/FastAPI + pytest 项目，提供后端 API、异步执行 worker、PostgreSQL 持久化、Redis 队列和 Vue 前端可视化。

## 核心功能

- 项目代码分析：通过白名单工具读取和分析目标项目。
- 测试生成：根据策略生成 pytest 测试文件。
- 测试执行：运行 pytest，并收集用例级结构化结果。
- 反思修复：在约束内基于失败信息改进测试。
- 运行追踪：记录 stage、tool call、LLM 输出、pytest 结果和 artifacts。
- 报告生成：输出可读报告和结构化指标。
- 策略对比：支持 Direct、Plan-and-Execute、ReAct + Reflection 等策略。
- seeded bug 评测：在干净项目与缺陷变体之间重放同一批测试，计算捕获率和误报率。
- Web 可视化：查看项目、运行详情、trace timeline、pytest 结果、报告和对比矩阵。

## 技术栈

- Backend：FastAPI, SQLAlchemy, Alembic
- Database：PostgreSQL
- Queue：Celery, Redis
- Frontend：Vue 3, TypeScript, Vite
- Test/Eval：pytest, seeded bug evaluation
- LLM：OpenAI Responses API 或 OpenAI Chat Completions 兼容接口

## 快速开始

建议使用 Python 3.11、Node.js 18+ 和 Docker。

安装 Python 依赖：

```powershell
cd D:\GitRepo\专业实训\TRACE
conda activate trace
pip install -r backend/requirements.txt
```

启动 PostgreSQL 和 Redis：

```powershell
cd D:\GitRepo\专业实训\TRACE
docker compose up -d
```

复制本地环境配置：

```powershell
Copy-Item .env.example .env.local
```

默认配置如下：

```text
TRACE_DB_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/trace_test
TRACE_REDIS_URL=redis://127.0.0.1:6379/0
TRACE_API_HOST=127.0.0.1
TRACE_API_PORT=8000
```

初始化数据库和基础数据：

```powershell
cd D:\GitRepo\专业实训\TRACE\backend
conda activate trace

python scripts/init_db.py
python scripts/seed_strategies.py
python scripts/seed_eval_demo.py
```

## 配置真实 LLM

普通 API run 默认从 `backend/llm.config.json` 读取模型配置。可以从示例文件复制：

```powershell
cd D:\GitRepo\专业实训\TRACE\backend
Copy-Item llm.config.example.json llm.config.json
```

示例配置：

```json
{
  "provider": "openai",
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-5",
  "api_key": "你的 API key",
  "temperature": 0,
  "max_output_tokens": 8192
}
```

也可以通过环境变量配置：

```powershell
$env:TRACE_LLM_PROVIDER="openai"
$env:TRACE_LLM_MODEL="gpt-5"
$env:TRACE_LLM_API_KEY="你的 API key"
$env:TRACE_LLM_BASE_URL="https://api.openai.com/v1"
```

使用 OpenAI Chat Completions 兼容接口时，显式设置兼容 provider、模型和 base URL：

```powershell
$env:TRACE_LLM_PROVIDER="openai_chat_compat"
$env:TRACE_LLM_MODEL="兼容端点模型名"
$env:TRACE_LLM_API_KEY="你的兼容端点 key"
$env:TRACE_LLM_BASE_URL="https://api.example.com/v1"
```

`backend/llm.config.json` 已被 Git 忽略，不要提交真实 API key。

## 正式运行

正式运行需要同时启动 API、Worker 和前端。PostgreSQL 与 Redis 需要保持运行。

终端 1：启动后端 API。

```powershell
cd D:\GitRepo\专业实训\TRACE\backend
conda activate trace
python scripts/run_api.py
```

默认地址：

```text
http://127.0.0.1:8000
```

终端 2：启动异步 Worker。

```powershell
cd D:\GitRepo\专业实训\TRACE\backend
conda activate trace
python scripts/run_worker.py
```

Windows 下 worker 默认使用 Celery `solo` pool，适合本地开发和演示运行。

终端 3：启动前端。

```powershell
cd D:\GitRepo\专业实训\TRACE\frontend
npm install
npm run dev
```

默认前端地址：

```text
http://127.0.0.1:5186
```

前端 dev server 会把 `/api` 代理到 `http://127.0.0.1:8000`。如果后端端口不同，可以启动前端前指定代理目标：

```powershell
$env:VITE_TRACE_API_PROXY_TARGET="http://127.0.0.1:8001"
npm run dev
```

如果只查看已经落库的历史结果，通常只需要 PostgreSQL、后端 API 和前端；不需要启动 Redis、Worker 或真实 LLM API。新建实验或继续执行任务时，必须启动 Redis、Worker，并保证 LLM 配置可用。

## 前端使用流程

1. 打开前端首页。
2. 进入项目列表，选择已有项目或创建新项目。
3. 创建测试计划或实验运行。
4. 选择测试生成策略和运行参数。
5. 启动 run，等待状态从 queued/running 进入 completed 或 failed。
6. 查看运行详情中的 trace、pytest results、artifacts 和 report。
7. 在对比页面查看不同策略的评测指标和 seeded bug 捕获矩阵。

如果只想预览静态前端效果，可以使用 demo 数据源：

```powershell
cd D:\GitRepo\专业实训\TRACE\frontend
$env:VITE_TRACE_DATA_SOURCE="demo"
npm run dev
```

demo 数据只用于前端展示，不代表真实 API、数据库、pytest 或 LLM 状态。

## 测试与评测

运行后端测试：

```powershell
cd D:\GitRepo\专业实训\TRACE
conda activate trace
python -m pytest backend/tests -q --rootdir backend -p no:cacheprovider
```

运行前端构建检查：

```powershell
cd D:\GitRepo\专业实训\TRACE\frontend
npm run build
```

在 API 和 Worker 已启动后，可以运行异步链路 smoke 验证：

```powershell
cd D:\GitRepo\专业实训\TRACE\backend
conda activate trace
python scripts/smoke_async_run.py
```

运行 seeded bug 评测：

```powershell
cd D:\GitRepo\专业实训\TRACE
conda activate trace
python eval/harness/run_eval.py
```

评测结果会生成到：

```text
eval/results/comparison.md
eval/results/comparison.json
```

## 项目结构

```text
TRACE/
  backend/
    app/
      agents/       # Agent 策略、LLM 适配、报告与契约守卫
      api/          # FastAPI 路由
      core/         # 错误码和基础 ID
      db/           # 数据库配置、engine、session
      models/       # SQLAlchemy ORM 模型
      recorders/    # 运行记录落库
      repositories/ # 数据访问层
      schemas/      # API、工具、trace、策略等数据契约
      services/     # 项目、运行、实验、评测等业务服务
      tools/        # list/read/analyze/write/run_pytest 工具
      workers/      # Celery worker 与异步任务
    alembic/        # 数据库迁移
    scripts/        # 初始化、启动、seed、smoke 脚本
    tests/          # 后端测试
  frontend/
    src/
      api/          # 前端 API client
      components/   # 运行详情、trace、pytest、报告等组件
      demo/         # 静态演示数据
      pages/        # 页面入口
  eval/
    demo/           # seeded bug 评测用 demo 项目
    harness/        # 评测执行与指标聚合
    results/        # 评测输出
```

## 已知限制

- 当前主要覆盖 Python/FastAPI + pytest 项目。
- 本地 pytest 执行器有路径白名单和超时控制，但不是强安全沙箱。
- 生成测试本质上仍是 Python 代码，不应在不可信项目上直接运行。
- 真实 LLM 的效果、成本和稳定性依赖所选模型与 API 服务。
- demo 数据只用于前端预览，判断真实系统状态应以后端 API、数据库和运行记录为准。
