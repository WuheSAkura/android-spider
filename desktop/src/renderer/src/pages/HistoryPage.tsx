import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api, formatDateTime, RunSummary } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export default function HistoryPage(): React.JSX.Element {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    void loadRuns();
    const timer = window.setInterval(() => {
      void loadRuns();
    }, 4000);
    return () => window.clearInterval(timer);
  }, []);

  async function loadRuns(): Promise<void> {
    try {
      const data = await api.listRuns();
      setRuns(data);
      setError("");
    } catch (caughtError) {
      setError((caughtError as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page-stack">
      <section className="section-heading">
        <div>
          <div className="eyebrow">Run Ledger</div>
          <h1>运行历史</h1>
        </div>
        <button className="ghost-button" onClick={() => void loadRuns()}>
          刷新列表
        </button>
      </section>

      {error ? <div className="inline-error">{error}</div> : null}

      <div className="panel">
        {loading ? (
          <div className="empty-state">正在加载运行历史...</div>
        ) : runs.length === 0 ? (
          <div className="empty-state">还没有运行记录。</div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>平台</th>
                <th>状态</th>
                <th>模式</th>
                <th>设备</th>
                <th>时间</th>
                <th>结果</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
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
                    {run.items_count} 条 / {run.comment_count} 评论
                  </td>
                  <td>
                    <Link className="text-link" to={`/runs/${run.id}`}>
                      查看详情
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
