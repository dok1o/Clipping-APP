// Minimal fetch client: no axios, unified error contract
// {"detail": {"code": "snake_case", "message": "...", "fields": {...}}} (CONTRACTS §1).

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields: Record<string, string> | null;

  constructor(status: number, code: string, message: string, fields: Record<string, string> | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
}

const BASE_URL = import.meta.env.VITE_API_URL ?? "";

async function parseError(response: Response): Promise<ApiError> {
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (detail?.code) {
      return new ApiError(response.status, detail.code, detail.message ?? "Request failed", detail.fields ?? null);
    }
    return new ApiError(response.status, "http_error", `HTTP ${response.status}`, null);
  } catch {
    return new ApiError(response.status, "http_error", `HTTP ${response.status}`, null);
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`);
  if (!response.ok) throw await parseError(response);
  return (await response.json()) as T;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw await parseError(response);
  return (await response.json()) as T;
}

export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${BASE_URL}${path}`, { method: "POST", body: form });
  if (!response.ok) throw await parseError(response);
  return (await response.json()) as T;
}
