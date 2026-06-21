import { requestJson } from "./client";
import type {
  ExperimentCreateRequest,
  ExperimentCleanRunOut,
  ExperimentDefinition,
  ExperimentMetricsResponse,
  ExperimentProgressOut,
  TestReplayOut
} from "../types/api";

export function listExperiments(): Promise<ExperimentDefinition[]> {
  return requestJson<ExperimentDefinition[]>("/api/v1/experiments");
}

export function createExperiment(body: ExperimentCreateRequest): Promise<ExperimentDefinition> {
  return requestJson<ExperimentDefinition>("/api/v1/experiments", {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function getExperiment(experimentId: string): Promise<ExperimentDefinition> {
  return requestJson<ExperimentDefinition>(`/api/v1/experiments/${experimentId}`);
}

export function runExperiment(experimentId: string): Promise<ExperimentDefinition> {
  return requestJson<ExperimentDefinition>(`/api/v1/experiments/${experimentId}/runs`, {
    method: "POST"
  });
}

export function cancelExperiment(experimentId: string): Promise<ExperimentDefinition> {
  return requestJson<ExperimentDefinition>(`/api/v1/experiments/${experimentId}/cancel`, {
    method: "POST"
  });
}

export function listExperimentCleanRuns(experimentId: string): Promise<ExperimentCleanRunOut[]> {
  return requestJson<ExperimentCleanRunOut[]>(`/api/v1/experiments/${experimentId}/clean-runs`);
}

export function listExperimentReplayRuns(experimentId: string): Promise<TestReplayOut[]> {
  return requestJson<TestReplayOut[]>(`/api/v1/experiments/${experimentId}/replay-runs`);
}

export function getExperimentMetrics(experimentId: string): Promise<ExperimentMetricsResponse> {
  return requestJson<ExperimentMetricsResponse>(`/api/v1/experiments/${experimentId}/metrics`);
}

export function getExperimentProgress(experimentId: string): Promise<ExperimentProgressOut> {
  return requestJson<ExperimentProgressOut>(`/api/v1/experiments/${experimentId}/progress`);
}

export function cleanupExperiment(
  experimentId: string,
  body: { dry_run?: boolean; keep_failed?: boolean } = {}
): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>(`/api/v1/experiments/${experimentId}/cleanup`, {
    method: "POST",
    body: JSON.stringify({ dry_run: body.dry_run ?? true, keep_failed: body.keep_failed ?? true })
  });
}

export function getExperimentArtifactInventory(experimentId: string): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>(`/api/v1/experiments/${experimentId}/artifact-inventory`);
}

export function getExperimentReplayCache(experimentId: string): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>(`/api/v1/experiments/${experimentId}/replay-cache`);
}

export function cleanupExperimentReplayCache(
  experimentId: string,
  body: { dry_run?: boolean } = {}
): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>(`/api/v1/experiments/${experimentId}/replay-cache/cleanup`, {
    method: "POST",
    body: JSON.stringify({ dry_run: body.dry_run ?? true, keep_failed: true })
  });
}
