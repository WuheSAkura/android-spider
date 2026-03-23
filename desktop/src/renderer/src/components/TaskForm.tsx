import { DeviceInfo, TaskTemplate } from "@/lib/api";

type TaskFormProps = {
  templates: TaskTemplate[];
  devices: DeviceInfo[];
  selectedTemplateId: string;
  selectedDeviceSerial: string;
  values: Record<string, string | number>;
  submitting: boolean;
  onTemplateChange: (templateId: string) => void;
  onDeviceChange: (deviceSerial: string) => void;
  onValueChange: (key: string, value: string | number) => void;
  onRun: (runMode: "normal" | "light_smoke") => void;
};

export function TaskForm(props: TaskFormProps): React.JSX.Element {
  const {
    templates,
    devices,
    selectedTemplateId,
    selectedDeviceSerial,
    values,
    submitting,
    onTemplateChange,
    onDeviceChange,
    onValueChange,
    onRun,
  } = props;

  const selectedTemplate = templates.find((item) => item.template_id === selectedTemplateId) ?? null;

  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <div className="eyebrow">Task Launchpad</div>
          <h2>发起采集任务</h2>
          <p>先选平台和设备，再决定是轻量试跑还是正式采集。</p>
        </div>
      </div>

      <div className="field-grid field-grid-two">
        <label className="field">
          <span>采集平台</span>
          <select value={selectedTemplateId} onChange={(event) => onTemplateChange(event.target.value)}>
            {templates.map((template) => (
              <option key={template.template_id} value={template.template_id}>
                {template.display_name}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>目标设备</span>
          <select value={selectedDeviceSerial} onChange={(event) => onDeviceChange(event.target.value)}>
            <option value="">默认在线设备</option>
            {devices
              .filter((device) => device.state === "device")
              .map((device) => (
                <option key={device.serial} value={device.serial}>
                  {device.model || "未知设备"} / {device.serial}
                </option>
              ))}
          </select>
        </label>
      </div>

      {selectedTemplate !== null ? (
        <>
          <div className="template-banner">
            <div className="template-chip">{selectedTemplate.display_name}</div>
            <p>{selectedTemplate.description}</p>
            <div className="smoke-note">
              轻量试跑会自动覆盖为安全的小规模参数：{Object.entries(selectedTemplate.light_smoke_overrides)
                .map(([key, value]) => `${key}=${value}`)
                .join(" / ")}
            </div>
          </div>

          <div className="field-grid">
            {selectedTemplate.fields.map((field) => {
              const fieldValue = values[field.key] ?? "";
              const inputType = field.field_type === "number" ? "number" : "text";
              return (
                <label key={field.key} className="field">
                  <span>{field.label}</span>
                  <input
                    type={inputType}
                    value={String(fieldValue)}
                    min={field.min_value ?? undefined}
                    max={field.max_value ?? undefined}
                    step={field.step ?? undefined}
                    onChange={(event) => {
                      if (field.field_type === "number") {
                        onValueChange(field.key, Number(event.target.value));
                        return;
                      }
                      onValueChange(field.key, event.target.value);
                    }}
                  />
                  <small>{field.description}</small>
                </label>
              );
            })}
          </div>
        </>
      ) : null}

      <div className="action-row">
        <button className="ghost-button" disabled={submitting} onClick={() => onRun("light_smoke")}>
          {submitting ? "提交中..." : "轻量试跑"}
        </button>
        <button className="primary-button" disabled={submitting} onClick={() => onRun("normal")}>
          {submitting ? "提交中..." : "正式采集"}
        </button>
      </div>
    </div>
  );
}
