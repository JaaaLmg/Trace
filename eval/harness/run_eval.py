# 评测入口：跑「N 策略 × N 重复」的干净生成 + 全变体重放，产出对比表 + 捕获矩阵。
# 既可被测试调用（run_full_eval），也可独立运行：
#   python eval/harness/run_eval.py                 # MockLLM（可复现 harness 验证）→ comparison.{md,json}
#   python eval/harness/run_eval.py --real --smoke  # 真实 LLM 冒烟（1 策略×1 重复，不落文件）
#   python eval/harness/run_eval.py --real          # 真实 LLM 全量 → comparison_real.{md,json}
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# 允许独立运行：把 backend 和 TRACE 根塞进 sys.path
_TRACE_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (str(_TRACE_ROOT / "backend"), str(_TRACE_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.agents.llm import MockLLM  # noqa: E402
from app.agents.seeds import seed_list  # noqa: E402

from eval.demo.bugs import TASKS  # noqa: E402
from eval.harness import dataset, metrics  # noqa: E402
from eval.harness.authors import demo_author  # noqa: E402
from eval.harness.runner import CleanRun, run_one  # noqa: E402


def _format_run_error(run) -> str:
    message = run.error_message or ""
    if len(message) > 500:
        message = message[:497] + "..."
    if run.error_code and message:
        return f"{run.error_code}: {message}"
    return run.error_code or message or "unknown error"


def _failed_smoke_runs(result: dict) -> list:
    return [
        run
        for runs in result["runs_by_strategy"].values()
        for run in runs
        if run.status != "completed"
    ]


def _merge_task_runs(strategy_spec, repeat: int, task_runs: list[CleanRun]) -> CleanRun:
    first_failed = next((run for run in task_runs if run.status != "completed"), None)
    merged = CleanRun(
        strategy_id=strategy_spec.id,
        strategy_name=strategy_spec.name,
        repeat=repeat,
        status=first_failed.status if first_failed else "completed",
        files={path: content for run in task_runs for path, content in run.files.items()},
        clean_passed=set().union(*(run.clean_passed for run in task_runs)) if task_runs else set(),
        clean_failed=any(run.clean_failed for run in task_runs),
        n_cases=sum(run.n_cases for run in task_runs),
        tokens=sum(run.tokens for run in task_runs),
        tool_calls=sum(run.tool_calls for run in task_runs),
        reflection_used=any(run.reflection_used for run in task_runs),
        error_code=first_failed.error_code if first_failed else None,
        error_message=first_failed.error_message if first_failed else None,
    )
    for run in task_runs:
        merged.variants.update(run.variants)
    return merged


def run_full_eval(workdir, repeats: int = 3, *, make_llm=None, author=demo_author, specs=None) -> dict:
    # make_llm 工厂 () -> LLMClient。缺省 = MockLLM(author)，mock 路径与现状完全一致。
    if make_llm is None:

        def make_llm():
            return MockLLM(author)

    bugs = dataset.load_bugs()
    spec_list = specs if specs is not None else seed_list()
    runs_by_strategy: dict = {}
    for spec in spec_list:
        runs_by_strategy[spec.id] = []
        for r in range(repeats):
            task_runs = []
            for task_id, task in TASKS.items():
                task_bugs = [bug for bug in bugs if bug.task_id == task_id]
                task_runs.append(
                    run_one(
                        spec,
                        make_llm,
                        r,
                        Path(workdir) / spec.id / f"rep{r}" / task_id,
                        task_bugs,
                        target_scope=task.targets,
                        goal=task.goal,
                    )
                )
            runs_by_strategy[spec.id].append(_merge_task_runs(spec, r, task_runs))
    rows = metrics.aggregate(runs_by_strategy, total_in_scope=len(bugs))
    matrix = metrics.capture_matrix(runs_by_strategy, bugs)
    return {
        "rows": rows,
        "capture_matrix": matrix,
        "table_md": metrics.comparison_table_md(rows),
        "matrix_md": metrics.capture_matrix_md(matrix, bugs, runs_by_strategy),
        "runs_by_strategy": runs_by_strategy,
    }


def run_full_eval_via_service(*, repeats: int = 3, llm_override: dict | None = None) -> dict:
    # V2 平台路径：CLI 只是薄包装，clean/replay/metrics 的核心逻辑走 DB experiment service。
    from sqlalchemy.orm import Session

    from app.db.session import get_engine
    from app.services.evaluation_seed import DEMO_DATASET_ID, seed_demo_dataset
    from app.services.experiments import create_experiment, get_experiment_metrics, run_experiment
    from app.services.strategies import seed_strategy_versions

    with Session(get_engine()) as session:
        seed_strategy_versions(session)
        seed_demo_dataset(session)
        experiment = create_experiment(
            session,
            name="cli-v2-eval",
            dataset_id=DEMO_DATASET_ID,
            strategy_version_ids=["sv-direct-v1", "sv-plan-v1", "sv-react-v1"],
            repeat_count=repeats,
            llm_override=llm_override,
        )
        run_experiment(session, experiment["id"])
        service_metrics = get_experiment_metrics(session, experiment["id"])

    class _Bug:
        def __init__(self, bug_id: str) -> None:
            self.id = bug_id
            self.bug_type = bug_id

    rows = service_metrics["rows"]
    matrix = service_metrics["capture_matrix"]
    strategy_names = {row["strategy_id"]: row["strategy_name"] for row in rows}
    runs_by_strategy = {sid: [type("_Run", (), {"strategy_name": name})()] for sid, name in strategy_names.items()}
    bugs = [_Bug(bug_id) for bug_id in matrix]
    return {
        "rows": rows,
        "capture_matrix": matrix,
        "table_md": metrics.comparison_table_md(rows),
        "matrix_md": metrics.capture_matrix_md(matrix, bugs, runs_by_strategy),
        "runs_by_strategy": runs_by_strategy,
        "experiment": service_metrics["experiment"],
    }


def main() -> None:
    # Windows 控制台默认 GBK，矩阵里的 ✓/✗ 会崩；切到 utf-8（文件写入本就是 utf-8）
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="TRACE 策略评测")
    parser.add_argument("--real", action="store_true", help="接真实 LLM API（默认走 MockLLM）")
    parser.add_argument(
        "--provider",
        default=None,
        help="真实模型 provider：openai=官方 Responses；openai_chat_compat=/chat/completions 兼容端点",
    )
    parser.add_argument("--model", default=None, help="真实模型 ID；openai 默认 gpt-5，openai_chat_compat 必须显式提供或走环境变量")
    parser.add_argument("--repeats", type=int, default=3, help="每策略重复次数")
    parser.add_argument("--temperature", type=float, default=None, help="真实模型采样温度；不传则使用模型默认值")
    parser.add_argument("--max-output-tokens", type=int, default=None, help="真实模型最大输出 token；不传则使用 provider 默认值")
    parser.add_argument(
        "--reasoning-effort",
        default=None,
        choices=["minimal", "low", "medium", "high"],
        help="真实模型 reasoning effort；不传则读 TRACE_LLM_REASONING_EFFORT/OPENAI_REASONING_EFFORT",
    )
    parser.add_argument("--base-url", default=None, help="LLM API base URL；openai_chat_compat 必须提供或走环境变量")
    parser.add_argument("--list-models", action="store_true", help="列出当前 provider 的 /models 返回值后退出")
    parser.add_argument("--smoke", action="store_true", help="冒烟：仅 1 策略×1 重复验证连通，不落对比文件")
    args = parser.parse_args()

    out_dir = _TRACE_ROOT / "eval" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    runtime_config = None
    if args.real or args.list_models:
        from app.agents.llm_config import load_llm_config

        try:
            runtime_config = load_llm_config()
        except ValueError as e:
            raise SystemExit(str(e)) from e

    if args.list_models:
        from app.agents.llm_factory import create_llm

        provider_arg = args.provider or (runtime_config.provider if runtime_config is not None else None)
        model_arg = args.model or (runtime_config.model if runtime_config is not None else None)
        base_url_arg = args.base_url or (runtime_config.base_url if runtime_config is not None else None)
        api_key_arg = runtime_config.api_key if runtime_config is not None else None
        try:
            llm = create_llm(provider_arg, model_arg, api_key=api_key_arg, base_url=base_url_arg)
        except ValueError as e:
            raise SystemExit(str(e)) from e
        try:
            models = llm.list_models()
        finally:
            llm.close()  # 列模型用完即关，别泄漏 httpx 连接
        if not models:
            print("(no models returned)")
            return
        for model_id in models:
            print(model_id)
        return

    if args.real:
        from app.agents.llm_factory import create_llm, normalize_provider, resolve_model

        try:
            provider = normalize_provider(args.provider or (runtime_config.provider if runtime_config is not None else None))
        except ValueError as e:
            raise SystemExit(str(e)) from e
        model = resolve_model(provider, args.model or (runtime_config.model if runtime_config is not None else None))
        if not model:
            raise SystemExit("openai_chat_compat 需要 --model 或 TRACE_LLM_MODEL/OPENAI_CHAT_COMPAT_MODEL")
        api_key = runtime_config.api_key if runtime_config is not None else None
        temperature = (
            args.temperature
            if args.temperature is not None
            else (runtime_config.temperature if runtime_config is not None else None)
        )
        max_output_tokens = (
            args.max_output_tokens
            if args.max_output_tokens is not None
            else (runtime_config.max_output_tokens if runtime_config is not None else None)
        )
        base_url = args.base_url or (runtime_config.base_url if runtime_config is not None else None)
        reasoning_effort = args.reasoning_effort or (
            runtime_config.reasoning_effort if runtime_config is not None else None
        )

        # 单一来源：实跑参数与落库快照（strategy_snapshot.model_params）同出这一份 dict，
        # 避免「快照写 temperature=0.2、实际跑的是别的值」这种自相矛盾的复现记录。
        model_params: dict = {}
        if temperature is not None:
            model_params["temperature"] = temperature
        if max_output_tokens is not None:
            model_params["max_output_tokens"] = max_output_tokens
        if base_url:
            model_params["base_url"] = base_url
        if reasoning_effort:
            model_params["reasoning_effort"] = reasoning_effort
        client_params = dict(model_params)
        if api_key:
            client_params["api_key"] = api_key

        # 提前构造一次做校验（chat_compat 缺 base_url、reasoning_effort 冲突等），失败立即退出；
        # 校验实例用完即关，不留泄漏的连接。
        try:
            create_llm(provider, model, **client_params).close()
        except ValueError as e:
            raise SystemExit(str(e)) from e

        def make_llm():
            return create_llm(provider, model, **client_params)

    else:
        make_llm = None  # run_full_eval 默认 MockLLM

    specs = seed_list()
    if args.real:
        specs = [
            s.model_copy(update={"model_provider": provider, "model_name": model, "model_params": model_params})
            for s in specs
        ]
    if args.smoke:
        specs = specs[:1]
    repeats = 1 if args.smoke else args.repeats
    if args.smoke:
        result = run_full_eval(_TRACE_ROOT / "eval" / ".work", repeats=repeats, make_llm=make_llm, specs=specs)
    else:
        service_override = None
        if args.real:
            service_override = {
                "provider": provider,
                "model": model,
                "temperature_policy": {"mode": "fixed", "value": temperature}
                if temperature is not None
                else {"mode": "strategy_default"},
                "model_params": {},
            }
            if max_output_tokens is not None:
                service_override["max_output_tokens"] = max_output_tokens
            if reasoning_effort:
                service_override["model_params"]["reasoning_effort"] = reasoning_effort
            if base_url:
                service_override["model_params"]["base_url"] = base_url
        else:
            service_override = {"provider": "mock", "model": "mock-1"}
        result = run_full_eval_via_service(repeats=repeats, llm_override=service_override)

    # 冒烟：只验证真实调用能跑通、JSON 能解析、run 能完成；不覆盖任何对比文件
    if args.smoke:
        if args.real:
            tag = f"real:{specs[0].model_provider}:{specs[0].model_name}"
        else:
            tag = "mock"
        failed_runs = _failed_smoke_runs(result)
        print(f"== SMOKE（{tag}，1 策略×1 重复）==")
        for runs in result["runs_by_strategy"].values():
            for run in runs:
                line = (
                    f"  {run.strategy_name}: status={run.status} tokens={run.tokens} "
                    f"tool_calls={run.tool_calls} cases={run.n_cases} reflection={run.reflection_used}"
                )
                if run.status != "completed":
                    line += f" error={_format_run_error(run)}"
                print(line)
        if failed_runs:
            print()
            print("SMOKE failed; comparison table omitted because failed runs are not evaluable.")
            raise SystemExit(1)
        print()
        print(result["table_md"])
        print()
        print(result["matrix_md"])
        return

    experiment_info = result.get("experiment") or {}
    bug_count = len(dataset.load_bugs())

    if args.real:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        json_path, md_path = out_dir / "comparison_real.json", out_dir / "comparison_real.md"
        provider = specs[0].model_provider
        model = specs[0].model_name
        header = [
            f"# TRACE 策略评测对比（真实模型 {model}）",
            "",
            f"> provider={provider}　model={model}　temperature={temperature}　reasoning_effort={reasoning_effort}　repeats={args.repeats}　生成于 {stamp}",
            f"> experiment_id={experiment_info.get('id', 'unknown')}",
            f"> 数据来自 `eval/harness/run_eval.py --real`：3 策略 × {args.repeats} 重复，干净代码生成 → {bug_count} 个 bug 变体重放。",
            "> 与 MockLLM 的 comparison.md 并存：本表是真实测量，捕获/假阳性/反思/token 皆来自真模型，逐次可能不同。",
            "",
        ]
    else:
        json_path, md_path = out_dir / "comparison.json", out_dir / "comparison.md"
        header = [
            "# TRACE 策略评测对比（demo seeded bugs）",
            "",
            f"> 数据来自 `eval/harness/run_eval.py`：3 策略 × 3 重复，干净代码生成 → {bug_count} 个 bug 变体重放。",
            "> demo 用 scripted MockLLM 作者建模三种策略的典型行为；harness 与指标计算与 LLM 无关。",
            "",
        ]

    payload = {"rows": result["rows"], "capture_matrix": result["capture_matrix"]}
    if experiment_info:
        payload["experiment"] = experiment_info
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md = header + ["## 策略对比", "", result["table_md"], "", "## 逐 bug 捕获矩阵", "", result["matrix_md"], ""]
    md_path.write_text("\n".join(md), encoding="utf-8")
    print(result["table_md"])
    print()
    print(result["matrix_md"])


if __name__ == "__main__":
    main()
