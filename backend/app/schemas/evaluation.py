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
BugVariantSourceKind = Literal["seeded_bug", "auto_mutation"]
MutationOperatorKind = Literal[
    "comparison_boundary",
    "comparison_negation",
    "boolean_negation",
    "arithmetic_operator",
    "constant_replacement",
    "return_value",
    "exception_type",
    "statement_deletion",
    "unknown",
]
MutantMatcherKind = Literal["source_location_hash", "operator_signature"]
MutantSelectionStatus = Literal["selected", "not_selected", "excluded"]
MutantSelectedBy = Literal["auto_sampler", "manual"]
MutationDiscoveryExclusionCode = Literal[
    "syntax_error",
    "target_not_found",
    "source_segment_unavailable",
    "unsupported_compare",
    "non_unique_patch",
]
SourceContextKind = Literal[
    "target_source",
    "dependency",
    "reference",
    "model_schema",
    "fixture",
    "existing_test",
    "failure_context",
    "fallback_file",
]
RetrievalSourceKind = Literal[
    "analysis_ast",
    "framework_scanner",
    "pytest_scanner",
    "direct_path",
    "default_path",
    "rg",
    "ast_grep",
    "lsp",
    "pytest_result",
    "evaluation_event",
]
RetrievalTraceStatus = Literal["resolved", "missing", "truncated", "error"]
ArtifactKind = Literal[
    "generated_test_set",
    "pytest_json",
    "junit_xml",
    "report_markdown",
    "report_json",
    "bug_patch",
    "experiment_metrics",
]
EvaluationEventType = Literal[
    "invalid_test_set",
    "context_incomplete_blocking",
    "flaky_clean_replay",
    "probe_check_passed",
    "probe_check_failed",
    "replay_captured",
    "replay_uncaptured",
    "replay_failure",
    "artifact_hash_mismatch",
    "provider_failure",
    "executor_unavailable",
    "executor_timeout",
    "setup_failed",
    "cleanup_failed",
    "resource_limit_exceeded",
    "network_policy_violation",
    "replay_cache_hit",
    "replay_cache_stale",
]
EvaluationEventSeverity = Literal["info", "warning", "error", "blocking"]
EvaluationEventScope = Literal["experiment", "clean_run", "replay", "variant", "task", "artifact"]
ReflectionEventBackfeedAction = Literal["included", "filtered"]
SampledMutationScoreStatus = Literal["ok", "not_applicable", "incomplete_replay"]


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
    return normalized


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
    model_config = ConfigDict(extra="allow")

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
    model_config = ConfigDict(extra="allow")

    runtime_profile_id: str | None = None
    runtime_profile_name: str | None = None
    executor: Literal["local_subprocess", "docker"] = "local_subprocess"
    image: str | None = None
    working_dir: str | None = None
    python_version: str | None = None
    install_command: str | None = None
    test_command: str
    network_policy: NetworkPolicy
    timeout_seconds: int = Field(ge=1)
    env_template: dict[str, Any] = Field(default_factory=dict)
    resource_limits: dict[str, Any] = Field(default_factory=dict)
    artifact_policy: dict[str, Any] = Field(default_factory=dict)
    cleanup_policy: dict[str, Any] = Field(default_factory=dict)
    executor_capabilities: dict[str, Any] = Field(default_factory=dict)
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
    runtime_profile_id: str | None = None
    strategy_version_ids: list[str] = Field(min_length=1)
    repeat_count: int = Field(ge=1)
    llm_override: LlmOverride | None = None
    status: ExperimentStatus
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class MutantPatchContract(ContractModel):
    file: str
    old: str = Field(min_length=1)
    new: str

    @field_validator("file")
    @classmethod
    def _file_is_project_relative(cls, value: str) -> str:
        return _validate_relative_project_path(value, field_name="mutation patch file")


class MutantMatcherContract(ContractModel):
    matcher_kind: MutantMatcherKind = "source_location_hash"
    source_path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    original_content_hash: str
    operator: MutationOperatorKind
    target_symbol: str | None = None
    context_hash: str | None = None

    @field_validator("source_path")
    @classmethod
    def _source_path_is_project_relative(cls, value: str) -> str:
        return _validate_relative_project_path(value, field_name="mutation matcher source_path")

    @field_validator("original_content_hash")
    @classmethod
    def _content_hash_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("mutation matcher original_content_hash cannot be blank")
        return value

    @model_validator(mode="after")
    def _line_range_is_valid(self) -> MutantMatcherContract:
        if self.end_line < self.start_line:
            raise ValueError("mutation matcher end_line must be >= start_line")
        return self


class MutantSelectionContract(ContractModel):
    status: MutantSelectionStatus
    selected_by: MutantSelectedBy = "auto_sampler"
    reason: str
    sample_seed: int | None = Field(default=None, ge=0)
    sample_index: int | None = Field(default=None, ge=0)

    @field_validator("reason")
    @classmethod
    def _reason_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("mutation selection reason cannot be blank")
        return value

    @model_validator(mode="after")
    def _auto_selected_mutants_are_reproducible(self) -> MutantSelectionContract:
        if self.status == "selected" and self.selected_by == "auto_sampler":
            if self.sample_seed is None or self.sample_index is None:
                raise ValueError("auto-selected mutants require sample_seed and sample_index")
        return self


class MutationCandidateContract(ContractModel):
    candidate_id: str
    eval_task_id: str
    source_snapshot_id: str
    operator: MutationOperatorKind
    patch: MutantPatchContract
    matcher: MutantMatcherContract
    selection: MutantSelectionContract
    probe: dict[str, Any] = Field(default_factory=dict)

    @field_validator("candidate_id", "eval_task_id", "source_snapshot_id")
    @classmethod
    def _required_ids_are_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("mutation candidate ids cannot be blank")
        return value

    @model_validator(mode="after")
    def _matcher_operator_matches_candidate(self) -> MutationCandidateContract:
        if self.matcher.operator != self.operator:
            raise ValueError("mutation matcher operator must match candidate operator")
        return self


class BugVariantGroundTruthContract(ContractModel):
    source: BugVariantSourceKind = "seeded_bug"
    target: str | None = None
    patch_unique_hit: dict[str, Any] = Field(default_factory=dict)
    patch_artifact: dict[str, Any] = Field(default_factory=dict)
    mutation: MutationCandidateContract | None = None
    probe: dict[str, Any] = Field(default_factory=dict)
    expected_behavior: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _auto_mutation_requires_selected_candidate(self) -> BugVariantGroundTruthContract:
        if self.source == "auto_mutation":
            if self.mutation is None:
                raise ValueError("auto mutation bug variants require mutation candidate metadata")
            if self.mutation.selection.status != "selected":
                raise ValueError("only selected mutants may become bug variants")
        elif self.mutation is not None:
            raise ValueError("seeded bug ground truth must not carry auto mutation metadata")
        return self


class MutationDiscoveryExclusionContract(ContractModel):
    reason_code: MutationDiscoveryExclusionCode
    message: str
    target_ref: str | None = None
    source_path: str | None = None
    line: int | None = Field(default=None, ge=1)

    @field_validator("message")
    @classmethod
    def _message_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("mutation discovery exclusion message cannot be blank")
        return value

    @field_validator("source_path")
    @classmethod
    def _source_path_is_project_relative(cls, value: str | None) -> str | None:
        if value is not None:
            _validate_relative_project_path(value, field_name="mutation discovery exclusion source_path")
        return value


class MutationDiscoveryResultContract(ContractModel):
    eval_task_id: str
    source_snapshot_id: str
    sample_seed: int = Field(ge=0)
    max_selected: int = Field(ge=0)
    candidates: list[MutationCandidateContract] = Field(default_factory=list)
    exclusions: list[MutationDiscoveryExclusionContract] = Field(default_factory=list)
    selected_count: int = Field(ge=0)
    excluded_count: int = Field(ge=0)

    @field_validator("eval_task_id", "source_snapshot_id")
    @classmethod
    def _required_ids_are_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("mutation discovery ids cannot be blank")
        return value

    @model_validator(mode="after")
    def _counts_match_payload(self) -> MutationDiscoveryResultContract:
        selected = [candidate for candidate in self.candidates if candidate.selection.status == "selected"]
        if self.selected_count != len(selected):
            raise ValueError("selected_count must match selected candidates")
        if self.excluded_count != len(self.exclusions):
            raise ValueError("excluded_count must match exclusions")
        if self.selected_count > self.max_selected:
            raise ValueError("selected_count cannot exceed max_selected")
        return self


class MutationDiscoveryAuditReportContract(ContractModel):
    schema_version: Literal["v2.mutation_discovery_audit"] = "v2.mutation_discovery_audit"
    generated_at: str
    eval_task_id: str
    dataset_id: str
    source_snapshot_id: str
    target_scope: dict[str, Any] | list[Any] | None = None
    sample_seed: int = Field(ge=0)
    max_selected: int = Field(ge=0)
    dry_run: Literal[True] = True
    writes_database: Literal[False] = False
    runs_replay: Literal[False] = False
    selected_candidate_ids: list[str] = Field(default_factory=list)
    exclusion_summary: dict[MutationDiscoveryExclusionCode, int] = Field(default_factory=dict)
    discovery: MutationDiscoveryResultContract

    @field_validator("generated_at", "eval_task_id", "dataset_id", "source_snapshot_id")
    @classmethod
    def _required_text_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("mutation discovery audit report identifiers cannot be blank")
        return value

    @model_validator(mode="after")
    def _summary_matches_discovery(self) -> MutationDiscoveryAuditReportContract:
        selected = [candidate.candidate_id for candidate in self.discovery.candidates if candidate.selection.status == "selected"]
        if self.selected_candidate_ids != selected:
            raise ValueError("selected_candidate_ids must match discovery selected candidates")
        summary: dict[str, int] = {}
        for exclusion in self.discovery.exclusions:
            summary[exclusion.reason_code] = summary.get(exclusion.reason_code, 0) + 1
        if dict(self.exclusion_summary) != summary:
            raise ValueError("exclusion_summary must match discovery exclusions")
        return self


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


class SourceContextRetrievalTrace(ContractModel):
    trace_id: str
    source_kind: SourceContextKind
    retrieval_source: RetrievalSourceKind
    target: str
    source_path: str | None = None
    symbol: str | None = None
    line_range: dict[str, int] | None = None
    confidence: float = Field(ge=0, le=1)
    content_hash: str | None = None
    status: RetrievalTraceStatus
    risk_notes: list[str] = Field(default_factory=list)

    @field_validator("source_path")
    @classmethod
    def _source_path_is_project_relative(cls, value: str | None) -> str | None:
        if value is not None:
            _validate_relative_project_path(value, field_name="source_path")
        return value

    @field_validator("line_range")
    @classmethod
    def _line_range_shape_is_valid(cls, value: dict[str, int] | None) -> dict[str, int] | None:
        if value is None:
            return value
        if set(value) != {"start", "end"}:
            raise ValueError("line_range must contain start and end")
        if value["start"] < 1 or value["end"] < value["start"]:
            raise ValueError("line_range must be a valid 1-based range")
        return value


class SourceContextSnippet(ContractModel):
    path: str
    source_path: str | None = None
    target_ref: str
    target: str | None = None
    symbol: str | None = None
    source_kind: SourceContextKind = "target_source"
    retrieval_source: RetrievalSourceKind = "analysis_ast"
    confidence: float = Field(default=1.0, ge=0, le=1)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content_hash: str
    bytes: int = Field(ge=0)
    retrieval_trace_id: str | None = None
    trace_step_id: str | None = None

    @field_validator("path")
    @classmethod
    def _path_is_project_relative(cls, value: str) -> str:
        return _validate_relative_project_path(value, field_name="path")

    @model_validator(mode="after")
    def _line_range_is_valid(self) -> SourceContextSnippet:
        if self.end_line < self.start_line:
            raise ValueError("source context end_line must be >= start_line")
        if self.source_path is None:
            self.source_path = self.path
        else:
            _validate_relative_project_path(self.source_path, field_name="source_path")
        return self


class ContextCompletenessEvidence(ContractModel):
    status: Literal["complete", "partial", "incomplete"]
    context_incomplete: bool
    snippets: list[SourceContextSnippet] = Field(default_factory=list)
    retrieval_trace: list[SourceContextRetrievalTrace] = Field(default_factory=list)
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
    model_config = ConfigDict(extra="allow")

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
        if self.clean_metrics.validity_status == "invalid_test_set":
            return self
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
    model_config = ConfigDict(extra="allow")

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
    runtime_snapshot: RuntimeSnapshotContract = Field(default_factory=lambda: RuntimeSnapshotContract(
        test_command="python -m pytest tests -q --rootdir . -p no:cacheprovider",
        network_policy="default",
        timeout_seconds=120,
    ))
    executor_metadata: dict[str, Any] = Field(default_factory=dict)
    workspace_manifest: dict[str, Any] = Field(default_factory=dict)
    cache_key: str | None = None
    cache_status: Literal["miss", "hit", "stale"] = "miss"
    source_replay_id: str | None = None
    replay_mode: ReplayMode = "frozen_test_set"
    llm_calls: Literal[0] = 0
    started_at: str | None = None
    finished_at: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class ReplayMetricsContract(ContractModel):
    model_config = ConfigDict(extra="allow")

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
    model_config = ConfigDict(extra="allow")

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


class SampledMutationScoreRow(ContractModel):
    strategy_id: str
    strategy_name: str
    mutant_count: int = Field(ge=0)
    repeat_count: int = Field(ge=0)
    expected_replay_count: int = Field(ge=0)
    observed_replay_count: int = Field(ge=0)
    captured_mutant_count: int = Field(ge=0)
    score: float | None = Field(default=None, ge=0, le=1)
    status: SampledMutationScoreStatus

    @model_validator(mode="after")
    def _score_inputs_are_consistent(self) -> SampledMutationScoreRow:
        expected = self.mutant_count * self.repeat_count
        if self.expected_replay_count != expected:
            raise ValueError("expected_replay_count must equal mutant_count * repeat_count")
        if self.observed_replay_count > self.expected_replay_count:
            raise ValueError("observed_replay_count cannot exceed expected_replay_count")
        if self.captured_mutant_count > self.mutant_count:
            raise ValueError("captured_mutant_count cannot exceed mutant_count")
        if self.mutant_count == 0:
            if self.status != "not_applicable":
                raise ValueError("0 sampled mutants must use not_applicable status")
            if self.score is not None:
                raise ValueError("not_applicable sampled mutation score must be null")
            return self
        if self.expected_replay_count == 0 or self.observed_replay_count != self.expected_replay_count:
            if self.status != "incomplete_replay":
                raise ValueError("incomplete sampled replay coverage must use incomplete_replay status")
            if self.score is not None:
                raise ValueError("incomplete sampled mutation score must be null")
            return self
        if self.status != "ok":
            raise ValueError("complete sampled mutation score rows must use ok status")
        expected_score = self.captured_mutant_count / self.mutant_count
        if self.score is None or abs(self.score - expected_score) > 1e-9:
            raise ValueError("sampled mutation score must equal captured_mutant_count / mutant_count")
        return self


class SampledMutationScoreContract(ContractModel):
    status: SampledMutationScoreStatus
    unit: Literal["auto_mutation_bug_variant"] = "auto_mutation_bug_variant"
    denominator_source: Literal[
        "bug_variants.ground_truth.source=auto_mutation + ground_truth.probe.probe_check.status=passed"
    ] = "bug_variants.ground_truth.source=auto_mutation + ground_truth.probe.probe_check.status=passed"
    mutant_count: int = Field(ge=0)
    included_variant_ids: list[str] = Field(default_factory=list)
    excluded_variant_counts: dict[str, int] = Field(default_factory=dict)
    rows: list[SampledMutationScoreRow] = Field(default_factory=list)
    matrix_counts: dict[str, dict[str, dict[str, Any]]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _summary_matches_rows(self) -> SampledMutationScoreContract:
        if self.mutant_count != len(self.included_variant_ids):
            raise ValueError("mutant_count must match included_variant_ids")
        if any(count < 0 for count in self.excluded_variant_counts.values()):
            raise ValueError("excluded_variant_counts cannot contain negative counts")
        if self.mutant_count == 0:
            if self.status != "not_applicable":
                raise ValueError("empty sampled mutation scope must use not_applicable status")
            if any(row.status != "not_applicable" for row in self.rows):
                raise ValueError("empty sampled mutation scope rows must be not_applicable")
            return self
        if any(row.mutant_count != self.mutant_count for row in self.rows):
            raise ValueError("sampled mutation rows must use the summary mutant_count")
        expected_status = (
            "incomplete_replay"
            if not self.rows or any(row.status == "incomplete_replay" for row in self.rows)
            else "ok"
        )
        if self.status != expected_status:
            raise ValueError("sampled mutation summary status must match row statuses")
        return self


def _empty_sampled_mutation_score() -> SampledMutationScoreContract:
    return SampledMutationScoreContract(
        status="not_applicable",
        mutant_count=0,
        included_variant_ids=[],
        excluded_variant_counts={},
        rows=[],
        matrix_counts={},
    )


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


class EvaluationEventContract(ContractModel):
    event_id: str
    event_type: EvaluationEventType
    severity: EvaluationEventSeverity
    scope: EvaluationEventScope
    experiment_id: str
    clean_run_id: str | None = None
    replay_id: str | None = None
    bug_variant_id: str | None = None
    eval_task_id: str | None = None
    strategy_version_id: str | None = None
    repeat_index: int | None = Field(default=None, ge=0)
    stable_code: str
    reason: str
    source_ids: dict[str, str] = Field(default_factory=dict)
    artifact_ids: list[str] = Field(default_factory=list)
    nodeids: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_from: Literal["experiment_service_projection"] = "experiment_service_projection"

    @field_validator("event_id", "stable_code", "reason")
    @classmethod
    def _required_text_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("evaluation event id, stable_code, and reason cannot be blank")
        return value

    @field_validator("source_ids")
    @classmethod
    def _source_ids_have_no_blank_values(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not str(key).strip() or not str(item).strip() for key, item in value.items()):
            raise ValueError("evaluation event source_ids cannot contain blank keys or values")
        return value


class ReflectionEventBackfeedDecisionContract(ContractModel):
    event_id: str
    event_type: EvaluationEventType
    action: ReflectionEventBackfeedAction
    reason: str

    @field_validator("event_id", "reason")
    @classmethod
    def _required_text_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reflection event backfeed decision event_id and reason cannot be blank")
        return value


class ReflectionEventBackfeedContract(ContractModel):
    clean_run_id: str
    eval_task_id: str
    strategy_version_id: str
    repeat_index: int = Field(ge=0)
    max_events: int = Field(ge=1)
    included_event_ids: list[str] = Field(default_factory=list)
    decisions: list[ReflectionEventBackfeedDecisionContract] = Field(default_factory=list)
    created_from: Literal["evaluation_event_projection"] = "evaluation_event_projection"

    @field_validator("clean_run_id", "eval_task_id", "strategy_version_id")
    @classmethod
    def _required_text_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reflection event backfeed identifiers cannot be blank")
        return value


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
    runtime_execution: dict[str, Any] = Field(default_factory=dict)
    capture_scope: dict[str, Any] = Field(default_factory=dict)
    rows: list[ExperimentMetricRow]
    capture_matrix: dict[str, dict[str, bool]]
    capture_matrix_counts: dict[str, dict[str, dict[str, Any]]] = Field(default_factory=dict)
    sampled_mutation_score: SampledMutationScoreContract = Field(default_factory=_empty_sampled_mutation_score)
    clean_runs: list[CleanRunContract]
    replay_runs: list[TestReplayContract]
    experiment_replay_runs: list[ExperimentReplayRunContract]
    evaluation_events: list[EvaluationEventContract] = Field(default_factory=list)
    reflection_event_backfeed: list[ReflectionEventBackfeedContract] = Field(default_factory=list)
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
        constraints=[
            "canonical patch must apply to exactly one clean snapshot location",
            "auto mutation variants must carry selected mutation matcher metadata in ground_truth",
        ],
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
