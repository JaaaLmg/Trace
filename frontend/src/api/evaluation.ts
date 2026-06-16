import { requestJson } from "./client";
import type { EvalDatasetDetailOut, EvalDatasetOut } from "../types/api";

export function listEvalDatasets(): Promise<EvalDatasetOut[]> {
  return requestJson<EvalDatasetOut[]>("/api/v1/eval-datasets");
}

export function getEvalDataset(datasetId: string): Promise<EvalDatasetDetailOut> {
  return requestJson<EvalDatasetDetailOut>(`/api/v1/eval-datasets/${datasetId}`);
}
