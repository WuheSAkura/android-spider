import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { ACTIVE_STATUSES, api, DeviceInfo, DoctorReport, formatDateTime, RunSummary, TaskTemplate } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { TaskForm } from "@/components/TaskForm";

export default function DashboardPage(): React.JSX.Element {
  const [templates, setTemplates] = useState<TaskTemplate[]>([]);
  const [devices, setDevices] = useState<DeviceInfo[]>([]);
  const [doctor, setDoctor] = useState<DoctorReport | null>(null);
  const [activeRuns, setActiveRuns] = useState<RunSummary[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [selectedDeviceSerial, setSelectedDeviceSerial] = useState("");
  const [values, setValues] = useState<Record<string, string | number>>({});
  const [submitting, setSubmitting] = useState(false);
  const [stoppingRunId, setStoppingRunId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [successRunId, setSuccessRunId] = useState<number | null>(null);

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
      if (templateData.length > 0) {
        const nextTemplate = templateData[0];
        setSelectedTemplateId(nextTemplate.template_id);
        setValues(nextTemplate.default_options);
      }
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
    setSelectedTemplateId(templateId);
    const template = templates.find((item) => item.template_id === templateId);
    if (template !== undefined) {
      setValues(template.default_options);
    }
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
      setSelectedDeviceSerial("");
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
            onDeviceChange={setSelectedDeviceSerial}
            onValueChange={(key, value) => setValues((current) => ({ ...current, [key]: value }))}
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
