CREATE TABLE IF NOT EXISTS projects (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT NULL,
    source_type VARCHAR(64) NOT NULL DEFAULT 'local_path',
    repo_url TEXT NULL,
    local_path TEXT NOT NULL,
    default_branch VARCHAR(255) NULL,
    language VARCHAR(64) NOT NULL DEFAULT 'python',
    framework VARCHAR(64) NOT NULL DEFAULT 'fastapi',
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name);

CREATE TABLE IF NOT EXISTS project_snapshots (
    id VARCHAR(36) PRIMARY KEY,
    project_id VARCHAR(36) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source_kind VARCHAR(64) NOT NULL,
    root_path TEXT NOT NULL,
    content_hash VARCHAR(128) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_project_snapshots_project_id ON project_snapshots(project_id);

CREATE TABLE IF NOT EXISTS strategy_versions (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    workflow_type VARCHAR(64) NOT NULL,
    model_provider VARCHAR(64) NOT NULL DEFAULT 'mock',
    model_name VARCHAR(255) NOT NULL DEFAULT 'mock-1',
    model_params JSONB NOT NULL DEFAULT '{}'::jsonb,
    allow_reflection BOOLEAN NOT NULL DEFAULT FALSE,
    max_tool_calls INTEGER NOT NULL DEFAULT 12,
    prompt_ref VARCHAR(128) NOT NULL DEFAULT 'v1',
    tool_schema_ref VARCHAR(128) NOT NULL DEFAULT 'v1',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS test_plans (
    id VARCHAR(36) PRIMARY KEY,
    project_id VARCHAR(36) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    target_scope JSONB NOT NULL DEFAULT '[]'::jsonb,
    goal TEXT NOT NULL,
    budget JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_options JSONB NOT NULL DEFAULT '{}'::jsonb,
    default_strategy_version_id VARCHAR(64) NULL REFERENCES strategy_versions(id) ON DELETE SET NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_test_plans_project_id ON test_plans(project_id);

CREATE TABLE IF NOT EXISTS test_runs (
    id VARCHAR(36) PRIMARY KEY,
    test_plan_id VARCHAR(36) NULL REFERENCES test_plans(id) ON DELETE SET NULL,
    retry_of_run_id VARCHAR(36) NULL REFERENCES test_runs(id) ON DELETE SET NULL,
    project_snapshot_id VARCHAR(36) NOT NULL REFERENCES project_snapshots(id) ON DELETE RESTRICT,
    runtime_profile_id VARCHAR(36) NULL,
    strategy_version_id VARCHAR(64) NOT NULL REFERENCES strategy_versions(id) ON DELETE RESTRICT,
    runtime_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    strategy_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(32) NOT NULL DEFAULT 'queued',
    stage VARCHAR(32) NULL,
    started_at TIMESTAMPTZ NULL,
    finished_at TIMESTAMPTZ NULL,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    total_cost NUMERIC(12,4) NULL,
    tool_call_count INTEGER NOT NULL DEFAULT 0,
    pytest_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_code VARCHAR(128) NULL,
    error_message TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_test_runs_test_plan_id ON test_runs(test_plan_id);
CREATE INDEX IF NOT EXISTS idx_test_runs_retry_of_run_id ON test_runs(retry_of_run_id);
CREATE INDEX IF NOT EXISTS idx_test_runs_project_snapshot_id ON test_runs(project_snapshot_id);
CREATE INDEX IF NOT EXISTS idx_test_runs_strategy_version_id ON test_runs(strategy_version_id);
CREATE INDEX IF NOT EXISTS idx_test_runs_status ON test_runs(status);
CREATE INDEX IF NOT EXISTS idx_test_runs_stage ON test_runs(stage);

CREATE TABLE IF NOT EXISTS run_plan_items (
    id VARCHAR(36) PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
    index INTEGER NOT NULL,
    target_type VARCHAR(64) NOT NULL,
    target_ref TEXT NOT NULL,
    goal TEXT NOT NULL,
    planned_assertions JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    CONSTRAINT uq_run_plan_items_run_id_index UNIQUE (run_id, index)
);

CREATE INDEX IF NOT EXISTS idx_run_plan_items_run_id ON run_plan_items(run_id);

CREATE TABLE IF NOT EXISTS run_attempts (
    id VARCHAR(36) PRIMARY KEY,
    run_plan_item_id VARCHAR(36) NOT NULL REFERENCES run_plan_items(id) ON DELETE CASCADE,
    attempt_no INTEGER NOT NULL,
    kind VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'running',
    started_at TIMESTAMPTZ NULL,
    finished_at TIMESTAMPTZ NULL,
    pytest_exit_code INTEGER NULL,
    error_code VARCHAR(128) NULL,
    reflection_reason TEXT NULL,
    CONSTRAINT uq_run_attempts_item_attempt UNIQUE (run_plan_item_id, attempt_no)
);

CREATE INDEX IF NOT EXISTS idx_run_attempts_run_plan_item_id ON run_attempts(run_plan_item_id);

CREATE TABLE IF NOT EXISTS generated_test_files (
    id VARCHAR(36) PRIMARY KEY,
    attempt_id VARCHAR(36) NOT NULL REFERENCES run_attempts(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    content_text TEXT NULL,
    content_hash VARCHAR(128) NOT NULL,
    artifact_id VARCHAR(36) NULL,
    previous_file_id VARCHAR(36) NULL REFERENCES generated_test_files(id) ON DELETE SET NULL,
    diff_artifact_id VARCHAR(36) NULL,
    generation_reason TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_generated_test_files_attempt_id ON generated_test_files(attempt_id);

CREATE TABLE IF NOT EXISTS generated_test_cases (
    id VARCHAR(36) PRIMARY KEY,
    file_id VARCHAR(36) NOT NULL REFERENCES generated_test_files(id) ON DELETE CASCADE,
    nodeid TEXT NULL,
    test_name VARCHAR(255) NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    target_route TEXT NULL,
    target_function TEXT NULL,
    assertion_summary TEXT NULL,
    source_strategy_version_id VARCHAR(64) NULL,
    adoption_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    human_meaningfulness_score INTEGER NULL,
    rule_flags JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_generated_test_cases_file_id ON generated_test_cases(file_id);

CREATE TABLE IF NOT EXISTS pytest_case_results (
    id VARCHAR(36) PRIMARY KEY,
    attempt_id VARCHAR(36) NOT NULL REFERENCES run_attempts(id) ON DELETE CASCADE,
    generated_test_case_id VARCHAR(36) NULL REFERENCES generated_test_cases(id) ON DELETE SET NULL,
    nodeid TEXT NOT NULL,
    mapping_status VARCHAR(32) NOT NULL DEFAULT 'matched',
    status VARCHAR(32) NOT NULL,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    failure_type VARCHAR(32) NULL,
    failure_message TEXT NULL,
    traceback_hash VARCHAR(128) NULL,
    stdout_excerpt TEXT NULL,
    stderr_excerpt TEXT NULL,
    is_collection_error BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_pytest_case_results_attempt_id ON pytest_case_results(attempt_id);
CREATE INDEX IF NOT EXISTS idx_pytest_case_results_generated_test_case_id ON pytest_case_results(generated_test_case_id);
CREATE INDEX IF NOT EXISTS idx_pytest_case_results_nodeid ON pytest_case_results(nodeid);

CREATE TABLE IF NOT EXISTS trace_steps (
    id VARCHAR(36) PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
    attempt_id VARCHAR(36) NULL REFERENCES run_attempts(id) ON DELETE SET NULL,
    step_index INTEGER NOT NULL,
    step_type VARCHAR(32) NOT NULL,
    name VARCHAR(255) NOT NULL,
    input_summary TEXT NULL,
    output_summary TEXT NULL,
    tool_name VARCHAR(128) NULL,
    payload JSONB NULL,
    tokens INTEGER NULL,
    duration_ms INTEGER NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'ok',
    error TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_trace_steps_run_id_step_index UNIQUE (run_id, step_index)
);

CREATE INDEX IF NOT EXISTS idx_trace_steps_run_id ON trace_steps(run_id);
CREATE INDEX IF NOT EXISTS idx_trace_steps_attempt_id ON trace_steps(attempt_id);

CREATE TABLE IF NOT EXISTS run_events (
    id VARCHAR(36) PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
    stage VARCHAR(32) NULL,
    event_type VARCHAR(64) NOT NULL,
    status_before VARCHAR(32) NULL,
    status_after VARCHAR(32) NULL,
    message TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_run_events_run_id ON run_events(run_id);
CREATE INDEX IF NOT EXISTS idx_run_events_stage ON run_events(stage);

CREATE TABLE IF NOT EXISTS run_artifacts (
    id VARCHAR(36) PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
    attempt_id VARCHAR(36) NULL REFERENCES run_attempts(id) ON DELETE SET NULL,
    runner_job_id VARCHAR(36) NULL,
    artifact_type VARCHAR(64) NOT NULL,
    uri TEXT NOT NULL,
    content_hash VARCHAR(128) NULL,
    size_bytes INTEGER NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_run_artifacts_run_id ON run_artifacts(run_id);
CREATE INDEX IF NOT EXISTS idx_run_artifacts_attempt_id ON run_artifacts(attempt_id);

CREATE TABLE IF NOT EXISTS test_reports (
    id VARCHAR(36) PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL UNIQUE REFERENCES test_runs(id) ON DELETE CASCADE,
    summary TEXT NOT NULL,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    risk_notes TEXT NULL,
    markdown_artifact_id VARCHAR(36) NULL,
    json_artifact_id VARCHAR(36) NULL,
    markdown_uri TEXT NULL,
    json_uri TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_test_reports_run_id ON test_reports(run_id);
