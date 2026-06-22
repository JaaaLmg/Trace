param(
    [string]$ApiBase = "http://127.0.0.1:8000",
    [string]$FrontendBase = "http://127.0.0.1:5186",
    [switch]$RunExperiment
)

$ErrorActionPreference = "Stop"

function Invoke-JsonCheck {
    param(
        [string]$Name,
        [string]$Url
    )
    Write-Host "Checking $Name -> $Url"
    return Invoke-RestMethod -Uri $Url -TimeoutSec 10
}

function Wait-ExperimentCompleted {
    param(
        [string]$ExperimentId,
        [int]$TimeoutSeconds = 180
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $progress = Invoke-JsonCheck -Name "Experiment progress" -Url "$ApiBase/api/v1/experiments/$ExperimentId/progress"
        Write-Host ("Experiment {0}: status={1}, clean={2}/{3}, replay={4}, running={5}" -f $ExperimentId, $progress.status, $progress.clean_runs_completed, $progress.clean_runs_total_estimate, $progress.replay_runs_completed, $progress.replay_runs_running)
        if ($progress.status -in @("completed", "failed", "cancelled")) {
            return $progress
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    throw "Experiment $ExperimentId did not finish within $TimeoutSeconds seconds"
}

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

Write-Host "Checking frontend -> $FrontendBase"
$frontend = Invoke-WebRequest -UseBasicParsing -Uri $FrontendBase -TimeoutSec 10
if ($frontend.StatusCode -ne 200 -or $frontend.Content -notmatch "TRACE") {
    throw "Frontend did not return the TRACE app shell"
}

if ($RunExperiment) {
    $profiles = Invoke-JsonCheck -Name "Runtime profiles" -Url "$ApiBase/api/v1/eval-datasets/dataset-demo-v2/runtime-profiles"
    $profile = @($profiles)[0]
    if (-not $profile.id) {
        throw "No runtime profile found for dataset-demo-v2"
    }

    $experimentId = "compose-smoke-" + (Get-Date -Format "yyyyMMddHHmmss")
    $createBody = @{
        id = $experimentId
        name = "Compose smoke direct"
        dataset_id = "dataset-demo-v2"
        runtime_profile_id = $profile.id
        strategy_version_ids = @("sv-direct-v1")
        repeat_count = 1
        llm_override = @{ provider = "mock"; model = "mock-1" }
    } | ConvertTo-Json -Depth 8

    Write-Host "Creating experiment -> $experimentId"
    $created = Invoke-RestMethod -Method Post -Uri "$ApiBase/api/v1/experiments" -ContentType "application/json" -Body $createBody -TimeoutSec 20
    if ($created.status -ne "draft") {
        throw "Expected draft experiment, got $($created.status)"
    }

    Write-Host "Starting experiment -> $experimentId"
    $started = Invoke-RestMethod -Method Post -Uri "$ApiBase/api/v1/experiments/$experimentId/runs" -TimeoutSec 20
    if ($started.status -notin @("queued", "running", "completed")) {
        throw "Expected queued/running/completed after start, got $($started.status)"
    }

    $progress = Wait-ExperimentCompleted -ExperimentId $experimentId
    if ($progress.status -ne "completed") {
        throw "Experiment $experimentId ended with status $($progress.status)"
    }

    $metrics = Invoke-JsonCheck -Name "Experiment metrics" -Url "$ApiBase/api/v1/experiments/$experimentId/metrics"
    $rows = @($metrics.rows)
    $replays = @($metrics.replay_runs)
    $llmCalls = @($replays | ForEach-Object { $_.llm_calls } | Sort-Object -Unique)
    if ($rows.Count -ne 1 -or $rows[0].metric_status -ne "ok") {
        throw "Expected one ok metric row for $experimentId"
    }
    if ($progress.clean_runs_completed -ne 1 -or $progress.replay_runs_completed -ne 9) {
        throw "Expected 1 clean run and 9 replay runs for $experimentId"
    }
    if ($llmCalls.Count -ne 1 -or $llmCalls[0] -ne 0) {
        throw "Expected replay llm_calls=[0] for $experimentId"
    }
    Write-Host "Experiment smoke passed -> $experimentId"
}

Write-Host "TRACE Compose smoke passed."
