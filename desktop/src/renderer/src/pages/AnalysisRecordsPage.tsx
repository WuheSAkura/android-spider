import { useEffect, useMemo, useState } from "react";

import {
  api,
  formatAnalysisOutcome,
  formatAnalysisStatus,
  formatDateTime,
  formatSourceType,
  getAnalysisOutcomeTone,
  JargonSourceDataset,
  JargonSourceRecord,
  JargonSourceType,
} from "@/lib/api";

export default function AnalysisRecordsPage(): React.JSX.Element {
  const [sources, setSources] = useState<JargonSourceDataset[]>([]);
  const [records, setRecords] = useState<JargonSourceRecord[]>([]);
  const [selectedSourceType, setSelectedSourceType] = useState<JargonSourceType>("xianyu");
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [matchedOnly, setMatchedOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [selectedRecord, setSelectedRecord] = useState<JargonSourceRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const filteredSources = useMemo(
    () => sources.filter((item) => item.source_type === selectedSourceType),
    [sources, selectedSourceType],
  );

  useEffect(() => {
    void loadSources();
  }, []);

  useEffect(() => {
    void loadRecords();
  }, [selectedSourceType, selectedTaskId, matchedOnly, page, pageSize]);

  async function loadSources(): Promise<void> {
    try {
      const data = await api.listJargonSources();
      setSources(data);
      const firstXianyu = data.find((item) => item.source_type === "xianyu") ?? data[0] ?? null;
      setSelectedSourceType(firstXianyu?.source_type ?? "xianyu");
      setSelectedTaskId(firstXianyu?.source_task_id ?? null);
      setError("");
    } catch (caughtError) {
      setError((caughtError as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function loadRecords(nextPage = page): Promise<void> {
    try {
      setLoading(true);
      const data = await api.listAnalysisRecords({
        source_type: selectedSourceType,
        page: nextPage,
        page_size: pageSize,
        task_id: selectedTaskId,
        search: search || undefined,
        matched_only: matchedOnly,
      });
      setRecords(data.items);
      setPage(data.page);
      setTotalPages(data.total_pages || 1);
      setTotal(data.total);
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
          <div className="eyebrow">Analysis Records</div>
          <h1>研判记录</h1>
        </div>
        <button className="ghost-button" onClick={() => void loadRecords(1)}>
          刷新
        </button>
      </section>

      {error ? <div className="inline-error">{error}</div> : null}

      <section className="panel">
        <div className="panel-header compact">
          <div>
            <div className="eyebrow">Filters</div>
            <h2>筛选条件</h2>
          </div>
        </div>
        <div className="field-grid field-grid-two">
          <label className="field">
            <span>平台</span>
            <select
              value={selectedSourceType}
              onChange={(event) => {
                const nextType = event.target.value as JargonSourceType;
                setSelectedSourceType(nextType);
                const nextSource = sources.find((item) => item.source_type === nextType) ?? null;
                setSelectedTaskId(nextSource?.source_task_id ?? null);
                setPage(1);
              }}
            >
              <option value="xianyu">闲鱼</option>
              <option value="xhs">小红书</option>
            </select>
          </label>

          <label className="field">
            <span>数据源任务</span>
            <select
              value={selectedTaskId ?? ""}
              onChange={(event) => {
                setSelectedTaskId(Number(event.target.value || 0) || null);
                setPage(1);
              }}
            >
              {filteredSources.length === 0 ? <option value="">暂无可浏览数据</option> : null}
              {filteredSources.map((item) => (
                <option key={`${item.source_type}-${item.source_task_id}`} value={item.source_task_id}>
                  {item.source_task_name} · {item.record_count} 条
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>搜索标题/正文</span>
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="输入关键词" />
          </label>

          <label className="field">
            <span>命中过滤</span>
            <select
              value={matchedOnly ? "matched" : "all"}
              onChange={(event) => {
                setMatchedOnly(event.target.value === "matched");
                setPage(1);
              }}
            >
              <option value="all">全部记录</option>
              <option value="matched">仅命中记录</option>
            </select>
          </label>
        </div>
        <div className="action-row top-space">
          <button className="primary-button" onClick={() => void loadRecords(1)}>
            应用筛选
          </button>
          <span className="muted-text">当前共 {total} 条记录</span>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header compact">
          <div>
            <div className="eyebrow">Record Stream</div>
            <h2>记录列表</h2>
          </div>
        </div>
        {loading ? (
          <div className="empty-state small">正在加载记录...</div>
        ) : records.length === 0 ? (
          <div className="empty-state small">当前筛选条件下没有记录。</div>
        ) : (
          <div className="stack-list">
            {records.map((item) => (
              <article key={item.id} className={`result-card outcome-${getAnalysisOutcomeTone(item.analysis_status)}`}>
                <div className={`analysis-outcome-banner outcome-${getAnalysisOutcomeTone(item.analysis_status)}`}>
                  <div>
                    <strong>{formatAnalysisOutcome(item.analysis_status)}</strong>
                    <span>{formatAnalysisStatus(item.analysis_status)}</span>
                  </div>
                </div>
                <div className="inline-between">
                  <strong>{item.title || "无标题"}</strong>
                  <span className="muted-text">{item.matched_keywords.length > 0 ? `命中 ${item.matched_keywords.length} 个黑话` : "无命中黑话"}</span>
                </div>
                <p>{item.content || "无正文"}</p>
                <div className="chip-row">
                  <span className="status-chip">{formatSourceType(selectedSourceType)}</span>
                  <span className="status-chip">{formatDateTime(item.created_at)}</span>
                  {item.price_label ? <span className="status-chip">{item.price_label}</span> : null}
                  {item.author ? <span className="status-chip">{item.author}</span> : null}
                  {item.seller_name ? <span className="status-chip">{item.seller_name}</span> : null}
                </div>
                <div className="chip-row">
                  {item.matched_keywords.map((keyword) => (
                    <span key={`${item.id}-${keyword.keyword_id}`} className="match-chip">
                      {keyword.keyword} / {keyword.meaning}
                    </span>
                  ))}
                </div>
                <div className="action-row">
                  <button className="text-link-button" onClick={() => setSelectedRecord(item)}>
                    查看详情
                  </button>
                  {item.link ? (
                    <button className="text-link-button" onClick={() => void api.openExternal(item.link)}>
                      打开链接
                    </button>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        )}
        <div className="pagination-bar">
          <button className="ghost-button" disabled={page <= 1} onClick={() => void loadRecords(page - 1)}>
            上一页
          </button>
          <span>
            第 {page} / {totalPages} 页
          </span>
          <button className="ghost-button" disabled={page >= totalPages} onClick={() => void loadRecords(page + 1)}>
            下一页
          </button>
        </div>
      </section>

      {selectedRecord !== null ? (
        <div className="modal-backdrop" onClick={() => setSelectedRecord(null)}>
          <div className="modal-card wide" onClick={(event) => event.stopPropagation()}>
            <div className="panel-header compact">
              <div>
                <div className="eyebrow">Record Detail</div>
                <h2>{selectedRecord.title || "无标题"}</h2>
              </div>
              <button className="ghost-button" onClick={() => setSelectedRecord(null)}>
                关闭
              </button>
            </div>
            <div className={`analysis-outcome-banner detail outcome-${getAnalysisOutcomeTone(selectedRecord.analysis_status)}`}>
              <div>
                <strong>{formatAnalysisOutcome(selectedRecord.analysis_status)}</strong>
                <span>
                  {selectedRecord.matched_keywords.length > 0
                    ? `已命中 ${selectedRecord.matched_keywords.length} 个黑话词条`
                    : "当前记录已完成研判，但未命中黑话"}
                </span>
              </div>
            </div>
            <div className="summary-strip">
              <span>{formatSourceType(selectedSourceType)}</span>
              <span>{formatAnalysisStatus(selectedRecord.analysis_status)}</span>
              <span>{formatDateTime(selectedRecord.created_at)}</span>
            </div>
            <div className="detail-copy">
              <p>{selectedRecord.content || "无正文"}</p>
            </div>
            <div className="chip-row">
              {selectedRecord.matched_keywords.map((keyword) => (
                <span key={`${selectedRecord.id}-${keyword.keyword_id}`} className="match-chip">
                  {keyword.keyword} / {keyword.meaning} / {Math.round(keyword.confidence)}
                </span>
              ))}
            </div>
            <div className="kv-grid top-space">
              <div>
                <span>数据源任务</span>
                <strong>#{selectedRecord.source_task_id}</strong>
              </div>
              <div>
                <span>来源标签</span>
                <strong>{selectedRecord.source_label || "--"}</strong>
              </div>
              <div>
                <span>价格/作者</span>
                <strong>{selectedRecord.price_label || selectedRecord.author || selectedRecord.seller_name || "--"}</strong>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
