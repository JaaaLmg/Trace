import { requestJson } from "./client";

export interface DirectoryPickOut {
  path: string | null;
  cancelled: boolean;
}

export function pickLocalDirectory(initialPath: string | null | undefined, title: string): Promise<DirectoryPickOut> {
  return requestJson<DirectoryPickOut>("/api/v1/local/directories/pick", {
    method: "POST",
    body: JSON.stringify({
      initial_path: initialPath?.trim() || null,
      title
    })
  });
}
