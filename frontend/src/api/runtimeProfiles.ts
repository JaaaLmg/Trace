import { requestJson } from "./client";
import type { DatasetRuntimeBindingManifestOut, RuntimeProfileOut, RuntimeProfileUpsertRequest } from "../types/api";

export interface ExecutorStatus {
  executors: Record<
    string,
    {
      available: boolean;
      isolation_level: string;
      network_enforced: boolean;
      resource_limits_enforced: boolean;
      warning?: string;
      unavailable_reason?: string | null;
    }
  >;
}

export function getExecutorStatus(): Promise<ExecutorStatus> {
  return requestJson<ExecutorStatus>("/api/v1/runtime-profiles/executors/status");
}

export function listRuntimeProfiles(projectId: string): Promise<RuntimeProfileOut[]> {
  return requestJson<RuntimeProfileOut[]>(`/api/v1/projects/${projectId}/runtime-profiles`);
}

export function listDatasetRuntimeProfiles(datasetId: string): Promise<RuntimeProfileOut[]> {
  return requestJson<RuntimeProfileOut[]>(`/api/v1/eval-datasets/${datasetId}/runtime-profiles`);
}

export function getDatasetRuntimeBindingManifest(datasetId: string): Promise<DatasetRuntimeBindingManifestOut> {
  return requestJson<DatasetRuntimeBindingManifestOut>(`/api/v1/eval-datasets/${datasetId}/runtime-binding-manifest`);
}

export function createRuntimeProfile(projectId: string, body: RuntimeProfileUpsertRequest): Promise<RuntimeProfileOut> {
  return requestJson<RuntimeProfileOut>(`/api/v1/projects/${projectId}/runtime-profiles`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function createDatasetRuntimeProfile(datasetId: string, body: RuntimeProfileUpsertRequest): Promise<RuntimeProfileOut> {
  return requestJson<RuntimeProfileOut>(`/api/v1/eval-datasets/${datasetId}/runtime-profiles`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function updateRuntimeProfile(profileId: string, body: Partial<RuntimeProfileUpsertRequest>): Promise<RuntimeProfileOut> {
  return requestJson<RuntimeProfileOut>(`/api/v1/runtime-profiles/${profileId}`, {
    method: "PATCH",
    body: JSON.stringify(body)
  });
}

export function archiveRuntimeProfile(profileId: string): Promise<RuntimeProfileOut> {
  return requestJson<RuntimeProfileOut>(`/api/v1/runtime-profiles/${profileId}/archive`, {
    method: "POST"
  });
}

export function preflightRuntimeProfileDraft(body: RuntimeProfileUpsertRequest): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>("/api/v1/runtime-profiles/preflight", {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function preflightRuntimeProfile(profileId: string): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>(`/api/v1/runtime-profiles/${profileId}/preflight`, {
    method: "POST"
  });
}
