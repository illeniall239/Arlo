export type JobStatus =
  | "pending"
  | "planning"
  | "running"
  | "structuring"
  | "completed"
  | "failed"
  | "cancelled";

export type FetcherType = "Fetcher" | "StealthyFetcher" | "DynamicFetcher" | "auto";

export interface JobSummary {
  id: string;
  prompt: string;
  url: string;
  status: JobStatus;
  fetcher_type: FetcherType;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  retry_count: number;
  batch_id: string | null;
}

export interface BatchResponse {
  batch_id: string;
  jobs: JobDetail[];
}

export interface JobDetail extends JobSummary {
  selectors: string | null;
  pagination_strategy: string | null;
  error: string | null;
  parent_job_id: string | null;
}

export interface ChangedRecord {
  key: string;
  changes: Record<string, { from: unknown; to: unknown }>;
}

export interface Diff {
  added: number;
  removed: number;
  changed: number;
  added_records: Record<string, unknown>[];
  removed_records: Record<string, unknown>[];
  changed_records: ChangedRecord[];
}

export interface ScrapeResult {
  id: string;
  job_id: string;
  structured_data: Record<string, unknown>[];
  row_count: number;
  schema_detected: string[];
  diff: Diff | null;
  created_at: string;
}

export interface Schedule {
  id: string;
  url: string;
  prompt: string;
  fetcher_type: string;
  max_pages: number;
  interval_minutes: number;
  enabled: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
  last_job_id: string | null;
  last_status: string | null;
  created_at: string;
}

export interface ScheduleRun {
  id: string;
  status: string;
  created_at: string;
  completed_at: string | null;
  row_count: number | null;
  diff: Diff | null;
}

export interface PaginatedJobs {
  data: JobSummary[];
  meta: {
    total: number;
    page: number;
    page_size: number;
    pages: number;
  };
}

export interface AppSettings {
  proxy_list: string[];
  default_fetcher: string;
  concurrency_limit: number;
  rate_limit_delay: number;
  respect_robots_txt: boolean;
}

export interface SSEEvent {
  type: "status" | "progress" | "done" | "error";
  message?: string;
  rows_found?: number;
  result_id?: string;
  rows?: number;
  detail?: string;
}

// ── Agent types ─────────────────────────────────────────────────────────────

export type AgentStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface AgentRun {
  id: string;
  goal: string;
  status: AgentStatus;
  summary: string | null;
  iterations: number;
  created_at: string;
  completed_at: string | null;
  error: string | null;
}

export interface AgentRunDetail extends AgentRun {
  trace:              string | null;   // JSON string
  result:             string | null;   // JSON string
  formatted_response: string | null;   // Markdown narrative
}

export interface AgentSSEEvent {
  type: "status" | "progress" | "done" | "error";
  message?:            string;
  rows?:               number;
  summary?:            string;
  formatted_response?: string;
  detail?:             string;
}
