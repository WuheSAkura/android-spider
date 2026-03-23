import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, DeviceInfo, DoctorReport, TaskTemplate } from "@/lib/api";
import { TaskForm } from "@/components/TaskForm";

export default function DashboardPage(): React.JSX.Element {
  const navigate = useNavigate();
  const [templates, setTemplates] = useState<TaskTemplate[]>([]);
  const [devices, setDevices] = useState<DeviceInfo[]>([]);
  const [doctor, setDoctor] = useState<DoctorReport | null>(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [selectedDeviceSerial, setSelectedDeviceSerial] = useState("");
  const [values, setValues] = useState<Record<string, string | number>>({});
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    void loadInitialData();
  }, []);

  const selectedTemplate = useMemo(
    () => templates.find((item) => item.template_id === selectedTemplateId) ?? null,
    [selectedTemplateId, templates],
  );

  async function loadInitialData(): Promise<void> {
    setLoading(true);
    setError("");
    try {
      const [templateData, deviceData, doctorData] = await Promise.all([
        api.listTemplates(),
        api.listDevices(),
        api.getDoctor(),
      ]);
      setTemplates(templateData);
      setDevices(deviceData);
      setDoctor(doctorData);
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
      navigate(`/runs/${run.id}`);
    } catch (caughtError) {
      const message = (caughtError as Error).message;
      setError(message);
      await window.desktopApi.showError("启动任务失败", message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page-stack">
      <section className="hero-card">
        <div>
          <div className="eyebrow">Android Spider Console</div>
          <h1>把现有采集脚本变成可操作的桌面控制台</h1>
          <p>这版先聚焦在“发任务、看状态、查结果、快速停止”。先把可视化操作闭环打通，再继续迭代多设备和调度。</p>
        </div>
        <div className="hero-grid">
          <div className="hero-metric">
            <strong>{doctor?.adb_available ? "ADB 已就绪" : "ADB 未就绪"}</strong>
            <span>{doctor?.adb_path || "尚未识别到 adb 路径"}</span>
          </div>
          <div className="hero-metric">
            <strong>{devices.filter((item) => item.state === "device").length} 台在线设备</strong>
            <span>支持指定设备，也支持默认首台在线设备。</span>
          </div>
          <div className="hero-metric">
            <strong>{templates.length} 个采集模板</strong>
            <span>基于现有小红书 / 闲鱼脚本自动整理。</span>
          </div>
        </div>
      </section>

      {error ? <div className="inline-error">{error}</div> : null}

      {loading ? (
        <div className="panel empty-state">正在加载任务模板和设备信息...</div>
      ) : (
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
      )}
    </div>
  );
}
