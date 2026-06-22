param(
    [string]$ApiBase = "http://127.0.0.1:8000",
    [string]$ExperimentId = "",
    [int]$RepeatCount = 1,
    [int]$TimeoutSeconds = 600,
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"

function Invoke-JsonCheck {
    param(
        [string]$Name,
        [string]$Url
    )
    Write-Host "Checking $Name -> $Url"
    return Invoke-RestMethod -Uri $Url -TimeoutSec 15
}

function Wait-ExperimentCompleted {
    param(
        [string]$ExperimentId,
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $progress = Invoke-JsonCheck -Name "Experiment progress" -Url "$ApiBase/api/v1/experiments/$ExperimentId/progress"
        Write-Host ("Experiment {0}: status={1}, clean={2}/{3}, replay={4}, running={5}" -f $ExperimentId, $progress.status, $progress.clean_runs_completed, $progress.clean_runs_total_estimate, $progress.replay_runs_completed, $progress.replay_runs_running)
        if ($progress.status -in @("completed", "failed", "cancelled")) {
            return $progress
        }
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $deadline)

    throw "Experiment $ExperimentId did not finish within $TimeoutSeconds seconds"
}

if (-not $ExperimentId) {
    $ExperimentId = "compose-benchmark-suite-" + (Get-Date -Format "yyyyMMddHHmmss")
}
if ($RepeatCount -lt 1) {
    throw "RepeatCount must be >= 1"
}

$strategyIds = @("sv-direct-v1", "sv-plan-v1", "sv-react-v1")

$health = Invoke-JsonCheck -Name "API health" -Url "$ApiBase/healthz"
if (-not $health.ok) {
    throw "API healthz did not return ok=true"
}

$llmOptions = Invoke-JsonCheck -Name "LLM options" -Url "$ApiBase/api/v1/llm-options"
$mockOption = $llmOptions.options | Where-Object { $_.id -eq "mock" -and $_.selectable -eq $true } | Select-Object -First 1
if (-not $mockOption) {
    throw "MockLLM option is missing or not selectable"
}

$datasets = Invoke-JsonCheck -Name "Datasets" -Url "$ApiBase/api/v1/eval-datasets"
$demoDataset = $datasets | Where-Object { $_.id -eq "dataset-demo-v2" } | Select-Object -First 1
if (-not $demoDataset) {
    throw "dataset-demo-v2 is missing"
}

$datasetDetail = Invoke-JsonCheck -Name "Dataset detail" -Url "$ApiBase/api/v1/eval-datasets/dataset-demo-v2"
$tasks = @($datasetDetail.tasks)
$taskCount = $tasks.Count
$bugVariantCount = 0
foreach ($task in $tasks) {
    foreach ($bug in @($task.seeded_bugs)) {
        $bugVariantCount += @($bug.variants).Count
    }
}
if ($taskCount -lt 1 -or $bugVariantCount -lt 1) {
    throw "dataset-demo-v2 must include at least one task and one bug variant"
}

$expectedCleanRuns = $taskCount * $strategyIds.Count * $RepeatCount
$expectedVariantReplayRuns = $bugVariantCount * $strategyIds.Count * $RepeatCount

$profiles = Invoke-JsonCheck -Name "Runtime profiles" -Url "$ApiBase/api/v1/eval-datasets/dataset-demo-v2/runtime-profiles"
$profile = @($profiles)[0]
if (-not $profile.id) {
    throw "No runtime profile found for dataset-demo-v2"
}

$createBody = @{
    id = $ExperimentId
    name = "Compose benchmark three strategies"
    dataset_id = "dataset-demo-v2"
    runtime_profile_id = $profile.id
    strategy_version_ids = $strategyIds
    repeat_count = $RepeatCount
    llm_override = @{ provider = "mock"; model = "mock-1" }
} | ConvertTo-Json -Depth 8

Write-Host "Creating benchmark experiment -> $ExperimentId"
$created = Invoke-RestMethod -Method Post -Uri "$ApiBase/api/v1/experiments" -ContentType "application/json" -Body $createBody -TimeoutSec 20
if ($created.status -ne "draft") {
    throw "Expected draft experiment, got $($created.status)"
}

Write-Host "Starting benchmark experiment -> $ExperimentId"
$started = Invoke-RestMethod -Method Post -Uri "$ApiBase/api/v1/experiments/$ExperimentId/runs" -TimeoutSec 20
if ($started.status -notin @("queued", "running", "completed")) {
    throw "Expected queued/running/completed after start, got $($started.status)"
}

$progress = Wait-ExperimentCompleted -ExperimentId $ExperimentId -TimeoutSeconds $TimeoutSeconds
if ($progress.status -ne "completed") {
    throw "Experiment $ExperimentId ended with status $($progress.status)"
}

$metrics = Invoke-JsonCheck -Name "Experiment metrics" -Url "$ApiBase/api/v1/experiments/$ExperimentId/metrics"
$rows = @($metrics.rows)
$replays = @($metrics.replay_runs)
$metricStatuses = @($rows | ForEach-Object { $_.metric_status } | Sort-Object -Unique)
$llmCalls = @($replays | ForEach-Object { [int]$_.llm_calls } | Sort-Object -Unique)

if ($rows.Count -ne 3) {
    throw "Expected 3 metric rows for $ExperimentId, got $($rows.Count)"
}
if ($metricStatuses.Count -ne 1 -or $metricStatuses[0] -ne "ok") {
    throw "Expected metric_status=[ok] for $ExperimentId"
}
if ($progress.clean_runs_completed -ne $expectedCleanRuns) {
    throw "Expected $expectedCleanRuns clean runs for $ExperimentId, got $($progress.clean_runs_completed)"
}
if (@($metrics.clean_runs).Count -ne $expectedCleanRuns) {
    throw "Expected $expectedCleanRuns clean run records for $ExperimentId, got $(@($metrics.clean_runs).Count)"
}
if (@($metrics.experiment_replay_runs).Count -ne $expectedVariantReplayRuns) {
    throw "Expected $expectedVariantReplayRuns variant replay records for $ExperimentId, got $(@($metrics.experiment_replay_runs).Count)"
}
if ($metrics.capture_scope.total_bug_variants -ne $bugVariantCount) {
    throw "Expected capture_scope.total_bug_variants=$bugVariantCount for $ExperimentId"
}
if ($progress.replay_runs_completed -lt $expectedVariantReplayRuns) {
    throw "Expected at least $expectedVariantReplayRuns completed replay runs for $ExperimentId, got $($progress.replay_runs_completed)"
}
if ($llmCalls.Count -ne 1 -or $llmCalls[0] -ne 0) {
    throw "Expected replay llm_calls=[0] for $ExperimentId"
}

$summaryRows = @(
    $rows | ForEach-Object {
        [ordered]@{
            strategy_id = $_.strategy_id
            strategy_name = $_.strategy_name
            metric_status = $_.metric_status
            captured_per_repeat = $_.captured_per_repeat
            captured_mean = $_.captured_mean
            total_in_scope = $_.total_in_scope
            capture_rate_mean = $_.capture_rate_mean
            capture_rate_std = $_.capture_rate_std
            false_positive_rate = $_.false_positive_rate
            avg_tokens = $_.avg_tokens
            avg_tool_calls = $_.avg_tool_calls
            reflection_used = $_.reflection_used
            invalid_test_set_count = $_.invalid_test_set_count
            cost_per_captured_bug = $_.cost_per_captured_bug
        }
    }
)

$summary = [ordered]@{
    generated_at = (Get-Date).ToString("o")
    experiment_id = $ExperimentId
    dataset_id = "dataset-demo-v2"
    task_count = $taskCount
    bug_variant_count = $bugVariantCount
    runtime_profile_id = $profile.id
    strategy_version_ids = $strategyIds
    repeat_count = $RepeatCount
    llm_override = @{ provider = "mock"; model = "mock-1" }
    status = $progress.status
    clean_runs_completed = $progress.clean_runs_completed
    replay_runs_completed = $progress.replay_runs_completed
    expected_clean_runs = $expectedCleanRuns
    expected_variant_replay_runs = $expectedVariantReplayRuns
    metric_statuses = $metricStatuses
    replay_llm_calls = $llmCalls
    rows = $summaryRows
}

$json = $summary | ConvertTo-Json -Depth 8
if ($OutputPath) {
    $fullPath = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputPath))
    $directory = [System.IO.Path]::GetDirectoryName($fullPath)
    if ($directory) {
        New-Item -ItemType Directory -Force -Path $directory | Out-Null
    }
    Set-Content -LiteralPath $fullPath -Value $json -Encoding UTF8
    Write-Host "Benchmark summary written -> $fullPath"
}

$json
Write-Host "TRACE Compose benchmark passed -> $ExperimentId"
