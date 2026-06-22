# Prompt 工程：system 角色 + 各阶段消息构造。prompt 正文放代码里（prompt_ref 版本化），
# 建 run 时由 orchestrator 冻结进 strategy_snapshot（V1实施清单 §3：不允许只存版本号）。
from __future__ import annotations

from app.agents.llm import Message
from app.schemas.agent import PlanItemDraft
from app.schemas.evaluation import ContextCompletenessEvidence
from app.schemas.strategy import StrategyVersionSpec
from app.schemas.tools import AnalyzeProjectOutput, RunPytestOutput

SYSTEM_PROMPT_V1 = """你是 TRACE 的测试生成 Agent，专为 Python/FastAPI 项目生成 pytest 测试。
原则：
- 只依据给你的项目分析摘要写测试，不臆测不存在的接口；
- 测试要可执行、断言有业务意义，覆盖正常路径和关键边界；
- 只输出要求的 JSON，不要解释、不要 markdown 围栏。"""

REFLECTION_CONTRACT_V1 = """Reflection 红线（违反即判失败）：
- 只允许修生成测试自身的问题：import 路径、fixture、调用签名、测试数据构造、断言写反、TestClient 用法；
- 禁止修改业务源码；
- 禁止删除核心断言、改成空洞断言（如只断言 200、断言 True）；
- 禁止用 pytest.skip / 条件跳过 / 宽泛 except 吞掉失败；
- 禁止为了变绿而迁就明显错误的业务行为。
若不削弱断言就无法通过，停止修复，把 suspected_code_bug 置 true，并在 fix_reason 说明疑点。"""


def build_system_prompt(strategy: StrategyVersionSpec) -> str:
    # V1 只有 v1；后续按 strategy.prompt_ref 选不同正文
    return SYSTEM_PROMPT_V1


def summarize_analysis(analysis: AnalyzeProjectOutput, limit: int = 40) -> str:
    """给 LLM 的项目摘要：结构化要点，绝不贴整仓源码。"""
    lines: list[str] = []
    if analysis.routes:
        lines.append("FastAPI 路由：")
        for r in analysis.routes[:limit]:
            lines.append(f"  - {r.method} {r.path}  (handler={r.handler}, file={r.file})")
    if analysis.functions:
        lines.append("函数：")
        for fn in analysis.functions[:limit]:
            lines.append(f"  - {fn.signature}  (file={fn.file})")
    if analysis.models:
        lines.append("Pydantic 模型：")
        for m in analysis.models[:limit]:
            lines.append(f"  - {m.name}  (file={m.file})")
    if analysis.existing_tests:
        lines.append("已有测试：")
        for t in analysis.existing_tests[:limit]:
            lines.append(f"  - {t.path}（{len(t.test_functions)} 个测试函数）")
    if analysis.warnings:
        lines.append("分析告警：")
        for w in analysis.warnings[:limit]:
            lines.append(f"  - {w}")
    return "\n".join(lines) or "（分析未发现可测对象）"


def summarize_context_completeness(context: ContextCompletenessEvidence | None, limit: int = 8) -> str:
    if context is None:
        return "上下文完整性：\n  - status: unknown\n  - context_incomplete: true"

    lines = [
        "上下文完整性：",
        f"  - status: {context.status}",
        f"  - context_incomplete: {str(context.context_incomplete).lower()}",
    ]
    if context.missing_targets:
        lines.append("  - missing_targets:")
        for target in context.missing_targets[:limit]:
            lines.append(f"    - {target}")
    if context.risk_notes:
        lines.append("  - risk_notes:")
        for note in context.risk_notes[:limit]:
            lines.append(f"    - {note}")
    if context.context_incomplete:
        lines.append(
            "  - 生成要求：上下文不完整时，缺失或截断的源码不能当作 oracle 证据；"
            "不要为不可见行为写 pytest.raises、精确异常消息或边界期望。"
        )
    return "\n".join(lines)


_GEN_SCHEMA_HINT = (
    '返回 JSON：{"test_file_content":"完整 pytest 文件源码字符串",'
    '"cases":[{"test_name":"test_xxx","target_route":null,"target_function":"fn","assertion_summary":"断言要点"}],'
    '"coverage_notes":"覆盖说明","risks":"风险/假设"}。'
    'test_file_path 可省略，文件路径由系统决定。'
)

GEN_PREFIX = "生成一个 pytest 测试文件。"

GEN_CONTRACT = """生成硬约束（违反会被 PIPELINE_REJECT）：
- 每个检查必须写成 assert 或 pytest.raises；不要写裸表达式，例如 response.json()["total"] == 270.0。
- 不要写 `pytest.raises(Exception/BaseException)`；异常 oracle 必须是源码或已有测试能证明的具体异常类型。
- 成功路由测试不能只断言 2xx status_code，必须断言响应 JSON 的业务字段和值。
- 边界/负数/阈值/异常路径的预期必须来自目标源码片段；源码没有 raise 证据时不要写 pytest.raises。
- `pytest.raises(..., match=...)` 的 match 必须来自同一输入的源码 raise 或已有测试证据；只有相似场景、相似错误类型时不要写精确异常消息。
- 单次生成保持紧凑：优先 4-8 个高价值测试函数，最多 12 个；不要枚举大量同质输入。
- 若目标函数签名第一个参数是 self/cls，它是内部方法：不要把它当自由函数调用，不要猜测构造内部类；优先通过已有测试或公开 API 间接触达该行为。
- 不要从包根导入未在项目分析/已有测试/源码片段中证明可导出的内部类；只有看见类定义和 __init__ 调用证据时才允许手动构造对象。
- 对 `/x/{param}` 这类 path 参数路由，不要把 `/x/` 空 path 段当成 `param=""` 的 handler 业务用例。
- 不要给测试函数添加未知参数；只能使用 pytest 内置 fixture（如 monkeypatch/tmp_path）或项目分析中列出的 fixture。没有 `client` fixture 证据时，FastAPI 路由测试应在测试内构造 `TestClient(app)`，不要把 `client` 写成函数参数。
- 使用 unittest.mock.patch(..., new_value) 时不要额外声明 mock 参数；可优先使用 pytest 内置 monkeypatch。
- cases[*].test_name 必须对应真实 test 函数名；参数化测试可使用 test_x[...]。"""

GEN_RETRY_INSTRUCTION = """上次生成被 Contract Guard 拒绝。
只修复 violations 指出的测试契约问题：删除或修正无源码证据的边界/异常 oracle、补强断言、修正 cases 元数据或 fixture 使用。
如果 violation 是 `fixture 缺少项目证据：client`，不要继续声明 `client` 参数；改为导入 FastAPI app 并在测试内使用 `TestClient(app)` 构造局部 client。
如果 violation 是 `目标绑定不匹配 plan item`，必须围绕本次聚焦任务的 target_type/target_ref 重写测试和 cases，不要切换到其它函数或路由。
如果 violation 是 `路由响应 oracle 与目标源码行为不一致`，必须按 handler 源码和被调用函数重新计算响应 JSON 期望值；不要手写与源码条件矛盾的折扣、阈值或状态。
不要降低有源码证据的业务断言；继续只返回要求的 GenerationOutput JSON。"""

GEN_RETRY_OUTPUT_INVARIANTS = """重试输出不变量：
- 必须返回完整 GenerationOutput JSON，不要只返回 diff 或解释。
- `test_file_content` 必须是完整 pytest 文件源码。
- `cases` 必须与真实 pytest 测试函数一一对应；每个 case 必须保留 `test_name`、`assertion_summary`，并填写 `target_function` 或 `target_route`。
- 不要输出 `test_file_path: null`；路径由系统决定。
- 只修正 violation 指向的问题，不要切换目标、删除有证据的业务断言或新增无证据 fixture/request field/oracle。"""


def generation_retry_fix_hints(violations: list[str]) -> list[str]:
    """把 Guard violation 翻译成可执行修复动作；Guard 本身仍是最终边界。"""
    hints: list[str] = []
    for violation in violations:
        hint = _generation_retry_fix_hint(violation)
        if hint and hint not in hints:
            hints.append(hint)
    return hints


def _generation_retry_fix_hint(violation: str) -> str | None:
    if "无法解析为 Python" in violation or "invalid syntax" in violation:
        return "先修 Python 语法：检查括号、逗号和字符串引号；JSON 示例优先写成单引号包裹的 Python 字符串（如 '{\"key\": \"value\"}'），内部换行用 \\n 或三引号，确保 test_file_content 可被 ast.parse。"
    if "真实测试函数缺少 cases 声明" in violation or "cases 声明未对应真实测试函数" in violation:
        return "修正 cases 映射：逐个读取 test_file_content 中的真实 pytest 函数名，并让 cases[*].test_name 与函数名完全一致；参数化测试使用基础函数名即可。"
    if "缺少 assertion_summary" in violation:
        return "补齐每个 case 的 assertion_summary，写清断言的业务字段、输入和期望值。"
    if "缺少 target_function/target_route" in violation or "目标绑定不匹配 plan item" in violation:
        return "修正目标绑定：函数任务填写 target_function；路由任务填写 target_route，并确保测试请求仍命中本次 plan item 的目标。"
    if "测试函数 fixture 缺少项目证据" in violation:
        return "删除无证据 fixture 参数；FastAPI 路由测试在测试内导入 app 并用 TestClient(app) 构造局部 client，pytest 内置 fixture 如 monkeypatch/tmp_path 可继续使用。"
    if "请求字段缺少证据" in violation or "请求字段缺少模型证据" in violation:
        return "只使用模型 schema、路由 query 参数或源码证据中出现的 request 字段；删除 made-up json/params/data 字段。"
    if "业务 oracle" in violation:
        return "补强路由业务 oracle：除状态码外，必须断言响应 JSON 中有源码/response model 证据的字段和值。"
    if "请求路径不匹配目标路由" in violation or "请求方法不匹配目标路由" in violation:
        return "修正 TestClient 请求 method/path，使其与 target_route 或 plan item 的 method/path 一致。"
    if "空 path 参数" in violation:
        return "不要用空 path 段测试 path 参数；选择源码常量或 fixture 证据中的有效 path 参数值。"
    if "内部方法不能当自由函数调用" in violation:
        return "目标签名含 self/cls 时，不要直接调用该函数名；改用已有测试或源码片段中出现的公开 API 间接覆盖该内部方法，并保持 cases 的 target_function 绑定本次目标。"
    if "构造类缺少可调用性证据" in violation:
        return "删除无证据的内部类构造；不要从包根导入未证明导出的类。若源码片段没有类定义和 __init__ 签名，优先使用已有测试中出现的 public API。"
    if "宽泛异常" in violation:
        return "不要使用 pytest.raises(Exception/BaseException)；改成源码或已有测试能证明的具体异常类型。若没有具体异常证据，删除异常 oracle。"
    if "没有可见 raise 证据" in violation or "异常类型" in violation or "异常消息" in violation:
        return "异常 oracle 必须来自目标源码片段中的 raise 语句；没有 raise 证据时改测返回值或状态，不要写 pytest.raises。"
    if "源码行为" in violation or "路由响应 oracle" in violation or "响应模型字段" in violation:
        return "按目标源码、依赖函数和 response model 重新计算期望；删除与源码条件、字段或状态码矛盾的 oracle。"
    if "空洞断言" in violation or "没有任何断言" in violation:
        return "把空洞断言替换为具体业务断言，断言返回值、异常、状态码和响应 JSON 字段中的可证事实。"
    if "重新定义被测目标" in violation:
        return "不要在测试文件里重定义被测函数、路由 handler 或 app；必须 import 项目里的真实目标。"
    return None

PLAN_INSTRUCTION = (
    '把目标拆成若干测试任务，返回 JSON：'
    '{"items":[{"index":0,"target_type":"function|route|module","target_ref":"标识","goal":"该任务测什么","planned_assertions":["..."]}]}。'
    '最多 4 个 items，优先选择覆盖面最大、oracle 最明确的任务；'
    'target_ref 必须是项目分析中出现的精确函数名、路由（METHOD path）或模块/文件标识；'
    '不要把 strict mode、边界条件、场景描述拼进 target_ref，这些细节放进 goal/planned_assertions。'
)

REFLECT_JSON_TAIL = (
    '返回 JSON：{"fixed_content":"修复后的完整文件源码","fix_reason":"为何这么修",'
    '"changed_points":["改了哪些"],"lowered_assertion_strength":false,"suspected_code_bug":false}'
)


def prompt_bundle(strategy: StrategyVersionSpec) -> dict:
    """冻结进 strategy_snapshot 的完整 prompt 正文。
    只存 prompt_ref 不够：以后改这里的任何模板，历史 run 就不可复现了（V1实施清单 §3）。"""
    return {
        "prompt_ref": strategy.prompt_ref,
        "version": "v1",
        "system": SYSTEM_PROMPT_V1,
        "reflection_contract": REFLECTION_CONTRACT_V1,
        "plan_instruction": PLAN_INSTRUCTION,
        "generate_prefix": GEN_PREFIX,
        "generate_contract": GEN_CONTRACT,
        "generate_retry_instruction": GEN_RETRY_INSTRUCTION,
        "generate_retry_output_invariants": GEN_RETRY_OUTPUT_INVARIANTS,
        "generate_schema_hint": _GEN_SCHEMA_HINT,
        "reflect_json_tail": REFLECT_JSON_TAIL,
    }


def build_plan_messages(
    strategy: StrategyVersionSpec, analysis: AnalyzeProjectOutput, scope: list[str], goal: str
) -> list[Message]:
    user = (
        f"TASK: PLAN\n目标：{goal}\n范围：{scope or '整个项目'}\n\n"
        f"项目分析：\n{summarize_analysis(analysis)}\n\n"
        f"{PLAN_INSTRUCTION}"
    )
    return [Message("system", build_system_prompt(strategy)), Message("user", user)]


def build_generate_messages(
    strategy: StrategyVersionSpec,
    analysis: AnalyzeProjectOutput,
    scope: list[str],
    goal: str,
    item: PlanItemDraft | None,
    source_context: str = "",
    context_completeness: ContextCompletenessEvidence | None = None,
) -> list[Message]:
    focus = f"\n本次聚焦任务：{item.goal}（target={item.target_type}:{item.target_ref}）" if item else ""
    callable_guidance = _callable_guidance(analysis, item)
    callable_block = f"\n可调用性约束：\n{callable_guidance}\n" if callable_guidance else ""
    source_block = f"\n目标源码片段：\n{source_context}\n" if source_context else "\n目标源码片段：\ncontext_incomplete\n"
    context_block = summarize_context_completeness(context_completeness)
    user = (
        f"TASK: GENERATE\n总目标：{goal}\n范围：{scope or '整个项目'}{focus}\n\n"
        f"项目分析：\n{summarize_analysis(analysis)}\n\n"
        f"{callable_block}"
        f"{source_block}\n"
        f"{context_block}\n\n"
        f"{GEN_CONTRACT}\n"
        f"{GEN_PREFIX}{_GEN_SCHEMA_HINT}"
    )
    return [Message("system", build_system_prompt(strategy)), Message("user", user)]


def _callable_guidance(analysis: AnalyzeProjectOutput, item: PlanItemDraft | None) -> str:
    if item is None or item.target_type != "function":
        return ""
    target = item.target_ref.rsplit(".", 1)[-1]
    for fn in analysis.functions:
        if fn.name != target and fn.signature.split("(", 1)[0].strip() != target:
            continue
        lines = [f"- 目标签名：{fn.signature}（file={fn.file}）"]
        if _signature_first_param(fn.signature) in {"self", "cls"}:
            lines.append(
                "- 这是绑定到对象/类的内部方法；不要把它当自由函数调用，"
                "也不要猜测内部类构造参数。若上下文没有完整类定义和 __init__，"
                "应通过已有测试或公开 API 间接触达该行为。"
            )
        else:
            lines.append("- 只按签名中可见参数调用；不要新增签名外参数或无证据 fixture。")
        return "\n".join(lines)
    return ""


def _signature_first_param(signature: str) -> str | None:
    if "(" not in signature or ")" not in signature:
        return None
    params = signature.split("(", 1)[1].split(")", 1)[0].strip()
    if not params:
        return None
    first = params.split(",", 1)[0].strip()
    return first.split(":", 1)[0].split("=", 1)[0].strip()


def build_reflect_messages(
    strategy: StrategyVersionSpec,
    analysis: AnalyzeProjectOutput,
    failed_content: str,
    pytest_result: RunPytestOutput,
    relevant_source: str = "",
) -> list[Message]:
    fails = "\n".join(
        f"  - {f.nodeid} [{f.failure_type}] {f.exc_type}: {f.message}" for f in pytest_result.failures[:20]
    )
    collect = "\n".join(f"  - {c.nodeid} [{c.failure_type}] {c.message}" for c in pytest_result.collection_errors[:20])
    failure_context = _failure_context_block(pytest_result)
    # 反斜杠不能进 f-string 的 {} 表达式（Py<3.12），相关源码块先拼好
    source_block = f"相关源码：\n{relevant_source}\n" if relevant_source else "相关源码：\ncontext_incomplete\n"
    user = (
        f"TASK: REFLECT\n首轮生成的测试没通过，请按契约修复一次。\n\n"
        f"{REFLECTION_CONTRACT_V1}\n\n"
        f"当前测试文件：\n```python\n{failed_content}\n```\n\n"
        f"失败用例：\n{fails or '（无）'}\n收集错误：\n{collect or '（无）'}\n\n"
        f"失败上下文：\n{failure_context}\n\n"
        f"项目分析：\n{summarize_analysis(analysis)}\n"
        f"{source_block}\n"
        f"{REFLECT_JSON_TAIL}"
    )
    return [Message("system", build_system_prompt(strategy)), Message("user", user)]


def build_generate_retry_messages(
    base_messages: list[Message],
    *,
    violations: list[str],
    previous_content: str,
) -> list[Message]:
    violation_lines = "\n".join(f"- {violation}" for violation in violations)
    fix_hints = generation_retry_fix_hints(violations)
    hint_lines = "\n".join(f"- {hint}" for hint in fix_hints) or "- 按 violations 原文修正，不新增无证据测试目标或 oracle。"
    user = (
        f"{GEN_RETRY_INSTRUCTION}\n\n"
        f"violations:\n{violation_lines}\n\n"
        f"针对性修复动作：\n{hint_lines}\n\n"
        f"{GEN_RETRY_OUTPUT_INVARIANTS}\n\n"
        f"上次生成的测试文件：\n```python\n{previous_content}\n```\n\n"
        f"{GEN_PREFIX}{_GEN_SCHEMA_HINT}"
    )
    return [*base_messages, Message("user", user)]


def _failure_context_block(pytest_result: RunPytestOutput, *, limit: int = 8, traceback_chars: int = 1200) -> str:
    rows: list[str] = []
    for detail in [*pytest_result.failures, *pytest_result.collection_errors][:limit]:
        location = _failure_location(detail.file, detail.line)
        header = f"- {detail.nodeid or '<collect>'} [{detail.failure_type}] {detail.exc_type or ''} {location}".strip()
        rows.append(header)
        if detail.message:
            rows.append(f"  message: {_clip(detail.message, 300)}")
        if detail.traceback:
            rows.append("  traceback:")
            rows.append(_indent(_clip(detail.traceback, traceback_chars), "    "))
    return "\n".join(rows) if rows else "（无）"


def _failure_location(path: str | None, line: int | None) -> str:
    if path and line:
        return f"@ {path}:{line}"
    if path:
        return f"@ {path}"
    return ""


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...<truncated>"


def _indent(text: str, prefix: str) -> str:
    return "\n".join(prefix + line for line in text.splitlines())
