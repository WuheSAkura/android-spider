import { useEffect, useState } from "react";

import { api, AppSettings } from "@/lib/api";

const EMPTY_SETTINGS: AppSettings = {
  adb_path: "",
  output_dir: "artifacts",
  mysql_host: "127.0.0.1",
  mysql_port: 3306,
  mysql_user: "root",
  mysql_password: "123456",
  mysql_database: "android_spider",
  mysql_charset: "utf8mb4",
  ssh_enabled: false,
  ssh_host: "",
  ssh_port: 22,
  ssh_user: "",
  ssh_password: "",
  ssh_local_port: 13306,
  ssh_remote_host: "127.0.0.1",
  ssh_remote_port: 3306,
  minio_enabled: false,
  minio_public_url: "",
  minio_endpoint: "",
  minio_access_key: "",
  minio_secret_key: "",
  minio_secure: false,
  minio_bucket: "",
};

export default function SettingsPage(): React.JSX.Element {
  const [settings, setSettings] = useState<AppSettings>(EMPTY_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    void loadSettings();
  }, []);

  async function loadSettings(): Promise<void> {
    setLoading(true);
    try {
      const data = await api.getSettings();
      setSettings(data);
      setError("");
    } catch (caughtError) {
      setError((caughtError as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleSave(): Promise<void> {
    setSaving(true);
    setMessage("");
    setError("");
    try {
      const saved = await api.saveSettings(settings);
      setSettings(saved);
      setMessage("本地设置已保存。");
    } catch (caughtError) {
      const nextError = (caughtError as Error).message;
      setError(nextError);
      await window.desktopApi.showError("保存设置失败", nextError);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page-stack">
      <section className="section-heading">
        <div>
          <div className="eyebrow">Local Runtime Settings</div>
          <h1>系统设置</h1>
        </div>
        <button className="primary-button" disabled={saving} onClick={() => void handleSave()}>
          {saving ? "保存中..." : "保存设置"}
        </button>
      </section>

      {message ? <div className="inline-success">{message}</div> : null}
      {error ? <div className="inline-error">{error}</div> : null}

      {loading ? (
        <div className="panel empty-state">正在读取本地设置...</div>
      ) : (
        <div className="panel">
          <div className="field-grid field-grid-two">
            <label className="field">
              <span>ADB 路径</span>
              <input
                value={settings.adb_path}
                onChange={(event) => setSettings((current) => ({ ...current, adb_path: event.target.value }))}
              />
              <small>留空时走自动发现逻辑。</small>
            </label>
            <label className="field">
              <span>产物目录</span>
              <input
                value={settings.output_dir}
                onChange={(event) => setSettings((current) => ({ ...current, output_dir: event.target.value }))}
              />
              <small>任务截图、JSON、日志等产物的输出目录。</small>
            </label>
            <label className="field">
              <span>MySQL Host</span>
              <input
                value={settings.mysql_host}
                onChange={(event) => setSettings((current) => ({ ...current, mysql_host: event.target.value }))}
              />
            </label>
            <label className="field">
              <span>MySQL Port</span>
              <input
                type="number"
                value={String(settings.mysql_port)}
                onChange={(event) =>
                  setSettings((current) => ({ ...current, mysql_port: Number(event.target.value) }))
                }
              />
            </label>
            <label className="field">
              <span>MySQL User</span>
              <input
                value={settings.mysql_user}
                onChange={(event) => setSettings((current) => ({ ...current, mysql_user: event.target.value }))}
              />
            </label>
            <label className="field">
              <span>MySQL Password</span>
              <input
                type="password"
                value={settings.mysql_password}
                onChange={(event) =>
                  setSettings((current) => ({ ...current, mysql_password: event.target.value }))
                }
              />
            </label>
            <label className="field">
              <span>MySQL Database</span>
              <input
                value={settings.mysql_database}
                onChange={(event) =>
                  setSettings((current) => ({ ...current, mysql_database: event.target.value }))
                }
              />
            </label>
            <label className="field">
              <span>MySQL Charset</span>
              <input
                value={settings.mysql_charset}
                onChange={(event) =>
                  setSettings((current) => ({ ...current, mysql_charset: event.target.value }))
                }
              />
            </label>
            <label className="field">
              <span>启用 SSH 隧道</span>
              <input
                type="checkbox"
                checked={settings.ssh_enabled}
                onChange={(event) =>
                  setSettings((current) => ({ ...current, ssh_enabled: event.target.checked }))
                }
              />
              <small>开启后会先连 SSH，再通过本地端口访问远端 MySQL。</small>
            </label>
            <label className="field">
              <span>SSH Host</span>
              <input
                value={settings.ssh_host}
                onChange={(event) => setSettings((current) => ({ ...current, ssh_host: event.target.value }))}
              />
            </label>
            <label className="field">
              <span>SSH Port</span>
              <input
                type="number"
                value={String(settings.ssh_port)}
                onChange={(event) =>
                  setSettings((current) => ({ ...current, ssh_port: Number(event.target.value) }))
                }
              />
            </label>
            <label className="field">
              <span>SSH User</span>
              <input
                value={settings.ssh_user}
                onChange={(event) => setSettings((current) => ({ ...current, ssh_user: event.target.value }))}
              />
            </label>
            <label className="field">
              <span>SSH Password</span>
              <input
                type="password"
                value={settings.ssh_password}
                onChange={(event) =>
                  setSettings((current) => ({ ...current, ssh_password: event.target.value }))
                }
              />
            </label>
            <label className="field">
              <span>SSH Local Port</span>
              <input
                type="number"
                value={String(settings.ssh_local_port)}
                onChange={(event) =>
                  setSettings((current) => ({ ...current, ssh_local_port: Number(event.target.value) }))
                }
              />
            </label>
            <label className="field">
              <span>SSH Remote Host</span>
              <input
                value={settings.ssh_remote_host}
                onChange={(event) =>
                  setSettings((current) => ({ ...current, ssh_remote_host: event.target.value }))
                }
              />
            </label>
            <label className="field">
              <span>SSH Remote Port</span>
              <input
                type="number"
                value={String(settings.ssh_remote_port)}
                onChange={(event) =>
                  setSettings((current) => ({ ...current, ssh_remote_port: Number(event.target.value) }))
                }
              />
            </label>
            <label className="field">
              <span>启用 MinIO 上传</span>
              <input
                type="checkbox"
                checked={settings.minio_enabled}
                onChange={(event) =>
                  setSettings((current) => ({ ...current, minio_enabled: event.target.checked }))
                }
              />
              <small>任务结束后把 `artifacts/` 里的文件上传到对象存储。</small>
            </label>
            <label className="field">
              <span>MinIO Public URL</span>
              <input
                value={settings.minio_public_url}
                onChange={(event) =>
                  setSettings((current) => ({ ...current, minio_public_url: event.target.value }))
                }
              />
            </label>
            <label className="field">
              <span>MinIO Endpoint</span>
              <input
                value={settings.minio_endpoint}
                onChange={(event) =>
                  setSettings((current) => ({ ...current, minio_endpoint: event.target.value }))
                }
              />
            </label>
            <label className="field">
              <span>MinIO Access Key</span>
              <input
                value={settings.minio_access_key}
                onChange={(event) =>
                  setSettings((current) => ({ ...current, minio_access_key: event.target.value }))
                }
              />
            </label>
            <label className="field">
              <span>MinIO Secret Key</span>
              <input
                type="password"
                value={settings.minio_secret_key}
                onChange={(event) =>
                  setSettings((current) => ({ ...current, minio_secret_key: event.target.value }))
                }
              />
            </label>
            <label className="field">
              <span>MinIO Bucket</span>
              <input
                value={settings.minio_bucket}
                onChange={(event) =>
                  setSettings((current) => ({ ...current, minio_bucket: event.target.value }))
                }
              />
            </label>
            <label className="field">
              <span>MinIO Secure</span>
              <input
                type="checkbox"
                checked={settings.minio_secure}
                onChange={(event) =>
                  setSettings((current) => ({ ...current, minio_secure: event.target.checked }))
                }
              />
            </label>
          </div>
        </div>
      )}
    </div>
  );
}
