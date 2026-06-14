export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(message: string, status: number, detail: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

const baseUrl = import.meta.env.VITE_TRACE_API_BASE_URL ?? "";

function endpoint(path: string): string {
  if (/^https?:\/\//.test(path)) {
    return path;
  }
  return `${baseUrl}${path}`;
}

async function readDetail(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function detailMessage(detail: unknown): string {
  if (typeof detail === "string") {
    return detail;
  }
  if (detail && typeof detail === "object" && "detail" in detail) {
    const value = (detail as { detail?: unknown }).detail;
    if (typeof value === "string") {
      return value;
    }
    return JSON.stringify(value);
  }
  return "";
}

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(endpoint(path), {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    ...init
  });

  if (!response.ok) {
    const detail = await readDetail(response);
    const suffix = detailMessage(detail);
    throw new ApiError(`Request failed: ${response.status}${suffix ? ` - ${suffix}` : ""}`, response.status, detail);
  }

  if (response.status === 204) {
    return null as T;
  }

  return (await response.json()) as T;
}

export async function requestOptionalJson<T>(path: string): Promise<T | null> {
  try {
    return await requestJson<T>(path);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}
