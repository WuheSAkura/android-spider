import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { ACTIVE_STATUSES, api, ArtifactItem, formatDateTime, RunLogs, RunRecord, RunSummary } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export default function RunDetailPage(): React.JSX.Element {
  const params = useParams();
  const runId = Number(params.runId);
  const [run, setRun] = useState<RunSummary | null>(null);
  const [records, setRecords] = useState<RunRecord[]>([]);
  const [logs, setLogs] = useState<RunLogs | null>(null);
  const [artifacts, setArtifacts] = useState<ArtifactItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const isActive = useMemo(() => (run ? ACTIVE_STATUSES.has(run.status) : false), [run]);

  useEffect(() => {
    void loadAll();
  }, [runId]);

  useEffect(() => {
    if (!isActive) {
      return;
    }
    const timer = window.setInterval(() => {
      void loadAll(false);
    }, 1200);
    return () => window.clearInterval(timer);
  }, [isActive, runId]);

  async function loadAll(showLoading = true): Promise<void> {
    if (showLoading) {
      setLoading(true);
    }
    try {
      const [runData, recordData, logData, artifactData] = await Promise.all([
        api.getRun(runId),
        api.getRunRecords(runId),
        api.getRunLogs(runId),
        api.getRunArtifacts(runId),
      ]);
      setRun(runData);
      setRecords(recordData);
      setLogs(logData);
      setArtifacts(artifactData);
      setError("");
    } catch (caughtError) {
      setError((caughtError as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleCancel(): Promise<void> {
    if (run === null) {
      return;
    }
    try {
      await api.cancelRun(run.id);
      await loadAll(false);
    } catch (caughtError) {
      const message = (caughtError as Error).message;
      setError(message);
      await window.desktopApi.showError("停止任务失败", message);
    }
  }

  return (
    <div className="page-stack">
      <section className="section-heading">
        <div>
          <div className="eyebrow">Run Observatory</div>
          <h1>任务详情 #{runId}</h1>
        </div>
        <div className="heading-actions">
          <button className="ghost-button" onClick={() => void loadAll()}>
            刷新
          </button>
          {isActive ? (
            <button className="danger-button" onClick={() => void handleCancel()}>
              停止任务
            </button>
          ) : null}
        </div>
      </section>

      {error ? <div className="inline-error">{error}</div> : null}

      {loading && run === null ? (
        <div className="panel empty-state">正在读取任务详情...</div>
      ) : run === null ? (
        <div className="panel empty-state">没有找到该任务。</div>
      ) : (
        <>
          <section className="detail-grid">
            <div className="panel">
              <div className="panel-header compact">
                <div>
                  <div className="eyebrow">Run Summary</div>
                  <h2>{run.platform === "xiaohongshu" ? "小红书任务" : "闲鱼任务"}</h2>
                </div>
                <StatusBadge status={run.status} />
              </div>
              <div className="kv-grid">
                <div>
                  <span>模式</span>
                  <strong>{run.run_mode === "light_smoke" ? "轻量试跑" : "正式采集"}</strong>
                </div>
                <div>
                  <span>设备</span>
                  <strong>{run.device_serial || "--"}</strong>
                </div>
                <div>
                  <span>开始时间</span>
                  <strong>{formatDateTime(run.started_at || run.requested_at)}</strong>
                </div>
                <div>
                  <span>结束时间</span>
                  <strong>{formatDateTime(run.finished_at)}</strong>
                </div>
                <div>
                  <span>采集条数</span>
                  <strong>{run.items_count}</strong>
                </div>
                <div>
                  <span>评论数量</span>
                  <strong>{run.comment_count}</strong>
                </div>
              </div>
              {run.error_message ? <div className="inline-error subtle">{run.error_message}</div> : null}
            </div>

            <div className="panel">
              <div className="panel-header compact">
                <div>
                  <div className="eyebrow">Outputs</div>
                  <h2>产物目录</h2>
                </div>
              </div>
              <div className="artifact-list">
                {artifacts.length === 0 ? (
                  <div className="empty-inline">尚未生成产物。</div>
                ) : (
                  artifacts.map((artifact) => (
                    <button
                      key={artifact.path}
                      className="artifact-item"
                      onClick={() => void api.openPath(artifact.path)}
                    >
                      <strong>{artifact.name}</strong>
                      <span>
                        {artifact.kind} / {artifact.size} bytes
                      </span>
                    </button>
                  ))
                )}
              </div>
            </div>
          </section>

          <section className="detail-grid large">
            <div className="panel">
              <div className="panel-header compact">
                <div>
                  <div className="eyebrow">Live Log</div>
                  <h2>运行日志</h2>
                </div>
                {logs?.path ? (
                  <button className="text-link-button" onClick={() => void api.openPath(logs.path)}>
                    打开日志文件
                  </button>
                ) : null}
              </div>
              <pre className="log-viewer">{logs?.content || "暂无日志输出"}</pre>
            </div>

            <div className="panel">
              <div className="panel-header compact">
                <div>
                  <div className="eyebrow">Structured Records</div>
                  <h2>结构化结果</h2>
                </div>
              </div>
              {records.length === 0 ? (
                <div className="empty-state small">当前还没有结构化记录。</div>
              ) : (
                <div className="record-list">
                  {records.slice(0, 40).map((record) => (
                    <article key={`${record.record_type}-${record.item_index}`} className="record-card">
                      <div className="record-meta">
                        <span>{record.record_type}</span>
                        <span>{record.author_name || "未知作者"}</span>
                      </div>
                      <h3>{record.title || "无标题"}</h3>
                      <p>{record.content_text || "无正文"}</p>
                    </article>
                  ))}
                </div>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
