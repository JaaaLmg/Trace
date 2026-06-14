import { requestJson } from "./client";
import type { ProjectOut, ProjectSnapshotOut, TestPlanOut } from "../types/api";

export function listProjects(): Promise<ProjectOut[]> {
  return requestJson<ProjectOut[]>("/api/v1/projects");
}

export function getProject(projectId: string): Promise<ProjectOut> {
  return requestJson<ProjectOut>(`/api/v1/projects/${projectId}`);
}

export function listSnapshots(projectId: string): Promise<ProjectSnapshotOut[]> {
  return requestJson<ProjectSnapshotOut[]>(`/api/v1/projects/${projectId}/snapshots`);
}

export function getTestPlan(planId: string): Promise<TestPlanOut> {
  return requestJson<TestPlanOut>(`/api/v1/test-plans/${planId}`);
}
