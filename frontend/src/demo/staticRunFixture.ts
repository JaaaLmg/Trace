import type {
  ComparisonResult,
  ProjectOut,
  ProjectSnapshotOut,
  RunBundle,
  StrategyVersionOut,
  TestPlanOut
} from "../types/api";

const now = "2026-06-14T08:00:00.000Z";

export const demoProjects: ProjectOut[] = [
  {
    id: "proj-async-demo",
    name: "async_demo_project",
    description: "FastAPI demo target used by TRACE V1 smoke runs.",
    source_type: "local_path",
    repo_url: null,
    local_path: "D:/GitRepo/专业实训/TRACE/backend/tests/fixtures/async_demo_project",
    default_branch: null,
    language: "python",
    framework: "fastapi",
    status: "active",
    created_at: now,
    updated_at: now
  },
  {
    id: "proj-shop-clean",
    name: "eval_demo_shop",
    description: "Seeded bug evaluation target with clean and variant directories.",
    source_type: "local_path",
    repo_url: null,
    local_path: "D:/GitRepo/专业实训/TRACE/eval/demo/clean",
    default_branch: null,
    language: "python",
    framework: "fastapi",
    status: "active",
    created_at: now,
    updated_at: now
  }
];

export const demoSnapshots: ProjectSnapshotOut[] = [
  {
    id: "snap-async-demo",
    project_id: "proj-async-demo",
    source_kind: "local_path",
    root_path: "D:/GitRepo/专业实训/TRACE/backend/tests/fixtures/async_demo_project",
    content_hash: "sha256:demo-async",
    created_at: now
  }
];

export const demoPlans: TestPlanOut[] = [
  {
    id: "plan-checkout-boundaries",
    project_id: "proj-async-demo",
    name: "Checkout pricing boundary tests",
    target_scope: ["calc.py", "tests/generated"],
    goal: "Generate pytest cases for checkout pricing, discount boundaries and invalid input.",
    budget: { timeout_seconds: 120, allow_reflection: true },
    output_options: { save_full_trace: true },
    default_strategy_version_id: "sv-react-v1",
    status: "active",
    created_at: now,
    updated_at: now
  }
];

export const demoStrategy: StrategyVersionOut = {
  id: "sv-react-v1",
  name: "ReAct+Reflection v1",
  workflow_type: "react_reflection",
  model_provider: "demo_static",
  model_name: "Static Demo Fixture",
  model_params: { temperature: 0, scripted_author: "react_reflection" },
  allow_reflection: true,
  max_tool_calls: 8,
  prompt_ref: "react_v1",
  tool_schema_ref: "tools_v1"
};

export const staticRunFixture: RunBundle = {
  run: {
    id: "run-demo-react-001",
    test_plan_id: "plan-checkout-boundaries",
    retry_of_run_id: null,
    project_snapshot_id: "snap-async-demo",
    runtime_profile_id: null,
    strategy_version_id: "sv-react-v1",
    runtime_snapshot: {
      python: "3.11.9",
      executor: "local_subprocess",
      network_policy: "best_effort_disabled",
      root_path: "D:/GitRepo/专业实训/TRACE/backend/tests/fixtures/async_demo_project"
    },
    strategy_snapshot: {
      name: "ReAct+Reflection v1",
      model_provider: "demo_static",
      model_name: "Static Demo Fixture",
      prompt_ref: "react_v1",
      prompt_text_frozen: "Analyze project, generate pytest, execute, and reflect once without weakening assertions.",
      model_params: { temperature: 0 }
    },
    status: "completed",
    stage: null,
    started_at: "2026-06-14T08:01:00.000Z",
    finished_at: "2026-06-14T08:01:08.400Z",
    total_tokens: 2384,
    total_cost: null,
    tool_call_count: 5,
    pytest_summary: { collected: 5, passed: 4, failed: 1, skipped: 0, duration_ms: 2418 },
    error_code: null,
    error_message: null,
    created_at: "2026-06-14T08:00:58.000Z"
  },
  traceSteps: [
    {
      id: "step-01",
      run_id: "run-demo-react-001",
      attempt_id: null,
      step_index: 1,
      step_type: "system",
      name: "run_enqueued",
      input_summary: "Run entered Celery queue trace_test_runs.",
      output_summary: "Worker accepted run and prepared local execution context.",
      tool_name: null,
      payload: {
        event: "run_enqueued",
        queue: "trace_test_runs",
        run_id: "run-demo-react-001",
        status_after: "queued"
      },
      tokens: null,
      duration_ms: 31,
      status: "ok",
      error: null,
      created_at: "2026-06-14T08:01:00.000Z"
    },
    {
      id: "step-02",
      run_id: "run-demo-react-001",
      attempt_id: "attempt-initial",
      step_index: 2,
      step_type: "tool_call",
      name: "analyze_project",
      input_summary: "Inspect target scope calc.py and generated tests directory.",
      output_summary: "Found pricing function, FastAPI route and no conflicting generated tests.",
      tool_name: "analyze_project",
      payload: {
        input: {
          snapshot_id: "snap-async-demo",
          target_scope: ["calc.py", "tests/generated"]
        },
        output: {
          files: [
            { path: "calc.py", kind: "source", size: 842 },
            { path: "tests/test_calc.py", kind: "test", size: 510 }
          ],
          routes: [{ method: "POST", path: "/checkout", handler: "checkout", file: "api.py" }],
          functions: [
            { name: "calculate_total", signature: "calculate_total(items, coupon=None)", file: "calc.py" }
          ],
          models: [{ name: "CheckoutRequest", file: "api.py" }],
          warnings: []
        }
      },
      tokens: null,
      duration_ms: 638,
      status: "ok",
      error: null,
      created_at: "2026-06-14T08:01:01.000Z"
    },
    {
      id: "step-03",
      run_id: "run-demo-react-001",
      attempt_id: "attempt-initial",
      step_index: 3,
      step_type: "generation",
      name: "generate pytest file",
      input_summary: "Use ReAct plan to cover discount, invalid coupon and tax boundary.",
      output_summary: "Generated five pytest cases with route and function assertions.",
      tool_name: null,
      payload: {
        attempt_logs: [
          {
            attempt: 1,
            messages: [
              { role: "system", content: "You are TRACE. Generate tests through tools only." },
              { role: "user", content: "Cover checkout pricing, invalid coupons, and tax boundary behavior." }
            ],
            raw_text: "{\"tests\":[\"test_checkout_happy_path\",\"test_checkout_applies_coupon_and_tax\"]}",
            error: null
          }
        ],
        value: {
          generated_file: "tests/generated/test_checkout_generated.py",
          planned_assertions: [
            "200 response for valid checkout",
            "discount applies before tax",
            "invalid coupon returns 400",
            "empty cart clamps total to zero"
          ]
        }
      },
      tokens: 913,
      duration_ms: 1204,
      status: "ok",
      error: null,
      created_at: "2026-06-14T08:01:02.000Z"
    },
    {
      id: "step-04",
      run_id: "run-demo-react-001",
      attempt_id: "attempt-initial",
      step_index: 4,
      step_type: "tool_call",
      name: "write_test_file",
      input_summary: "Write generated pytest file under tests/generated.",
      output_summary: "Wrote tests/generated/test_checkout_generated.py inside allowed path.",
      tool_name: "write_test_file",
      payload: {
        input: {
          path: "tests/generated/test_checkout_generated.py",
          reason: "cover checkout pricing and boundary behavior"
        },
        output: {
          file_id: "file-checkout-generated-initial",
          content_hash: "sha256:3f3a4e5d",
          bytes: 2341
        }
      },
      tokens: null,
      duration_ms: 118,
      status: "ok",
      error: null,
      created_at: "2026-06-14T08:01:03.000Z"
    },
    {
      id: "step-05",
      run_id: "run-demo-react-001",
      attempt_id: "attempt-initial",
      step_index: 5,
      step_type: "observation",
      name: "run_pytest",
      input_summary: "Run generated checkout tests with timeout 120s.",
      output_summary: "4 passed, 1 failed. Failure is assertion mismatch, not system error.",
      tool_name: "run_pytest",
      payload: {
        input: {
          attempt_id: "attempt-initial",
          test_paths: ["tests/generated/test_checkout_generated.py"],
          timeout_seconds: 120,
          large_fixture_ids: Array.from({ length: 65 }, (_, index) => `fixture_${String(index + 1).padStart(3, "0")}`),
          environment: {
            python: "3.11.9",
            root_path: "D:/GitRepo/专业实训/TRACE/backend/tests/fixtures/async_demo_project",
            allow_network: false,
            isolated_work_dir: ".trace_artifacts/run-demo-react-001"
          }
        },
        output: {
          exit_code: 1,
          collected: 5,
          passed: 4,
          failed: 1,
          skipped: 0,
          duration_ms: 2418,
          case_results: [
            {
              nodeid:
                "tests/generated/test_checkout_generated.py::test_checkout_applies_coupon_and_tax[member-tier-vip-long-nodeid-case-with-tax-boundary-and-rounding]",
              status: "failed",
              duration_ms: 211,
              failure_type: "assertion",
              failure_message: "Expected total to include tiered discount and tax.",
              stdout_excerpt: "pricing rule: VIP20, subtotal: 120, tax_rate: 0.06",
              stderr_excerpt: "",
              traceback_hash: "8c14b84e99e41f1227e3a9"
            }
          ],
          failures: [
            {
              nodeid:
                "tests/generated/test_checkout_generated.py::test_checkout_applies_coupon_and_tax[member-tier-vip-long-nodeid-case-with-tax-boundary-and-rounding]",
              traceback: [
                "AssertionError: expected total to include tiered discount and tax",
                "E   assert 118.32 == 116.87",
                "E    + where 118.32 = CheckoutResponse(total=118.32).total"
              ]
            }
          ]
        }
      },
      tokens: null,
      duration_ms: 2418,
      status: "error",
      error: "AssertionError: expected total to include tiered discount and tax",
      created_at: "2026-06-14T08:01:04.000Z"
    },
    {
      id: "step-06",
      run_id: "run-demo-react-001",
      attempt_id: "attempt-reflection",
      step_index: 6,
      step_type: "reflection",
      name: "fix import and assertion direction",
      input_summary: "Reflect on structured pytest failure without weakening core assertion.",
      output_summary: "Fixed fixture setup and preserved discount-before-tax assertion.",
      tool_name: null,
      payload: {
        reflection_reason: "Generated test built expected total with tax before discount.",
        changes: [
          "Move discount calculation before tax expectation",
          "Keep status code and response body assertions",
          "Do not mark suspected_code_bug"
        ],
        suspected_code_bug: false
      },
      tokens: 1471,
      duration_ms: 1908,
      status: "ok",
      error: null,
      created_at: "2026-06-14T08:01:06.000Z"
    },
    {
      id: "step-07",
      run_id: "run-demo-react-001",
      attempt_id: "attempt-reflection",
      step_index: 7,
      step_type: "tool_call",
      name: "run_pytest",
      input_summary: "Re-run reflected generated tests.",
      output_summary: "4 passed, 1 failed. Run still completes with structured pytest evidence.",
      tool_name: "run_pytest",
      payload: {
        output: {
          exit_code: 1,
          collected: 5,
          passed: 4,
          failed: 1,
          skipped: 0,
          duration_ms: 1881
        }
      },
      tokens: null,
      duration_ms: 1881,
      status: "error",
      error: "One business assertion remains failed.",
      created_at: "2026-06-14T08:01:07.000Z"
    },
    {
      id: "step-08",
      run_id: "run-demo-react-001",
      attempt_id: null,
      step_index: 8,
      step_type: "report",
      name: "build final report",
      input_summary: "Summarize trace, pytest results and reflection risk notes.",
      output_summary: "Report saved with metrics and risk notes.",
      tool_name: null,
      payload: {
        report_id: "report-demo-react-001",
        markdown_artifact_id: "artifact-report-md",
        json_artifact_id: "artifact-report-json"
      },
      tokens: null,
      duration_ms: 242,
      status: "ok",
      error: null,
      created_at: "2026-06-14T08:01:08.000Z"
    }
  ],
  events: [
    {
      id: "event-01",
      run_id: "run-demo-react-001",
      stage: null,
      event_type: "run_enqueued",
      status_before: null,
      status_after: "queued",
      message: "Run queued for worker execution.",
      created_at: "2026-06-14T08:01:00.000Z"
    },
    {
      id: "event-02",
      run_id: "run-demo-react-001",
      stage: "executing",
      event_type: "pytest_failed",
      status_before: "running",
      status_after: "running",
      message: "Pytest failure preserved as case result.",
      created_at: "2026-06-14T08:01:04.000Z"
    },
    {
      id: "event-03",
      run_id: "run-demo-react-001",
      stage: null,
      event_type: "run_completed",
      status_before: "running",
      status_after: "completed",
      message: "Run completed with pytest failure evidence.",
      created_at: "2026-06-14T08:01:08.000Z"
    }
  ],
  attempts: [
    {
      id: "attempt-initial",
      run_plan_item_id: "item-checkout",
      attempt_no: 1,
      kind: "initial",
      status: "failed",
      started_at: "2026-06-14T08:01:01.000Z",
      finished_at: "2026-06-14T08:01:04.000Z",
      pytest_exit_code: 1,
      error_code: null,
      reflection_reason: null
    },
    {
      id: "attempt-reflection",
      run_plan_item_id: "item-checkout",
      attempt_no: 2,
      kind: "reflection",
      status: "failed",
      started_at: "2026-06-14T08:01:05.000Z",
      finished_at: "2026-06-14T08:01:07.000Z",
      pytest_exit_code: 1,
      error_code: null,
      reflection_reason: "Correct expected total calculation without removing assertion."
    }
  ],
  pytestResults: [
    {
      id: "pytest-01",
      attempt_id: "attempt-reflection",
      generated_test_case_id: "case-happy",
      nodeid: "tests/generated/test_checkout_generated.py::test_checkout_happy_path",
      mapping_status: "matched",
      status: "passed",
      duration_ms: 82,
      failure_type: null,
      failure_message: null,
      traceback_hash: null,
      stdout_excerpt: null,
      stderr_excerpt: null,
      is_collection_error: false
    },
    {
      id: "pytest-02",
      attempt_id: "attempt-reflection",
      generated_test_case_id: "case-tax",
      nodeid:
        "tests/generated/test_checkout_generated.py::test_checkout_applies_coupon_and_tax[member-tier-vip-long-nodeid-case-with-tax-boundary-and-rounding]",
      mapping_status: "matched",
      status: "failed",
      duration_ms: 211,
      failure_type: "assertion",
      failure_message: "Expected total to include tiered discount and tax. assert 118.32 == 116.87",
      traceback_hash: "8c14b84e99e41f1227e3a9",
      stdout_excerpt: "pricing rule: VIP20, subtotal: 120, tax_rate: 0.06",
      stderr_excerpt: "",
      is_collection_error: false
    },
    {
      id: "pytest-03",
      attempt_id: "attempt-reflection",
      generated_test_case_id: "case-invalid-coupon",
      nodeid: "tests/generated/test_checkout_generated.py::test_checkout_rejects_invalid_coupon",
      mapping_status: "matched",
      status: "passed",
      duration_ms: 96,
      failure_type: null,
      failure_message: null,
      traceback_hash: null,
      stdout_excerpt: null,
      stderr_excerpt: null,
      is_collection_error: false
    },
    {
      id: "pytest-04",
      attempt_id: "attempt-reflection",
      generated_test_case_id: "case-empty",
      nodeid: "tests/generated/test_checkout_generated.py::test_checkout_handles_empty_cart",
      mapping_status: "unmatched",
      status: "skipped",
      duration_ms: 0,
      failure_type: "collection",
      failure_message: "Skipped by collection marker in generated parameter branch.",
      traceback_hash: null,
      stdout_excerpt: null,
      stderr_excerpt: null,
      is_collection_error: false
    }
  ],
  artifacts: [
    {
      id: "artifact-report-md",
      run_id: "run-demo-react-001",
      attempt_id: null,
      runner_job_id: null,
      artifact_type: "report_markdown",
      uri: "artifacts/run-demo-react-001/report.md",
      content_hash: "sha256:report-md",
      size_bytes: 3214,
      metadata_json: { generated_by: "TRACE", format: "markdown" },
      created_at: "2026-06-14T08:01:08.000Z"
    },
    {
      id: "artifact-report-json",
      run_id: "run-demo-react-001",
      attempt_id: null,
      runner_job_id: null,
      artifact_type: "report_json",
      uri: "artifacts/run-demo-react-001/report.json",
      content_hash: "sha256:report-json",
      size_bytes: 4821,
      metadata_json: { generated_by: "TRACE", format: "json" },
      created_at: "2026-06-14T08:01:08.000Z"
    },
    {
      id: "artifact-junit",
      run_id: "run-demo-react-001",
      attempt_id: "attempt-reflection",
      runner_job_id: null,
      artifact_type: "junit_xml",
      uri: "backend/tests/fixtures/async_demo_project/.trace_junit.xml",
      content_hash: "sha256:junit",
      size_bytes: 2048,
      metadata_json: { pytest_exit_code: 1 },
      created_at: "2026-06-14T08:01:07.000Z"
    }
  ],
  report: {
    id: "report-demo-react-001",
    run_id: "run-demo-react-001",
    summary:
      "本次运行完成了项目分析、测试生成、pytest 执行和一次受约束 Reflection。系统运行状态为 completed，但报告保留一个 pytest 业务断言失败。",
    metrics: {
      final_passed: 4,
      final_failed: 1,
      final_skipped: 0,
      attempts: 2,
      tool_call_count: 5,
      total_tokens: 2384,
      duration_ms: 8400,
      reflection_used: true
    },
    risk_notes:
      "Reflection 修改了测试期望计算，但没有删除核心断言。当前 token 来自静态演示 fixture，不代表真实模型成本。pytest failure 不等于 run failed。",
    markdown_artifact_id: "artifact-report-md",
    json_artifact_id: "artifact-report-json",
    markdown_uri: "artifacts/run-demo-react-001/report.md",
    json_uri: "artifacts/run-demo-react-001/report.json",
    created_at: "2026-06-14T08:01:08.000Z"
  },
  strategy: demoStrategy
};

export const demoComparison: ComparisonResult = {
  rows: [
    {
      strategy_id: "sv-direct-v1",
      strategy_name: "Direct v1",
      repeats: 3,
      captured_per_repeat: [5, 5, 5],
      captured_mean: 5,
      total_in_scope: 6,
      capture_rate_mean: 0.8333333333333334,
      capture_rate_std: 0,
      false_positive_rate: 1,
      avg_tokens: 610,
      avg_tool_calls: 3,
      reflection_used: false,
      cost_per_captured_bug: 122
    },
    {
      strategy_id: "sv-plan-v1",
      strategy_name: "Plan-and-Execute v1",
      repeats: 3,
      captured_per_repeat: [6, 6, 6],
      captured_mean: 6,
      total_in_scope: 6,
      capture_rate_mean: 1,
      capture_rate_std: 0,
      false_positive_rate: 0,
      avg_tokens: 2293,
      avg_tool_calls: 13,
      reflection_used: false,
      cost_per_captured_bug: 382.1666666666667
    },
    {
      strategy_id: "sv-react-v1",
      strategy_name: "ReAct+Reflection v1",
      repeats: 3,
      captured_per_repeat: [6, 6, 6],
      captured_mean: 6,
      total_in_scope: 6,
      capture_rate_mean: 1,
      capture_rate_std: 0,
      false_positive_rate: 0,
      avg_tokens: 1342,
      avg_tool_calls: 5,
      reflection_used: true,
      cost_per_captured_bug: 223.66666666666666
    }
  ],
  capture_matrix: {
    "cmp-flip-discount": { "sv-direct-v1": true, "sv-plan-v1": true, "sv-react-v1": true },
    "cmp-flip-freeship": { "sv-direct-v1": true, "sv-plan-v1": true, "sv-react-v1": true },
    "boundary-shipping": { "sv-direct-v1": true, "sv-plan-v1": true, "sv-react-v1": true },
    "boundary-loyalty": { "sv-direct-v1": true, "sv-plan-v1": true, "sv-react-v1": true },
    "missing-clamp": { "sv-direct-v1": true, "sv-plan-v1": true, "sv-react-v1": true },
    "wrong-status": { "sv-direct-v1": false, "sv-plan-v1": true, "sv-react-v1": true }
  }
};
