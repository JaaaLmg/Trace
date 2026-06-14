import { requestJson } from "./client";
import type { StrategyVersionOut } from "../types/api";

export function getStrategyVersion(strategyVersionId: string): Promise<StrategyVersionOut> {
  return requestJson<StrategyVersionOut>(`/api/v1/strategy-versions/${strategyVersionId}`);
}
