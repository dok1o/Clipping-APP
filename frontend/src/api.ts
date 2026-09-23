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

async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`);
  if (!response.ok) throw await parseError(response);
  return (await response.json()) as T;
}

async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!response.ok) throw await parseError(response);
  return (await response.json()) as T;
}

async function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!response.ok) throw await parseError(response);
  return (await response.json()) as T;
}

async function apiUpload<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${BASE_URL}${path}`, { method: "POST", body: form });
  if (!response.ok) throw await parseError(response);
  return (await response.json()) as T;
}

// ---------- domain types (backend CONTRACTS) ----------

export interface Video {
  id: string;
  original_filename: string;
  storage_key: string;
  size_bytes: number;
  mime_type: string;
  duration_sec: number | null;
  width: number | null;
  height: number | null;
  status: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface Clip {
  id: string;
  video_id: string;
  title: string;
  start_sec: number;
  end_sec: number;
  status: string;
  score: number | null;
  created_at: string;
  updated_at: string;
}

export interface Job {
  id: string;
  type: string;
  status: string;
  ref_type: string;
  ref_id: string;
  attempts: number;
  max_attempts: number;
  result: Record<string, unknown> | null;
  error_message: string | null;
  created_at: string;
}

export interface RenderedAsset {
  id: string;
  clip_id: string;
  storage_key: string;
  size_bytes: number;
  width: number;
  height: number;
  codec_video: string;
  codec_audio: string;
  pix_fmt: string;
  duration_sec: number;
  status: string;
  created_at: string;
}

export interface Publication {
  id: string;
  clip_id: string;
  platform: string;
  platform_account_id: string;
  external_post_id: string | null;
  status: string;
  scheduled_at: string | null;
  published_at: string | null;
  attempt_count: number;
  last_error: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface TrainingRun {
  id: string;
  created_at: string;
  status: string;
  n_rows: number;
  val_spearman: number | null;
  baseline_spearman: number | null;
  gate_passed: boolean;
  model_version: string | null;
  error_message: string | null;
}

export interface Metric {
  id: string;
  publication_id: string;
  captured_at: string;
  views: number | null;
  likes: number | null;
  comments: number | null;
  shares: number | null;
}

export interface PlatformAccount {
  id: string;
  platform: string;
  external_account_id: string;
  display_name: string | null;
  credentials: string;
  scopes: string[];
  is_active: boolean;
  created_at: string;
}

export interface Candidate {
  id: string;
  video_id: string;
  start: number;
  end: number;
  score: number;
  reason: string;
  features: Record<string, unknown>;
  created_at: string;
}

export interface TranscriptSegment {
  id: string;
  start: number;
  end: number;
  text: string;
  avg_confidence: number | null;
}

export interface GeneratedTexts {
  titles: string[];
  description: string;
  hashtags: string[];
}

export interface JobPage {
  items: Job[];
  total: number;
}

export interface OverviewStats {
  videos: Record<string, number>;
  clips: Record<string, number>;
  jobs: Record<string, number>;
  publications: Record<string, number>;
  scheduled_next_at: string | null;
  failed_jobs_recent: number;
  latest_metrics: {
    publications: number;
    views: number;
    likes: number;
    comments: number;
    shares: number;
  };
  ml: {
    dataset_rows: number;
    active_model: { model_version: string; backend: string } | null;
  };
}

export interface HealthStatus {
  status: string;
  version: string;
  checks: Record<string, string>;
}

// Upload with progress (fetch cannot report upload progress; XHR can).
export function uploadVideoWithProgress(
  file: File,
  onProgress: (fraction: number) => void,
): Promise<Video> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${BASE_URL}/api/v1/videos`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as Video);
        } catch {
          reject(new ApiError(xhr.status, "invalid_response", "Некорректный ответ сервера", null));
        }
      } else {
        try {
          const detail = JSON.parse(xhr.responseText)?.detail;
          reject(
            detail?.code
              ? new ApiError(xhr.status, detail.code, detail.message ?? "Upload failed", detail.fields ?? null)
              : new ApiError(xhr.status, "http_error", `HTTP ${xhr.status}`, null),
          );
        } catch {
          reject(new ApiError(xhr.status, "http_error", `HTTP ${xhr.status}`, null));
        }
      }
    };
    xhr.onerror = () => reject(new ApiError(0, "network_error", "Сеть недоступна", null));
    xhr.send(form);
  });
}

export const api = {
  health: () => apiGet<HealthStatus>("/health"),
  overview: () => apiGet<OverviewStats>("/api/v1/overview"),
  listJobs: (params?: { status?: string; type?: string; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.type) query.set("type", params.type);
    if (params?.limit) query.set("limit", String(params.limit));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return apiGet<JobPage>(`/api/v1/jobs${suffix}`);
  },
  // videos
  uploadVideo: (file: File) => apiUpload<Video>("/api/v1/videos", file),
  listVideos: (limit = 50, offset = 0) =>
    apiGet<{ items: Video[]; total: number }>(`/api/v1/videos?limit=${limit}&offset=${offset}`),
  getVideo: (id: string) => apiGet<Video>(`/api/v1/videos/${id}`),
  transcribe: (videoId: string) =>
    apiPost<{ job_id: string }>(`/api/v1/videos/${videoId}/transcribe`),
  getTranscript: (videoId: string) =>
    apiGet<{ items: TranscriptSegment[]; total: number }>(`/api/v1/videos/${videoId}/transcript`),
  // clips
  listClips: (videoId?: string) =>
    apiGet<{ items: Clip[]; total: number }>(
      `/api/v1/clips${videoId ? `?video_id=${videoId}` : ""}`,
    ),
  createManualClip: (videoId: string, body: { title: string; start_sec: number; end_sec: number }) =>
    apiPost<Clip>(`/api/v1/videos/${videoId}/clips/manual`, body),
  patchClip: (
    clipId: string,
    body: { title?: string; start_sec?: number; end_sec?: number },
  ) => apiPatch<Clip>(`/api/v1/clips/${clipId}`, body),
  getClipAsset: (clipId: string) =>
    apiGet<RenderedAsset>(`/api/v1/clips/${clipId}/asset`),
  renderClip: (clipId: string) =>
    apiPost<Job>(`/api/v1/clips/${clipId}/render`),
  getJob: (jobId: string) => apiGet<Job>(`/api/v1/jobs/${jobId}`),
  getRender: (assetId: string) => apiGet<RenderedAsset>(`/api/v1/renders/${assetId}`),
  getRenderUrl: (assetId: string) =>
    apiGet<{ url: string; expires_sec: number }>(`/api/v1/renders/${assetId}/download`),
  // candidates
  generateCandidates: (videoId: string, topK = 5) =>
    apiPost<{ items: Candidate[]; total: number; ranked_by: string }>(
      `/api/v1/videos/${videoId}/candidates?top_k=${topK}`,
    ),
  listCandidates: (videoId: string) =>
    apiGet<{ items: Candidate[]; total: number; ranked_by: string }>(`/api/v1/videos/${videoId}/candidates`),
  promoteCandidate: (id: string, title?: string) =>
    apiPost<Clip>(`/api/v1/candidates/${id}/promote`, title ? { title } : {}),
  // texts
  generateTexts: (clipId: string, platform: string) =>
    apiPost<{ job_id: string | null; texts: GeneratedTexts; captions_srt: string }>(
      "/api/v1/texts/generate",
      { clip_id: clipId, platform },
    ),
  getClipTexts: (clipId: string, platform: string) =>
    apiGet<{ texts: GeneratedTexts | null }>(`/api/v1/clips/${clipId}/texts?platform=${platform}`),
  // publications
  manualPublish: (body: {
    clip_id: string;
    platform: string;
    platform_account_id: string;
    title: string;
    description?: string;
    privacy: string;
    scheduled_at?: string;
  }) => apiPost<Publication>("/api/v1/publications/manual", body),
  listPublications: (params?: { clip_id?: string; platform?: string }) => {
    const query = new URLSearchParams();
    if (params?.clip_id) query.set("clip_id", params.clip_id);
    if (params?.platform) query.set("platform", params.platform);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return apiGet<{ items: Publication[]; total: number }>(`/api/v1/publications${suffix}`);
  },
  // ml (Stage 7)
  activeModel: () =>
    apiGet<{ active: boolean; model_version: string | null; backend?: string }>(
      "/api/v1/ml/active-model",
    ),
  trainModel: () => apiPost<{ job_id: string }>("/api/v1/ml/train"),
  listTrainingRuns: () =>
    apiGet<{ items: TrainingRun[]; total: number }>("/api/v1/ml/runs"),
  datasetStatus: () =>
    apiGet<{ rows: number; skipped: Record<string, number>; targets: string[] }>(
      "/api/v1/ml/dataset-status"
    ),
  // metrics
  syncMetrics: (publicationId: string) =>
    apiPost<{ job_id: string }>(`/api/v1/publications/${publicationId}/sync-metrics`),
  getMetrics: (publicationId: string) =>
    apiGet<{ items: Metric[]; total: number }>(`/api/v1/publications/${publicationId}/metrics`),
  // platform accounts
  createPlatformAccount: (body: {
    platform: string;
    external_account_id: string;
    display_name?: string;
    credentials: Record<string, string>;
    scopes?: string[];
  }) => apiPost<PlatformAccount>("/api/v1/platform-accounts", body),
  listPlatformAccounts: () =>
    apiGet<{ items: PlatformAccount[]; total: number }>("/api/v1/platform-accounts"),
};

export function fmtDuration(sec: number | null): string {
  if (sec === null || sec === undefined) return "—";
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function fmtBytes(bytes: number): string {
  if (bytes > 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`;
  if (bytes > 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024).toFixed(0)} KB`;
}
