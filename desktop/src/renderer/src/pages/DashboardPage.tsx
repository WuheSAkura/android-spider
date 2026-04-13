import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { ACTIVE_STATUSES, api, DeviceInfo, DoctorReport, formatDateTime, RunSummary, TaskTemplate } from "@/lib/api";
import { usePersistentState } from "@/lib/persistentState";
import { StatusBadge } from "@/components/StatusBadge";
import { TaskForm } from "@/components/TaskForm";

type TemplateDraftValues = Record<string, Record<string, string | number>>;

type TaskFormDraft = {
  selectedTemplateId: string;
  selectedDeviceSerial: string;
  templateValues: TemplateDraftValues;
};

const DEFAULT_TASK_FORM_DRAFT: TaskFormDraft = {
  selectedTemplateId: "",
  selectedDeviceSerial: "",
  templateValues: {},
};

function buildTemplateValues(
  template: TaskTemplate,
  draftValues: Record<string, string | number> | undefined,
): Record<string, string | number> {
  const allowedKeys = new Set(template.fields.map((field) => field.key));
  const nextValues: Record<string, string | number> = { ...template.default_options };

  Object.entries(draftValues ?? {}).forEach(([key, value]) => {
    if (allowedKeys.has(key)) {
      nextValues[key] = value;
    }
  });

  return nextValues;
}

function normalizeTemplateDraftValues(templates: TaskTemplate[], draftValues: TemplateDraftValues): TemplateDraftValues {
  const nextDraftValues: TemplateDraftValues = {};
  templates.forEach((template) => {
    nextDraftValues[template.template_id] = buildTemplateValues(template, draftValues[template.template_id]);
  });
  return nextDraftValues;
}

function resolveTemplateId(templates: TaskTemplate[], currentTemplateId: string): string {
  if (templates.some((template) => template.template_id === currentTemplateId)) {
    return currentTemplateId;
  }
  return templates[0]?.template_id ?? "";
}

function resolveDeviceSerial(devices: DeviceInfo[], currentDeviceSerial: string): string {
  if (currentDeviceSerial === "") {
    return "";
  }

  const selectedDevice = devices.find((device) => device.serial === currentDeviceSerial);
  if (selectedDevice === undefined || selectedDevice.state !== "device" || selectedDevice.busy) {
    return "";
  }

  return currentDeviceSerial;
}

export default function DashboardPage(): React.JSX.Element {
  const [templates, setTemplates] = useState<TaskTemplate[]>([]);
  const [devices, setDevices] = useState<DeviceInfo[]>([]);
  const [doctor, setDoctor] = useState<DoctorReport | null>(null);
  const [activeRuns, setActiveRuns] = useState<RunSummary[]>([]);
  const [taskFormDraft, setTaskFormDraft] = usePersistentState<TaskFormDraft>(
    "pages/dashboard/task-form",
    DEFAULT_TASK_FORM_DRAFT,
  );
  const [submitting, setSubmitting] = useState(false);
  const [stoppingRunId, setStoppingRunId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [successRunId, setSuccessRunId] = useState<number | null>(null);

  const { selectedTemplateId, selectedDeviceSerial, templateValues } = taskFormDraft;

  useEffect(() => {
    void loadInitialData();
    const timer = window.setInterval(() => {
      void loadRuntimeData();
    }, 4000);
    return () => window.clearInterval(timer);
  }, []);

  const selectedTemplate = useMemo(
    () => templates.find((item) => item.template_id === selectedTemplateId) ?? null,
    [selectedTemplateId, templates],
  );
  const values = useMemo<Record<string, string | number>>(
    () => (selectedTemplate === null ? {} : buildTemplateValues(selectedTemplate, templateValues[selectedTemplate.template_id])),
    [selectedTemplate, templateValues],
  );

  async function loadInitialData(): Promise<void> {
    setLoading(true);
    setError("");
    try {
      const [templateData, doctorData, runData] = await Promise.all([
        api.listTemplates(),
        api.getDoctor(),
        api.listRuns(),
      ]);
      setTemplates(templateData);
      applyRuntimeData(doctorData, runData);
      setTaskFormDraft((currentDraft) => ({
        selectedTemplateId: resolveTemplateId(templateData, currentDraft.selectedTemplateId),
        selectedDeviceSerial: resolveDeviceSerial(doctorData.devices, currentDraft.selectedDeviceSerial),
        templateValues: normalizeTemplateDraftValues(templateData, currentDraft.templateValues),
      }));
    } catch (caughtError) {
      setError((caughtError as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function loadRuntimeData(): Promise<void> {
    try {
      const [doctorData, runData] = await Promise.all([api.getDoctor(), api.listRuns()]);
      applyRuntimeData(doctorData, runData);
      setError("");
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  function applyRuntimeData(doctorData: DoctorReport, runData: RunSummary[]): void {
    setDoctor(doctorData);
    setDevices(doctorData.devices);
    setActiveRuns(runData.filter((item) => ACTIVE_STATUSES.has(item.status)));
  }

  function handleTemplateChange(templateId: string): void {
    const template = templates.find((item) => item.template_id === templateId);
    setTaskFormDraft((currentDraft) => ({
      ...currentDraft,
      selectedTemplateId: templateId,
      templateValues:
        template === undefined
          ? currentDraft.templateValues
          : {
              ...currentDraft.templateValues,
              [templateId]: buildTemplateValues(template, currentDraft.templateValues[templateId]),
            },
    }));
  }

  function handleDeviceChange(deviceSerial: string): void {
    setTaskFormDraft((currentDraft) => ({
      ...currentDraft,
      selectedDeviceSerial: deviceSerial,
    }));
  }

  function handleValueChange(key: string, value: string | number): void {
    if (selectedTemplate === null) {
      return;
    }

    setTaskFormDraft((currentDraft) => ({
      ...currentDraft,
      templateValues: {
        ...currentDraft.templateValues,
        [selectedTemplate.template_id]: {
          ...buildTemplateValues(selectedTemplate, currentDraft.templateValues[selectedTemplate.template_id]),
          [key]: value,
        },
      },
    }));
  }

  async function handleRun(runMode: "normal" | "light_smoke"): Promise<void> {
    if (selectedTemplate === null) {
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const run = await api.createRun({
        template_id: selectedTemplate.template_id,
        device_serial: selectedDeviceSerial || null,
        run_mode: runMode,
        adapter_options: values,
      });
      setSuccessRunId(run.id);
      setTaskFormDraft((currentDraft) => ({
        ...currentDraft,
        selectedDeviceSerial: "",
      }));
      await loadRuntimeData();
    } catch (caughtError) {
      const message = (caughtError as Error).message;
      setError(message);
      await window.desktopApi.showError("启动任务失败", message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCancelRun(runId: number): Promise<void> {
    setStoppingRunId(runId);
    setError("");
    try {
      await api.cancelRun(runId);
      await loadRuntimeData();
    } catch (caughtError) {
      const message = (caughtError as Error).message;
      setError(message);
      await window.desktopApi.showError("停止任务失败", message);
    } finally {
      setStoppingRunId(null);
    }
  }

  return (
    <div className="page-stack">
      <section className="hero-card">
        <div>
          <div className="eyebrow">Android Spider Console</div>
          <h1>把现有采集脚本变成可操作的桌面控制台</h1>
          <p>当前版本已支持多设备并行采集，规则是“单设备互斥、空闲设备自动分配”。</p>
        </div>
        <div className="hero-grid">
          <div className="hero-metric">
            <strong>{doctor?.adb_available ? "ADB 已就绪" : "ADB 未就绪"}</strong>
            <span>{doctor?.adb_path || "尚未识别到 adb 路径"}</span>
          </div>
          <div className="hero-metric">
            <strong>
              {devices.filter((item) => item.state === "device").length} 台在线 /{" "}
              {devices.filter((item) => item.state === "device" && !item.busy).length} 台空闲
            </strong>
            <span>支持指定空闲设备，也支持自动分配空闲设备。</span>
          </div>
          <div className="hero-metric">
            <strong>{templates.length} 个采集模板</strong>
            <span>基于现有小红书 / 闲鱼脚本自动整理。</span>
          </div>
        </div>
      </section>

      {error ? <div className="inline-error">{error}</div> : null}
      {successRunId !== null ? (
        <div className="inline-success">
          已启动任务 #{successRunId}，当前页面不会跳走，你可以继续为其他空闲设备发起任务。
          {" "}
          <Link className="text-link" to={`/runs/${successRunId}`}>
            查看详情
          </Link>
        </div>
      ) : null}

      {loading ? (
        <div className="panel empty-state">正在加载任务模板和设备信息...</div>
      ) : (
        <>
          <TaskForm
            templates={templates}
            devices={devices}
            selectedTemplateId={selectedTemplateId}
            selectedDeviceSerial={selectedDeviceSerial}
            values={values}
            submitting={submitting}
            onTemplateChange={handleTemplateChange}
            onDeviceChange={handleDeviceChange}
            onValueChange={handleValueChange}
            onRun={handleRun}
          />

          <section className="panel">
            <div className="panel-header compact">
              <div>
                <div className="eyebrow">Active Runs</div>
                <h2>运行中任务</h2>
                <p>已启动的任务会在后台继续执行。你可以留在当前页继续选择其他空闲设备发起任务。</p>
              </div>
              <button className="ghost-button" onClick={() => void loadRuntimeData()}>
                刷新状态
              </button>
            </div>

            {activeRuns.length === 0 ? (
              <div className="empty-state small">当前没有运行中的任务。</div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>平台</th>
                    <th>状态</th>
                    <th>模式</th>
                    <th>设备</th>
                    <th>开始时间</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {activeRuns.map((run) => (
                    <tr key={run.id}>
                      <td>#{run.id}</td>
                      <td>{run.platform}</td>
                      <td>
                        <StatusBadge status={run.status} />
                      </td>
                      <td>{run.run_mode === "light_smoke" ? "轻量试跑" : "正式采集"}</td>
                      <td>{run.device_serial || "--"}</td>
                      <td>{formatDateTime(run.started_at || run.requested_at)}</td>
                      <td>
                        <div className="action-row compact-end">
                          <Link className="text-link" to={`/runs/${run.id}`}>
                            查看详情
                          </Link>
                          <button
                            className="text-link-button danger-text"
                            disabled={stoppingRunId === run.id || run.status === "cancel_requested"}
                            onClick={() => void handleCancelRun(run.id)}
                          >
                            {stoppingRunId === run.id ? "停止中..." : "停止任务"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}
    </div>
  );
}
