export type DeviceInfo = {
  serial: string;
  state: string;
  android_version: string | null;
  model: string | null;
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

export const api = {
  getDoctor: () => request<DoctorReport>("GET", "/api/system/doctor"),
  listDevices: () => request<DeviceInfo[]>("GET", "/api/system/devices"),
  listTemplates: () => request<TaskTemplate[]>("GET", "/api/task-templates"),
  getSettings: () => request<AppSettings>("GET", "/api/settings"),
  saveSettings: (body: AppSettings) => request<AppSettings>("PUT", "/api/settings", body),
  listRuns: () => request<RunSummary[]>("GET", "/api/runs"),
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
  openPath: (targetPath: string) => window.desktopApi.openPath(targetPath),
};

export const ACTIVE_STATUSES = new Set(["pending", "running", "cancel_requested"]);

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
    default:
      return status;
  }
}

export function formatDateTime(value: string): string {
  return value || "--";
}
