import type {
  AgentRun,
  AgentRunDetail,
  AppSettings,
  BatchResponse,
  FetcherType,
  JobDetail,
  JobSummary,
  PaginatedJobs,
  Schedule,
  ScheduleRun,
  ScrapeResult,
} from "@/types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw Object.assign(new Error(err.detail ?? "Request failed"), { status: res.status, body: err });
  }
  return res.json() as Promise<T>;
}

// ── Jobs ───────────────────────────────────────────────────────────────────

export function fetchJobs(params?: {
  status?: string;
  page?: number;
  page_size?: number;
  search?: string;
  batch_id?: string;
}): Promise<PaginatedJobs> {
  const qs = new URLSearchParams();
  if (params?.status) qs.set("status", params.status);
  if (params?.page) qs.set("page", String(params.page));
  if (params?.page_size) qs.set("page_size", String(params.page_size));
  if (params?.search) qs.set("search", params.search);
  if (params?.batch_id) qs.set("batch_id", params.batch_id);
  return request<PaginatedJobs>(`/jobs?${qs}`);
}

export function createBatchJob(data: {
  prompt: string;
  urls: string[];
  fetcher_type?: FetcherType;
  max_pages?: number;
}): Promise<BatchResponse> {
  return request<BatchResponse>("/jobs/batch", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function fetchBatch(batchId: string): Promise<{ batch_id: string; jobs: JobSummary[] }> {
  return request<{ batch_id: string; jobs: JobSummary[] }>(`/jobs/batch/${batchId}`);
}

export function fetchJob(id: string): Promise<JobDetail> {
  return request<JobDetail>(`/jobs/${id}`);
}

export function createJob(data: {
  prompt?: string;
  url: string;
  fetcher_type?: FetcherType;
  max_pages?: number;
}): Promise<JobDetail> {
  return request<JobDetail>("/jobs/", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function cancelJob(id: string): Promise<void> {
  return request<void>(`/jobs/${id}`, { method: "DELETE" });
}

export function retryJob(id: string): Promise<JobDetail> {
  return request<JobDetail>(`/jobs/${id}/retry`, { method: "POST" });
}

export function fetchJobResults(jobId: string): Promise<ScrapeResult> {
  return request<ScrapeResult>(`/jobs/${jobId}/results`);
}

// ── Results ────────────────────────────────────────────────────────────────

export function getExportUrl(resultId: string, format: "json" | "csv"): string {
  return `${BASE}/results/${resultId}/export?format=${format}`;
}

// ── Settings ───────────────────────────────────────────────────────────────

export function fetchSettings(): Promise<AppSettings> {
  return request<AppSettings>("/settings/");
}

export function updateSettings(data: Partial<AppSettings>): Promise<AppSettings> {
  return request<AppSettings>("/settings/", {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

// ── Agents ──────────────────────────────────────────────────────────────────

export function createAgentRun(goal: string, context?: string): Promise<AgentRun> {
  return request<AgentRun>("/agents/", {
    method: "POST",
    body: JSON.stringify({ goal, ...(context ? { context } : {}) }),
  });
}

export function fetchAgentRuns(limit = 20): Promise<AgentRun[]> {
  return request<AgentRun[]>(`/agents/?limit=${limit}`);
}

export function fetchAgentRun(id: string): Promise<AgentRunDetail> {
  return request<AgentRunDetail>(`/agents/${id}`);
}

export function cancelAgentRun(id: string): Promise<void> {
  return request<void>(`/agents/${id}`, { method: "DELETE" });
}

export function agentStreamUrl(id: string): string {
  return `${BASE}/agents/${id}/stream`;
}

// ── Schedules ────────────────────────────────────────────────────────────────

export function fetchSchedules(): Promise<Schedule[]> {
  return request<Schedule[]>("/schedules/");
}

export function createSchedule(data: {
  url: string;
  prompt: string;
  fetcher_type?: string;
  max_pages?: number;
  interval_minutes: number;
}): Promise<Schedule> {
  return request<Schedule>("/schedules/", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function updateSchedule(
  id: string,
  data: { enabled?: boolean; interval_minutes?: number }
): Promise<Schedule> {
  return request<Schedule>(`/schedules/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export function deleteSchedule(id: string): Promise<void> {
  return request<void>(`/schedules/${id}`, { method: "DELETE" });
}

export function fetchScheduleRuns(id: string): Promise<ScheduleRun[]> {
  return request<ScheduleRun[]>(`/schedules/${id}/runs`);
}
