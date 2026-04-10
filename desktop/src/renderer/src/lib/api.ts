export type DeviceInfo = {
  serial: string;
  state: string;
  android_version: string | null;
  model: string | null;
  busy: boolean;
  active_run_id: number | null;
  active_run_status: string;
};

export type TaskTemplateField = {
  key: string;
  label: string;
  field_type: string;
  required: boolean;
  min_value: number | null;
  max_value: number | null;
  step: number | null;
  description: string;
};

export type TaskTemplate = {
  template_id: string;
  display_name: string;
  description: string;
  adapter: string;
  package_name: string;
  platform: string;
  default_options: Record<string, string | number>;
  light_smoke_overrides: Record<string, string | number>;
  fields: TaskTemplateField[];
};

export type AppSettings = {
  adb_path: string;
  output_dir: string;
  mysql_host: string;
  mysql_port: number;
  mysql_user: string;
  mysql_password: string;
  mysql_database: string;
  mysql_charset: string;
};

export type DoctorReport = {
  adb_available: boolean;
  adb_version: string;
  adb_path: string | null;
  dependencies: Record<string, boolean>;
  devices: DeviceInfo[];
  default_device_serial: string | null;
};

export type RunSummary = {
  id: number;
  task_name: string;
  adapter: string;
  platform: string;
  package_name: string;
  run_mode: string;
  status: string;
  device_serial: string;
  requested_at: string;
  started_at: string;
  finished_at: string;
  artifact_dir: string;
  log_path: string;
  config: Record<string, unknown>;
  result: Record<string, unknown>;
  error_message: string;
  mysql_run_id: number | null;
  items_count: number;
  comment_count: number;
  cancel_requested: boolean;
  created_at: string;
  updated_at: string;
};

export type RunRecord = {
  id: number;
  local_run_id: number;
  item_index: number;
  platform: string;
  record_type: string;
  keyword: string;
  title: string;
  content_text: string;
  author_name: string;
  author_id: string;
  location_text: string;
  ip_location: string;
  published_text: string;
  metrics: Record<string, unknown>;
  extra: Record<string, unknown>;
  raw_visible_texts: string[];
  created_at: string;
};

export type RunLogs = {
  path: string;
  content: string;
  line_count: number;
};

export type ArtifactItem = {
  name: string;
  path: string;
  is_dir: boolean;
  size: number;
  kind: string;
};

export type Keyword = {
  id: number;
  keyword: string;
  meaning: string;
  category_id: number;
  subcategory_id: number;
  category_name: string;
  subcategory_name: string;
  sort_order: number;
  created_at: string;
  updated_at: string;
};

export type KeywordSubcategory = {
  id: number;
  name: string;
  description: string;
  category_id: number;
  sort_order: number;
  keywords: Keyword[];
  created_at: string;
  updated_at: string;
};

export type KeywordCategory = {
  id: number;
  name: string;
  description: string;
  sort_order: number;
  subcategories: KeywordSubcategory[];
  keywords: Keyword[];
  created_at: string;
  updated_at: string;
};

export type JargonSourceType = "xianyu" | "xhs";

export type JargonSourceDataset = {
  source_type: JargonSourceType;
  source_task_id: number;
  source_task_name: string;
  label: string;
  record_count: number;
  created_at: string;
};

export type JargonTask = {
  id: number;
  source_type: JargonSourceType;
  source_task_id: number;
  source_task_name: string;
  keyword_id: number;
  keyword_name: string;
  keyword_meaning: string;
  category_name: string;
  subcategory_name: string;
  status: string;
  total_records: number;
  processed_records: number;
  matched_records: number;
  error_message: string;
  created_at: string;
  started_at: string;
  completed_at: string;
  updated_at: string;
};

export type MatchedKeyword = {
  task_id: number;
  keyword_id: number;
  keyword: string;
  meaning: string;
  confidence: number;
};

export type JargonSourceRecord = {
  id: number;
  platform: string;
  source_task_id: number;
  source_label: string;
  title: string;
  content: string;
  image_url: string;
  price: string | number | null;
  price_label: string;
  link: string;
  created_at: string;
  matched_keywords: MatchedKeyword[];
  analysis_status: string;
  want_count?: number | null;
  view_count?: number | null;
  seller_name?: string;
  seller_region?: string;
  author?: string;
  publish_time?: string;
  likes?: number;
  collects?: number;
  comment_count?: number;
  topics?: string[];
  ip_location?: string;
};

export type JargonTaskResultItem = {
  id: number;
  source_record_id: number;
  is_match: boolean;
  confidence: number;
  reason: string;
  record: JargonSourceRecord;
};

export type HitTracingMatch = {
  task_id: number;
  keyword_id: number;
  keyword: string;
  meaning: string;
  confidence: number;
  reason: string;
  category_name: string;
  subcategory_name: string;
  task_created_at: string;
  task_completed_at: string;
};

export type HitTracingRecordSummary = {
  id: number;
  local_run_id: number;
  item_index: number;
  platform: string;
  record_type: string;
  source_task_id: number;
  source_label: string;
  title: string;
  content: string;
  image_url: string;
  price: string | number | null;
  price_label: string;
  link: string;
  created_at: string;
  match_count: number;
  top_confidence: number;
  matches: HitTracingMatch[];
  want_count?: number | null;
  view_count?: number | null;
  seller_name?: string;
  seller_region?: string;
  author?: string;
  publish_time?: string;
  likes?: number;
  collects?: number;
  comment_count?: number;
  topics?: string[];
  ip_location?: string;
};

export type HitTracingRecordDetail = HitTracingRecordSummary & {
  author_name: string;
  author_id: string;
  location_text: string;
  published_text: string;
  metrics: Record<string, unknown>;
  extra: Record<string, unknown>;
  raw_visible_texts: string[];
};

export type PaginatedResult<T> = {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

export type FileEntry = {
  name: string;
  path: string;
  relative_path: string;
  root: string;
  size: number;
  time: string;
  type: string;
};

type ServiceEnvelope<T> = {
  ok: boolean;
  status: number;
  data: T;
  error: string;
};

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = (await window.desktopApi.request({
    method,
    path,
    body,
  })) as ServiceEnvelope<T>;
  if (!response.ok) {
    throw new Error(response.error || `请求失败：${response.status}`);
  }
  return response.data;
}

function buildQuery(params: Record<string, string | number | boolean | null | undefined>): string {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined || value === "") {
      return;
    }
    searchParams.set(key, String(value));
  });
  const query = searchParams.toString();
  return query ? `?${query}` : "";
}

export const api = {
  getDoctor: () => request<DoctorReport>("GET", "/api/system/doctor"),
  listDevices: () => request<DeviceInfo[]>("GET", "/api/system/devices"),
  listTemplates: () => request<TaskTemplate[]>("GET", "/api/task-templates"),
  getSettings: () => request<AppSettings>("GET", "/api/settings"),
  saveSettings: (body: AppSettings) => request<AppSettings>("PUT", "/api/settings", body),
  listRuns: (limit = 100) => request<RunSummary[]>("GET", `/api/runs${buildQuery({ limit })}`),
  getRun: (runId: number) => request<RunSummary>("GET", `/api/runs/${runId}`),
  createRun: (body: {
    template_id: string;
    device_serial: string | null;
    run_mode: "normal" | "light_smoke";
    adapter_options: Record<string, string | number>;
  }) => request<RunSummary>("POST", "/api/runs", body),
  cancelRun: (runId: number) => request<RunSummary>("POST", `/api/runs/${runId}/cancel`),
  getRunRecords: (runId: number) => request<RunRecord[]>("GET", `/api/runs/${runId}/records`),
  getRunLogs: (runId: number) => request<RunLogs>("GET", `/api/runs/${runId}/logs`),
  getRunArtifacts: (runId: number) => request<ArtifactItem[]>("GET", `/api/runs/${runId}/artifacts`),
  listKeywordCategories: () => request<KeywordCategory[]>("GET", "/api/keyword-categories"),
  createKeywordCategory: (body: { name: string; description: string; sort_order: number }) =>
    request<KeywordCategory>("POST", "/api/keyword-categories", body),
  updateKeywordCategory: (
    categoryId: number,
    body: Partial<{ name: string; description: string; sort_order: number }>,
  ) => request<KeywordCategory>("PUT", `/api/keyword-categories/${categoryId}`, body),
  deleteKeywordCategory: (categoryId: number) => request<void>("DELETE", `/api/keyword-categories/${categoryId}`),
  createKeywordSubcategory: (
    categoryId: number,
    body: { name: string; description: string; sort_order: number },
  ) => request<KeywordSubcategory>("POST", `/api/keyword-categories/${categoryId}/subcategories`, body),
  updateKeywordSubcategory: (
    subcategoryId: number,
    body: Partial<{ name: string; description: string; sort_order: number }>,
  ) => request<KeywordSubcategory>("PUT", `/api/keyword-subcategories/${subcategoryId}`, body),
  deleteKeywordSubcategory: (subcategoryId: number) =>
    request<void>("DELETE", `/api/keyword-subcategories/${subcategoryId}`),
  createKeyword: (
    subcategoryId: number,
    body: { keyword: string; meaning: string; sort_order: number },
  ) => request<Keyword>("POST", `/api/keyword-subcategories/${subcategoryId}/keywords`, body),
  updateKeyword: (
    keywordId: number,
    body: Partial<{ keyword: string; meaning: string; subcategory_id: number; sort_order: number }>,
  ) => request<Keyword>("PUT", `/api/keywords/${keywordId}`, body),
  deleteKeyword: (keywordId: number) => request<void>("DELETE", `/api/keywords/${keywordId}`),
  listJargonSources: () => request<JargonSourceDataset[]>("GET", "/api/jargon-analysis/sources"),
  createJargonTask: (body: { source_type: JargonSourceType; source_task_id: number; keyword_id: number }) =>
    request<JargonTask>("POST", "/api/jargon-analysis/tasks", body),
  listJargonTasks: (page = 1, pageSize = 20) =>
    request<PaginatedResult<JargonTask>>(
      "GET",
      `/api/jargon-analysis/tasks${buildQuery({ page, page_size: pageSize })}`,
    ),
  getJargonTask: (taskId: number) => request<JargonTask>("GET", `/api/jargon-analysis/tasks/${taskId}`),
  getJargonTaskResults: (taskId: number) =>
    request<{ task: JargonTask; items: JargonTaskResultItem[] }>("GET", `/api/jargon-analysis/tasks/${taskId}/results`),
  listAnalysisRecords: (params: {
    source_type: JargonSourceType;
    page?: number;
    page_size?: number;
    task_id?: number | null;
    search?: string;
    matched_only?: boolean;
  }) =>
    request<PaginatedResult<JargonSourceRecord>>("GET", `/api/jargon-analysis/records${buildQuery(params)}`),
  listHitTracingRecords: (params: {
    source_type: JargonSourceType;
    page?: number;
    page_size?: number;
    task_id?: number | null;
    search?: string;
    keyword_id?: number | null;
    category_id?: number | null;
    subcategory_id?: number | null;
    min_confidence?: number | null;
  }) =>
    request<PaginatedResult<HitTracingRecordSummary>>("GET", `/api/jargon-analysis/matches${buildQuery(params)}`),
  getHitTracingRecord: (recordId: number) =>
    request<HitTracingRecordDetail>("GET", `/api/jargon-analysis/matches/${recordId}`),
  listFiles: () => request<FileEntry[]>("GET", "/api/files"),
  deleteFile: (path: string) => request<void>("DELETE", "/api/files", { path }),
  deleteFiles: (paths: string[]) => request<void>("POST", "/api/files/batch-delete", { paths }),
  openPath: (targetPath: string) => window.desktopApi.openPath(targetPath),
  openExternal: (targetUrl: string) => window.desktopApi.openExternal(targetUrl),
};

export const ACTIVE_STATUSES = new Set(["pending", "running", "cancel_requested"]);
export const ACTIVE_JARGON_TASK_STATUSES = new Set(["pending", "running"]);

export function formatStatus(status: string): string {
  switch (status) {
    case "pending":
      return "等待中";
    case "running":
      return "运行中";
    case "cancel_requested":
      return "停止中";
    case "cancelled":
      return "已停止";
    case "success":
      return "已完成";
    case "failed":
      return "已失败";
    case "completed":
      return "已完成";
    default:
      return status;
  }
}

export function formatDateTime(value: string): string {
  return value || "--";
}

export function formatSourceType(sourceType: JargonSourceType): string {
  return sourceType === "xhs" ? "小红书" : "闲鱼";
}

export function formatAnalysisStatus(status: string): string {
  switch (status) {
    case "matched":
      return "已命中";
    case "analyzed":
      return "已研判";
    case "unanalyzed":
      return "未研判";
    default:
      return status;
  }
}

export function formatAnalysisOutcome(status: string): string {
  switch (status) {
    case "matched":
      return "命中黑话";
    case "analyzed":
      return "未命中";
    case "unanalyzed":
      return "未研判";
    default:
      return status;
  }
}

export function getAnalysisOutcomeTone(status: string): "matched" | "unmatched" | "pending" {
  switch (status) {
    case "matched":
      return "matched";
    case "analyzed":
      return "unmatched";
    default:
      return "pending";
  }
}

export function formatFileSize(size: number): string {
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  if (size < 1024 * 1024 * 1024) {
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}
