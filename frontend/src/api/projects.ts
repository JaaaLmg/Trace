import { requestJson } from "./client";
import type {
  ProjectCreateRequest,
  ProjectOut,
  ProjectSnapshotOut,
  SnapshotCreateRequest,
  TestPlanCreateRequest,
  TestPlanOut,
  TestRunOut
} from "../types/api";

export function listProjects(): Promise<ProjectOut[]> {
  return requestJson<ProjectOut[]>("/api/v1/projects");
}

export function createProject(body: ProjectCreateRequest): Promise<ProjectOut> {
  return requestJson<ProjectOut>("/api/v1/projects", {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function getProject(projectId: string): Promise<ProjectOut> {
  return requestJson<ProjectOut>(`/api/v1/projects/${projectId}`);
}

export function listSnapshots(projectId: string): Promise<ProjectSnapshotOut[]> {
  return requestJson<ProjectSnapshotOut[]>(`/api/v1/projects/${projectId}/snapshots`);
}

export function listProjectTestPlans(projectId: string): Promise<TestPlanOut[]> {
  return requestJson<TestPlanOut[]>(`/api/v1/projects/${projectId}/test-plans`);
}

export function listProjectTestRuns(projectId: string): Promise<TestRunOut[]> {
  return requestJson<TestRunOut[]>(`/api/v1/projects/${projectId}/test-runs`);
}

export function createSnapshot(projectId: string, body: SnapshotCreateRequest): Promise<ProjectSnapshotOut> {
  return requestJson<ProjectSnapshotOut>(`/api/v1/projects/${projectId}/snapshots`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function createTestPlan(body: TestPlanCreateRequest): Promise<TestPlanOut> {
  return requestJson<TestPlanOut>("/api/v1/test-plans", {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export function getTestPlan(planId: string): Promise<TestPlanOut> {
  return requestJson<TestPlanOut>(`/api/v1/test-plans/${planId}`);
}
