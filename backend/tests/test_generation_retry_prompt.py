from __future__ import annotations

from app.agents.llm import Message
from app.agents.prompts import build_generate_retry_messages, generation_retry_fix_hints, prompt_bundle
from app.agents.seeds import SEED_STRATEGIES


def test_generation_retry_fix_hints_cover_common_real_api_contract_rejections():
    hints = generation_retry_fix_hints(
        [
            "真实测试函数缺少 cases 声明：test_real",
            "cases 声明未对应真实测试函数：test_declared",
            "测试函数 fixture 缺少项目证据：client",
            "请求字段缺少模型证据：made_up",
            "路由测试缺少业务 oracle（只有 2xx status_code 断言）：test_health",
            "路由测试请求路径不匹配目标路由：test_price",
            "test_price 的目标绑定不匹配 plan item：route:GET /price/{item}",
            "异常类型与目标源码不一致：test_validate",
            "生成测试无法解析为 Python：invalid syntax. Perhaps you forgot a comma? (<unknown>, line 46)",
        ]
    )

    joined = "\n".join(hints)
    assert "cases[*].test_name" in joined
    assert "TestClient(app)" in joined
    assert "request 字段" in joined
    assert "响应 JSON" in joined
    assert "method/path" in joined
    assert "target_route" in joined
    assert "pytest.raises" in joined
    assert "ast.parse" in joined
    assert "JSON 示例" in joined


def test_generate_retry_message_keeps_previous_content_and_output_invariants():
    messages = build_generate_retry_messages(
        [Message("system", "system"), Message("user", "TASK: GENERATE")],
        violations=[
            "测试函数 fixture 缺少项目证据：client",
            "cases 声明未对应真实测试函数：test_declared",
        ],
        previous_content="def test_declared(client):\n    assert client.get('/health').status_code == 200\n",
    )

    retry = messages[-1].content
    assert "针对性修复动作" in retry
    assert "重试输出不变量" in retry
    assert "完整 GenerationOutput JSON" in retry
    assert "不要输出 `test_file_path: null`" in retry
    assert "def test_declared(client)" in retry
    assert "TestClient(app)" in retry
    assert "cases[*].test_name" in retry


def test_prompt_bundle_freezes_generate_retry_invariants():
    bundle = prompt_bundle(SEED_STRATEGIES["direct"])

    assert "generate_retry_output_invariants" in bundle
    assert "完整 GenerationOutput JSON" in bundle["generate_retry_output_invariants"]
    assert ".py 文件路径" in bundle["plan_instruction"]
    assert "不要写 function" in bundle["plan_instruction"]
    assert "每个 item 只能覆盖一个 target_ref" in bundle["plan_instruction"]
    assert "只能为该 target 生成 pytest 函数和 cases" in bundle["generate_contract"]
