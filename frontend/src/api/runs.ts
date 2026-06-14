import { requestJson, requestOptionalJson } from "./client";
import type {
  PytestCaseResultOut,
  RunArtifactOut,
  RunAttemptOut,
  RunBundle,
  RunCreateRequest,
  RunEventOut,
  TestReportOut,
  TestRunOut,
  TraceStepOut
} from "../types/api";
import { getStrategyVersion } from "./strategies";

export function getRun(runId: string): Promise<TestRunOut> {
  return requestJson<TestRunOut>(`/api/v1/test-runs/${runId}`);
}

export function createRun(planId: string, body: RunCreateRequest): Promise<TestRunOut> {
  return requestJson<TestRunOut>(`/api/v1/test-plans/${planId}/runs`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function cancelRun(runId: string): Promise<TestRunOut> {
  return requestJson<TestRunOut>(`/api/v1/test-runs/${runId}/cancel`, {
    method: "POST"
  });
}

export function retryRun(runId: string): Promise<TestRunOut> {
  return requestJson<TestRunOut>(`/api/v1/test-runs/${runId}/retry`, {
    method: "POST"
  });
}

export function listTraceSteps(runId: string): Promise<TraceStepOut[]> {
  return requestJson<TraceStepOut[]>(`/api/v1/test-runs/${runId}/trace-steps`);
}

export function listEvents(runId: string): Promise<RunEventOut[]> {
  return requestJson<RunEventOut[]>(`/api/v1/test-runs/${runId}/events`);
}

export function listAttempts(runId: string): Promise<RunAttemptOut[]> {
  return requestJson<RunAttemptOut[]>(`/api/v1/test-runs/${runId}/attempts`);
}

export function listPytestResults(runId: string): Promise<PytestCaseResultOut[]> {
  return requestJson<PytestCaseResultOut[]>(`/api/v1/test-runs/${runId}/pytest-results`);
}

export function listArtifacts(runId: string): Promise<RunArtifactOut[]> {
  return requestJson<RunArtifactOut[]>(`/api/v1/test-runs/${runId}/artifacts`);
}

export function getReport(runId: string): Promise<TestReportOut | null> {
  return requestOptionalJson<TestReportOut>(`/api/v1/test-runs/${runId}/report`);
}

export async function getRunBundle(runId: string): Promise<RunBundle> {
  const run = await getRun(runId);
  const [traceSteps, events, attempts, pytestResults, artifacts, report, strategy] = await Promise.all([
    listTraceSteps(runId),
    listEvents(runId),
    listAttempts(runId),
    listPytestResults(runId),
    listArtifacts(runId),
    getReport(runId),
    getStrategyVersion(run.strategy_version_id).catch(() => null)
  ]);

  return { run, traceSteps, events, attempts, pytestResults, artifacts, report, strategy };
}
