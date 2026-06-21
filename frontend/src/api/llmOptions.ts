import { requestJson } from "./client";
import type { LlmOptionsOut } from "../types/api";

export function listLlmOptions(): Promise<LlmOptionsOut> {
  return requestJson<LlmOptionsOut>("/api/v1/llm-options");
}