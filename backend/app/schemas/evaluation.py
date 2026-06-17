from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.tools import FailureType


DataSourceKind = Literal["mock", "scripted", "real_llm"]
ExperimentStatus = Literal["draft", "queued", "running", "completed", "failed", "cancelled"]
NetworkPolicy = Literal["default", "disabled", "install_only"]
ReplayMode = Literal["frozen_test_set"]
ReplayStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
WorkflowType = Literal["direct", "plan_execute", "react_reflection"]
CostPerCapturedBugStatus = Literal["ok", "no_bug_captured"]
MetricStatus = Literal["ok", "invalid_test_set", "evaluable_zero_capture"]
CleanRunValidityStatus = Literal["evaluable", "invalid_test_set"]
ResolutionStep = Literal["strategy_version_defaults", "experiment_llm_override", "repeat_derivation"]
CaptureRule = Literal["clean_passed_variant_assertion_failure_same_nodeid"]
ArtifactKind = Literal[
    "generated_test_set",
    "pytest_json",
    "junit_xml",
    "report_markdown",
    "report_json",
    "bug_patch",
    "experiment_metrics",
]


SECRET_PARAM_TOKENS = ("api_key", "apikey", "secret", "token", "password", "authorization")
RESERVED_MODEL_PARAM_KEYS = {
    "provider",
    "model",
    "model_provider",
    "model_name",
    "temperature",
    "max_output_tokens",
    "max_tokens",
}
LLM_RESOLUTION_ORDER: list[ResolutionStep] = [
    "strategy_version_defaults",
    "experiment_llm_override",
    "repeat_derivation",
]


def _reject_secret_param_names(value: dict[str, Any]) -> dict[str, Any]:
    for key in value:
        normalized = key.lower().replace("-", "_")
        if any(token in normalized for token in SECRET_PARAM_TOKENS):
            raise ValueError(f"LLM parameter {key!r} looks like a secret and must not be persisted")
    return value


def _reject_reserved_model_param_names(value: dict[str, Any]) -> dict[str, Any]:
    for key in value:
        normalized = key.lower().replace("-", "_")
        if normalized in RESERVED_MODEL_PARAM_KEYS:
            raise ValueError(f"LLM parameter {key!r} is a typed field and must not be duplicated in model_params")
    return value


def _validate_relative_project_path(value: str, *, field_name: str) -> str:
    normalized = value.replace("\\", "/").strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    if normalized.startswith("/") or normalized.startswith("//") or (len(normalized) >= 2 and normalized[1] == ":"):
        raise ValueError(f"{field_name} must be relative to the project root")
    if any(part == ".." for part in normalized.split("/")):
        raise ValueError(f"{field_name} must not contain parent-directory traversal")
    return value


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TemperaturePolicy(ContractModel):
    mode: Literal["strategy_default", "fixed", "repeat_jitter"] = "strategy_default"
    value: float | None = Field(default=None, ge=0)
    seed: int | None = None

    @model_validator(mode="after")
    def _fixed_temperature_needs_value(self) -> TemperaturePolicy:
        if self.mode == "fixed" and self.value is None:
            raise ValueError("fixed temperature policy requires value")
        return self


class LlmOverride(ContractModel):
    provider: str | None = None
    model: str | None = None
    temperature_policy: TemperaturePolicy = Field(default_factory=TemperaturePolicy)
    max_output_tokens: int | None = Field(default=None, ge=1)
    model_params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("model_params")
    @classmethod
    def _model_params_have_no_secrets(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _reject_reserved_model_param_names(_reject_secret_param_names(value))


class ResolvedLlmSpec(ContractModel):
    provider: str
    model: str
    temperature: float | None = Field(default=None, ge=0)
    max_output_tokens: int | None = Field(default=None, ge=1)
    model_params: dict[str, Any] = Field(default_factory=dict)
    resolution_order: list[ResolutionStep] = Field(default_factory=lambda: list(LLM_RESOLUTION_ORDER))
    repeat_index: int = Field(ge=0)
    secret_included: Literal[False] = False

    @field_validator("model_params")
    @classmethod
    def _model_params_have_no_secrets(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _reject_reserved_model_param_names(_reject_secret_param_names(value))

    @model_validator(mode="after")
    def _resolution_order_is_fixed(self) -> ResolvedLlmSpec:
        if self.resolution_order != LLM_RESOLUTION_ORDER:
            raise ValueError("LLM resolution order must be strategy defaults, experiment override, repeat derivation")
        return self


class StrategySnapshotContract(ContractModel):
    strategy_version_id: str
    prompt_version_id: str
    prompt_content_hash: str
    prompt_content: dict[str, Any]
    tool_schema_version_id: str
    tool_schema_content_hash: str
    tool_schema_json: dict[str, Any]
    workflow_type: WorkflowType
    allow_reflection: bool
    resolved_llm: ResolvedLlmSpec


class RuntimeSnapshotContract(ContractModel):
    runtime_profile_id: str | None = None
    runtime_profile_name: str | None = None
    executor: Literal["local_subprocess", "docker"] = "local_subprocess"
    python_version: str | None = None
    install_command: str | None = None
    test_command: str
    network_policy: NetworkPolicy
    timeout_seconds: int = Field(ge=1)
    env_template: dict[str, Any] = Field(default_factory=dict)
    resource_limits: dict[str, Any] = Field(default_factory=dict)
    env_keys: list[str] = Field(default_factory=list)
    secret_included: Literal[False] = False


class DataSourceLabel(ContractModel):
    kind: DataSourceKind
    label: str
    provider_label: str | None = None
    model_label: str | None = None
    generated_by: str


class ExperimentDefinition(ContractModel):
    id: str
    name: str
    dataset_id: str
    strategy_version_ids: list[str] = Field(min_length=1)
    repeat_count: int = Field(ge=1)
    llm_override: LlmOverride | None = None
    status: ExperimentStatus
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class TargetMappingEvidence(ContractModel):
    target_type: Literal["function", "route", "model", "module", "unknown"]
    target_ref: str
    source_path: str | None = None
    symbol: str | None = None
    mapping_status: Literal["mapped", "partial", "unmapped"]
    trace_step_id: str | None = None

    @field_validator("source_path")
    @classmethod
    def _source_path_is_project_relative(cls, value: str | None) -> str | None:
        if value is not None:
            _validate_relative_project_path(value, field_name="source_path")
        return value


class TestInventoryEvidence(ContractModel):
    test_name: str
    source_path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    nodeid: str | None = None

    @field_validator("source_path")
    @classmethod
    def _source_path_is_project_relative(cls, value: str) -> str:
        return _validate_relative_project_path(value, field_name="source_path")

    @model_validator(mode="after")
    def _line_range_is_valid(self) -> TestInventoryEvidence:
        if self.end_line < self.start_line:
            raise ValueError("test inventory end_line must be >= start_line")
        return self


class AssertionEvidence(ContractModel):
    test_name: str
    nodeid: str | None = None
    assertion_summary: str
    target_ref: str | None = None


class FailureClassificationEvidence(ContractModel):
    nodeid: str
    classification: FailureType
    message: str | None = None


class ReflectionEvidence(ContractModel):
    used: bool
    contract_checked: bool
    contract_passed: bool | None = None
    violation_reasons: list[str] = Field(default_factory=list)
    accepted_attempt_id: str | None = None
    rejected_attempt_ids: list[str] = Field(default_factory=list)


class SourceContextSnippet(ContractModel):
    path: str
    target_ref: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content_hash: str
    bytes: int = Field(ge=0)
    trace_step_id: str | None = None

    @field_validator("path")
    @classmethod
    def _path_is_project_relative(cls, value: str) -> str:
        return _validate_relative_project_path(value, field_name="path")

    @model_validator(mode="after")
    def _line_range_is_valid(self) -> SourceContextSnippet:
        if self.end_line < self.start_line:
            raise ValueError("source context end_line must be >= start_line")
        return self


class ContextCompletenessEvidence(ContractModel):
    status: Literal["complete", "partial", "incomplete"]
    context_incomplete: bool
    snippets: list[SourceContextSnippet] = Field(default_factory=list)
    missing_targets: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _incomplete_context_is_explicit(self) -> ContextCompletenessEvidence:
        if self.context_incomplete and self.status == "complete":
            raise ValueError("context_incomplete cannot be true when status is complete")
        if self.status != "complete" and not (self.missing_targets or self.risk_notes):
            raise ValueError("partial or incomplete context must explain the missing target or risk")
        return self


class ReportQualityEvidence(ContractModel):
    test_inventory: list[TestInventoryEvidence] = Field(default_factory=list)
    target_mappings: list[TargetMappingEvidence] = Field(default_factory=list)
    assertion_summaries: list[AssertionEvidence] = Field(default_factory=list)
    failure_classifications: list[FailureClassificationEvidence] = Field(default_factory=list)
    reflection_evidence: ReflectionEvidence
    context_completeness: ContextCompletenessEvidence


class SourceContextPolicy(ContractModel):
    project_root_boundary: Literal["project_snapshot_root"] = "project_snapshot_root"
    read_allowlist_globs: list[str] = Field(min_length=1)
    deny_globs: list[str] = Field(default_factory=list)
    generated_tests_dir: str
    max_file_bytes: int = Field(gt=0)
    max_total_bytes: int = Field(gt=0)
    max_snippets: int = Field(gt=0)
    trace_payload_required: bool = True
    missing_context_marker: Literal["context_incomplete"] = "context_incomplete"
    agent_source_write_permission: Literal["generated_tests_only"] = "generated_tests_only"

    @field_validator("read_allowlist_globs")
    @classmethod
    def _allowlist_is_project_relative(cls, value: list[str]) -> list[str]:
        for pattern in value:
            _validate_relative_project_path(pattern, field_name="read_allowlist_globs")
        return value

    @field_validator("generated_tests_dir")
    @classmethod
    def _generated_tests_dir_is_project_relative(cls, value: str) -> str:
        return _validate_relative_project_path(value, field_name="generated_tests_dir")

    @model_validator(mode="after")
    def _policy_has_budget_and_escape_guard(self) -> SourceContextPolicy:
        if self.max_total_bytes < self.max_file_bytes:
            raise ValueError("max_total_bytes must be >= max_file_bytes")
        normalized_denies = {pattern.replace("\\", "/") for pattern in self.deny_globs}
        if "../**" not in normalized_denies:
            raise ValueError("deny_globs must include ../** to document parent-directory escape rejection")
        return self


class CleanRunMetricsContract(ContractModel):
    final_cases_total: int = Field(ge=0)
    final_passed: int = Field(ge=0)
    final_failed: int = Field(ge=0)
    final_skipped: int = Field(ge=0)
    collection_errors: int = Field(default=0, ge=0)
    tool_call_count: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    clean_replay_id: str | None = None
    clean_replay: dict[str, Any] = Field(default_factory=dict)
    clean_replay_assertion_failure_nodeids: list[str] = Field(default_factory=list)
    clean_replay_matches_generation: bool | None = None
    validity_status: CleanRunValidityStatus = "evaluable"
    invalid_reason: str | None = None
    pipeline_reject_error: str | None = None
    context_completeness: ContextCompletenessEvidence | None = None
    analysis_warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _case_counts_are_consistent(self) -> CleanRunMetricsContract:
        counted = self.final_passed + self.final_failed + self.final_skipped
        if counted != self.final_cases_total:
            raise ValueError("final case counts must add up to final_cases_total")
        if self.validity_status == "invalid_test_set" and not self.invalid_reason:
            raise ValueError("invalid test sets must include invalid_reason")
        return self


class CleanRunContract(ContractModel):
    id: str
    experiment_id: str
    eval_task_id: str
    strategy_version_id: str
    repeat_index: int = Field(ge=0)
    clean_run_id: str
    status: ReplayStatus
    generated_test_set_artifact_id: str
    false_positive: bool
    clean_metrics: CleanRunMetricsContract
    runtime_snapshot: RuntimeSnapshotContract
    strategy_snapshot: StrategySnapshotContract
    report_quality: ReportQualityEvidence

    @model_validator(mode="after")
    def _repeat_index_matches_snapshot(self) -> CleanRunContract:
        if self.strategy_snapshot.resolved_llm.repeat_index != self.repeat_index:
            raise ValueError("clean run repeat_index must match strategy_snapshot.resolved_llm.repeat_index")
        if self.clean_metrics.clean_replay:
            replay = self.clean_metrics.clean_replay
            clean_failed = (
                int(replay.get("failed", 0)) > 0
                or int(replay.get("collection_errors", 0)) > 0
                or bool(replay.get("error"))
            )
        else:
            clean_failed = self.clean_metrics.final_failed > 0 or self.clean_metrics.collection_errors > 0
        if self.false_positive != clean_failed:
            raise ValueError("false_positive must match clean final failures or collection errors")
        return self


class PytestSummaryContract(ContractModel):
    collected: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    skipped: int = Field(ge=0)
    collection_errors: int = Field(default=0, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)


class TestReplayContract(ContractModel):
    __test__: ClassVar[bool] = False

    id: str
    experiment_clean_run_id: str
    generated_test_set_artifact_id: str
    target_snapshot_id: str
    bug_variant_id: str | None = None
    status: ReplayStatus
    pytest_summary: PytestSummaryContract
    replay_mode: ReplayMode = "frozen_test_set"
    llm_calls: Literal[0] = 0
    started_at: str | None = None
    finished_at: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class ReplayMetricsContract(ContractModel):
    capture_rule: CaptureRule = "clean_passed_variant_assertion_failure_same_nodeid"
    clean_passed_nodeids: list[str] = Field(default_factory=list)
    variant_assertion_failure_nodeids: list[str] = Field(default_factory=list)
    capturing_nodeids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _capturing_nodeids_are_intersection(self) -> ReplayMetricsContract:
        clean_passed = set(self.clean_passed_nodeids)
        assertion_failures = set(self.variant_assertion_failure_nodeids)
        capturing = set(self.capturing_nodeids)
        if not capturing.issubset(clean_passed):
            raise ValueError("capturing_nodeids must be present in clean_passed_nodeids")
        if not capturing.issubset(assertion_failures):
            raise ValueError("capturing_nodeids must be present in variant_assertion_failure_nodeids")
        return self


class ExperimentReplayRunContract(ContractModel):
    id: str
    experiment_clean_run_id: str
    bug_variant_id: str
    replay_id: str
    captured_bug: bool
    replay_metrics: ReplayMetricsContract

    @model_validator(mode="after")
    def _captured_bug_needs_nodeid(self) -> ExperimentReplayRunContract:
        if self.captured_bug and not self.replay_metrics.capturing_nodeids:
            raise ValueError("captured_bug=true requires at least one capturing nodeid")
        if not self.captured_bug and self.replay_metrics.capturing_nodeids:
            raise ValueError("capturing nodeids imply captured_bug=true")
        return self


class LlmDisplayEvidence(ContractModel):
    provider: str
    model: str
    derived_from_clean_run_ids: list[str] = Field(min_length=1)
    source: Literal["derived_from_clean_run_strategy_snapshots"] = "derived_from_clean_run_strategy_snapshots"


class ExperimentMetricRow(ContractModel):
    strategy_id: str
    strategy_name: str
    repeats: int = Field(ge=0)
    captured_per_repeat: list[int] = Field(default_factory=list)
    captured_mean: float = Field(ge=0)
    total_in_scope: int = Field(ge=0)
    capture_rate_mean: float = Field(ge=0, le=1)
    capture_rate_std: float = Field(ge=0, le=1)
    false_positive_rate: float = Field(ge=0, le=1)
    avg_tokens: float = Field(ge=0)
    avg_tool_calls: float = Field(ge=0)
    avg_duration_ms: float = Field(default=0.0, ge=0)
    pytest_collection_success_rate: float = Field(default=0.0, ge=0, le=1)
    reflection_used: bool
    reflection_contract_pass_rate: float | None = Field(default=None, ge=0, le=1)
    reflection_acceptance_rate: float | None = Field(default=None, ge=0, le=1)
    invalid_test_set_count: int = Field(default=0, ge=0)
    metric_status: MetricStatus = "ok"
    cost_per_captured_bug: float | None = Field(default=None, ge=0)
    cost_per_captured_bug_status: CostPerCapturedBugStatus
    data_source: DataSourceKind
    llm_display: LlmDisplayEvidence

    @model_validator(mode="after")
    def _metrics_are_consistent(self) -> ExperimentMetricRow:
        if self.repeats != len(self.captured_per_repeat):
            raise ValueError("repeats must equal len(captured_per_repeat)")
        if any(captured < 0 for captured in self.captured_per_repeat):
            raise ValueError("captured_per_repeat cannot contain negative values")
        if self.total_in_scope:
            if any(captured > self.total_in_scope for captured in self.captured_per_repeat):
                raise ValueError("captured_per_repeat cannot exceed total_in_scope")
            expected_mean = sum(self.captured_per_repeat) / self.repeats if self.repeats else 0.0
            expected_rate = expected_mean / self.total_in_scope
        else:
            if any(self.captured_per_repeat):
                raise ValueError("total_in_scope=0 cannot have captured bugs")
            expected_mean = 0.0
            expected_rate = 0.0
        if abs(self.captured_mean - expected_mean) > 1e-9:
            raise ValueError("captured_mean must equal mean(captured_per_repeat)")
        if abs(self.capture_rate_mean - expected_rate) > 1e-9:
            raise ValueError("capture_rate_mean must equal captured_mean / total_in_scope")
        total_captured = sum(self.captured_per_repeat)
        if self.invalid_test_set_count and self.repeats == 0:
            if self.metric_status != "invalid_test_set":
                raise ValueError("all-invalid metric rows must use invalid_test_set status")
        elif total_captured == 0:
            if self.metric_status != "evaluable_zero_capture":
                raise ValueError("evaluable zero capture rows must use evaluable_zero_capture status")
        elif self.metric_status != "ok":
            raise ValueError("captured metric rows must use ok status")
        if total_captured == 0:
            if self.cost_per_captured_bug is not None:
                raise ValueError("0 captured bugs must use null cost_per_captured_bug")
            if self.cost_per_captured_bug_status != "no_bug_captured":
                raise ValueError("0 captured bugs must use no_bug_captured status")
        else:
            if self.cost_per_captured_bug is None:
                raise ValueError("captured bugs require a cost_per_captured_bug value")
            if self.cost_per_captured_bug_status != "ok":
                raise ValueError("captured bugs require ok cost_per_captured_bug_status")
        return self


class ArtifactMetadataContract(ContractModel):
    kind: ArtifactKind
    created_by: Literal["agent", "executor", "experiment_service", "seed_script"]
    experiment_id: str | None = None
    clean_run_id: str | None = None
    replay_id: str | None = None
    content_role: str
    relative_paths: list[str] = Field(default_factory=list)
    hash_algorithm: Literal["sha256"] = "sha256"


class ArtifactContract(ContractModel):
    id: str
    artifact_type: ArtifactKind
    uri: str
    content_hash: str
    size_bytes: int = Field(ge=0)
    metadata: ArtifactMetadataContract


class TableSchemaDraft(ContractModel):
    name: str
    purpose: str
    fields: list[str] = Field(min_length=1)
    constraints: list[str] = Field(default_factory=list)


class ExperimentMetricsResponse(ContractModel):
    schema_version: Literal["v2.phase0"] = "v2.phase0"
    generated_at: str
    data_source: DataSourceLabel
    experiment: ExperimentDefinition
    source_context_policy: SourceContextPolicy
    capture_scope: dict[str, Any] = Field(default_factory=dict)
    rows: list[ExperimentMetricRow]
    capture_matrix: dict[str, dict[str, bool]]
    clean_runs: list[CleanRunContract]
    replay_runs: list[TestReplayContract]
    experiment_replay_runs: list[ExperimentReplayRunContract]
    artifacts: list[ArtifactContract] = Field(default_factory=list)

    @model_validator(mode="after")
    def _matrix_uses_row_strategy_ids(self) -> ExperimentMetricsResponse:
        row_strategy_ids = {row.strategy_id for row in self.rows}
        for bug_id, strategy_hits in self.capture_matrix.items():
            unknown = set(strategy_hits) - row_strategy_ids
            if unknown:
                raise ValueError(f"capture_matrix[{bug_id!r}] has unknown strategies: {sorted(unknown)}")
        return self


V2_PHASE0_DB_SCHEMA_DRAFT: tuple[TableSchemaDraft, ...] = (
    TableSchemaDraft(
        name="runtime_profiles",
        purpose="Reusable execution runtime; expanded into test_runs.runtime_snapshot at run creation.",
        fields=[
            "id",
            "project_id",
            "name",
            "python_version",
            "install_command",
            "test_command",
            "env_template",
            "resource_limits",
            "network_policy",
            "created_at",
            "updated_at",
        ],
        constraints=["env_template stores names/placeholders only, never secrets"],
    ),
    TableSchemaDraft(
        name="strategies",
        purpose="Parent strategy identity, for example Direct, Plan-and-Execute, ReAct.",
        fields=["id", "name", "workflow_type", "description", "created_at"],
    ),
    TableSchemaDraft(
        name="prompt_versions",
        purpose="Immutable prompt body version.",
        fields=["id", "name", "version", "content", "content_hash", "source_ref", "created_at"],
        constraints=["content_hash participates in reproducibility"],
    ),
    TableSchemaDraft(
        name="tool_schema_versions",
        purpose="Immutable generated tool schema version.",
        fields=["id", "version", "schema_json", "content_hash", "created_at"],
        constraints=["schema_json must come from code-generated schema, not hand drift"],
    ),
    TableSchemaDraft(
        name="eval_datasets",
        purpose="Immutable evaluation dataset version.",
        fields=["id", "name", "version", "description", "project_snapshot_ids", "created_at"],
    ),
    TableSchemaDraft(
        name="eval_tasks",
        purpose="Evaluation task scope and goal.",
        fields=["id", "dataset_id", "project_snapshot_id", "target_scope", "goal", "expected_capabilities"],
    ),
    TableSchemaDraft(
        name="seeded_bugs",
        purpose="Semantic seeded bug definition.",
        fields=["id", "eval_task_id", "bug_type", "description", "expected_detection"],
    ),
    TableSchemaDraft(
        name="bug_variants",
        purpose="Concrete canonical bug variant.",
        fields=["id", "seeded_bug_id", "variant_name", "canonical_kind", "patch_artifact_id", "mutated_snapshot_id", "ground_truth"],
        constraints=["canonical patch must apply to exactly one clean snapshot location"],
    ),
    TableSchemaDraft(
        name="experiments",
        purpose="Evaluation execution unit.",
        fields=["id", "name", "dataset_id", "repeat_count", "llm_override", "status", "created_at", "started_at", "finished_at", "error_code", "error_message"],
        constraints=["llm_override is only a layer; resolved provider/model/temperature freeze in clean run strategy_snapshot"],
    ),
    TableSchemaDraft(
        name="experiment_strategy_versions",
        purpose="Experiment to strategy version association with stable display order.",
        fields=["experiment_id", "strategy_version_id", "index", "created_at"],
        constraints=["unique(experiment_id, strategy_version_id)"],
    ),
    TableSchemaDraft(
        name="experiment_clean_runs",
        purpose="Clean snapshot generation run and frozen test set reference.",
        fields=["id", "experiment_id", "eval_task_id", "strategy_version_id", "repeat_index", "clean_run_id", "generated_test_set_artifact_id", "false_positive", "clean_metrics"],
    ),
    TableSchemaDraft(
        name="test_replays",
        purpose="Replay frozen generated test set against clean or variant snapshot without LLM calls.",
        fields=["id", "experiment_clean_run_id", "generated_test_set_artifact_id", "target_snapshot_id", "bug_variant_id", "status", "pytest_summary", "started_at", "finished_at", "error_code", "error_message"],
        constraints=["replay never plans, generates, or calls LLM"],
    ),
    TableSchemaDraft(
        name="experiment_replay_runs",
        purpose="Bug capture result for an experiment replay.",
        fields=["id", "experiment_clean_run_id", "bug_variant_id", "replay_id", "captured_bug", "replay_metrics"],
        constraints=["captured_bug=true must trace to at least one failing nodeid"],
    ),
)
