import { useEffect, useMemo, useState } from "react";

import {
  api,
  formatDateTime,
  formatSourceType,
  HitTracingRecordDetail,
  HitTracingRecordSummary,
  JargonSourceDataset,
  JargonSourceType,
  Keyword,
  KeywordCategory,
} from "@/lib/api";

type MatchFilters = {
  sourceType: JargonSourceType;
  taskId: number | null;
  categoryId: number | null;
  subcategoryId: number | null;
  keywordId: number | null;
  search: string;
  minConfidence: string;
};

const DEFAULT_FILTERS: MatchFilters = {
  sourceType: "xianyu",
  taskId: null,
  categoryId: null,
  subcategoryId: null,
  keywordId: null,
  search: "",
  minConfidence: "",
};

function formatMatchConfidence(value: number): string {
  return `${Math.round(value)}%`;
}

function formatJson(value: Record<string, unknown>): string {
  return JSON.stringify(value, null, 2);
}

export default function HitTracingPage(): React.JSX.Element {
  const [sources, setSources] = useState<JargonSourceDataset[]>([]);
  const [categories, setCategories] = useState<KeywordCategory[]>([]);
  const [records, setRecords] = useState<HitTracingRecordSummary[]>([]);
  const [filters, setFilters] = useState<MatchFilters>(DEFAULT_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<MatchFilters>(DEFAULT_FILTERS);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [selectedRecordId, setSelectedRecordId] = useState<number | null>(null);
  const [selectedRecord, setSelectedRecord] = useState<HitTracingRecordDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const filteredSources = useMemo(
    () => sources.filter((item) => item.source_type === filters.sourceType),
    [filters.sourceType, sources],
  );
  const selectedCategory = useMemo(
    () => categories.find((item) => item.id === filters.categoryId) ?? null,
    [categories, filters.categoryId],
  );
  const selectedSubcategory = useMemo(
    () => selectedCategory?.subcategories.find((item) => item.id === filters.subcategoryId) ?? null,
    [selectedCategory, filters.subcategoryId],
  );
  const keywordOptions = useMemo(() => {
    if (selectedSubcategory !== null) {
      return selectedSubcategory.keywords;
    }
    if (selectedCategory !== null) {
      return selectedCategory.keywords;
    }
    return categories.flatMap((item) => item.keywords);
  }, [categories, selectedCategory, selectedSubcategory]);

  useEffect(() => {
    void loadPageData();
  }, []);

  async function loadPageData(): Promise<void> {
    setLoading(true);
    try {
      const [sourceItems, categoryItems] = await Promise.all([
        api.listJargonSources(),
        api.listKeywordCategories(),
      ]);
      setSources(sourceItems);
      setCategories(categoryItems);
      setError("");
      await loadRecords(1, DEFAULT_FILTERS, false);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function loadRecords(nextPage = page, nextFilters = appliedFilters, showLoading = true): Promise<void> {
    try {
      if (showLoading) {
        setLoading(true);
      }
      const minConfidence = nextFilters.minConfidence.trim();
      const data = await api.listHitTracingRecords({
        source_type: nextFilters.sourceType,
        page: nextPage,
        page_size: pageSize,
        task_id: nextFilters.taskId,
        search: nextFilters.search.trim() || undefined,
        keyword_id: nextFilters.keywordId,
        category_id: nextFilters.categoryId,
        subcategory_id: nextFilters.subcategoryId,
        min_confidence: minConfidence === "" ? null : Number(minConfidence),
      });
      setRecords(data.items);
      setPage(data.page);
      setTotalPages(data.total_pages || 1);
      setTotal(data.total);
      setError("");
    } catch (caughtError) {
      setError((caughtError as Error).message);
    } finally {
      if (showLoading) {
        setLoading(false);
      }
    }
  }

  async function openRecordDetail(recordId: number): Promise<void> {
    setSelectedRecordId(recordId);
    setSelectedRecord(null);
    setDetailError("");
    setDetailLoading(true);

    try {
      const data = await api.getHitTracingRecord(recordId);
      setSelectedRecord(data);
    } catch (caughtError) {
      setDetailError((caughtError as Error).message);
    } finally {
      setDetailLoading(false);
    }
  }

  function closeDetail(): void {
    setSelectedRecordId(null);
    setSelectedRecord(null);
    setDetailError("");
    setDetailLoading(false);
  }

  function applyFilters(): void {
    setAppliedFilters(filters);
    void loadRecords(1, filters);
  }

  function resetFilters(): void {
    setFilters(DEFAULT_FILTERS);
    setAppliedFilters(DEFAULT_FILTERS);
    void loadRecords(1, DEFAULT_FILTERS);
  }

  function formatKeywordOption(item: Keyword): string {
    return `${item.keyword} / ${item.meaning} / ${item.subcategory_name}`;
  }

  return (
    <div className="page-stack hit-tracing-page">
      <section className="section-heading">
        <div>
          <div className="eyebrow">Hit Tracing</div>
          <h1>命中溯源</h1>
        </div>
        <button className="ghost-button" onClick={() => void loadRecords(1, appliedFilters)}>
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
        <div className="field-grid hit-filter-grid">
          <label className="field">
            <span>平台</span>
            <select
              value={filters.sourceType}
              onChange={(event) =>
                setFilters((state) => ({
                  ...state,
                  sourceType: event.target.value as JargonSourceType,
                  taskId: null,
                }))
              }
            >
              <option value="xianyu">闲鱼</option>
              <option value="xhs">小红书</option>
            </select>
          </label>

          <label className="field">
            <span>采集任务</span>
            <select
              value={filters.taskId ?? ""}
              onChange={(event) =>
                setFilters((state) => ({
                  ...state,
                  taskId: Number(event.target.value || 0) || null,
                }))
              }
            >
              <option value="">全部任务</option>
              {filteredSources.map((item) => (
                <option key={`${item.source_type}-${item.source_task_id}`} value={item.source_task_id}>
                  {item.source_task_name} · {item.record_count} 条
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>一级分类</span>
            <select
              value={filters.categoryId ?? ""}
              onChange={(event) => {
                const nextCategoryId = Number(event.target.value || 0) || null;
                setFilters((state) => ({
                  ...state,
                  categoryId: nextCategoryId,
                  subcategoryId: null,
                  keywordId: null,
                }));
              }}
            >
              <option value="">全部一级分类</option>
              {categories.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>二级分类</span>
            <select
              value={filters.subcategoryId ?? ""}
              onChange={(event) =>
                setFilters((state) => ({
                  ...state,
                  subcategoryId: Number(event.target.value || 0) || null,
                  keywordId: null,
                }))
              }
            >
              <option value="">全部二级分类</option>
              {(selectedCategory?.subcategories ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>黑话词条</span>
            <select
              value={filters.keywordId ?? ""}
              onChange={(event) =>
                setFilters((state) => ({
                  ...state,
                  keywordId: Number(event.target.value || 0) || null,
                }))
              }
            >
              <option value="">全部黑话词条</option>
              {keywordOptions.map((item) => (
                <option key={item.id} value={item.id}>
                  {formatKeywordOption(item)}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>最小置信度</span>
            <input
              type="number"
              min={0}
              max={100}
              placeholder="例如 80"
              value={filters.minConfidence}
              onChange={(event) =>
                setFilters((state) => ({
                  ...state,
                  minConfidence: event.target.value,
                }))
              }
            />
          </label>

          <label className="field hit-filter-search">
            <span>搜索标题 / 正文</span>
            <input
              placeholder="输入帖子标题、正文、作者等关键词"
              value={filters.search}
              onChange={(event) =>
                setFilters((state) => ({
                  ...state,
                  search: event.target.value,
                }))
              }
            />
          </label>
        </div>
        <div className="action-row top-space">
          <button className="primary-button" onClick={applyFilters}>
            应用筛选
          </button>
          <button className="ghost-button" onClick={resetFilters}>
            重置筛选
          </button>
          <span className="muted-text">当前共 {total} 条命中记录</span>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header compact">
          <div>
            <div className="eyebrow">Matched Stream</div>
            <h2>命中列表</h2>
          </div>
        </div>
        {loading ? (
          <div className="empty-state small">正在加载命中记录...</div>
        ) : records.length === 0 ? (
          <div className="empty-state small">当前筛选条件下没有命中记录。</div>
        ) : (
          <div className="hit-record-list">
            {records.map((item) => (
              <article key={item.id} className="result-card outcome-matched hit-record-card">
                <button className="hit-record-main" type="button" onClick={() => void openRecordDetail(item.id)}>
                  <div className="inline-between">
                    <strong>{item.title || "无标题"}</strong>
                    <span className="status-chip">最高置信度 {formatMatchConfidence(item.top_confidence)}</span>
                  </div>
                  <p>{item.content || "无正文"}</p>
                  <div className="chip-row">
                    <span className="status-chip">{formatSourceType(item.platform as JargonSourceType)}</span>
                    <span className="status-chip">任务 #{item.source_task_id}</span>
                    <span className="status-chip">{formatDateTime(item.created_at)}</span>
                    {item.source_label ? <span className="status-chip">{item.source_label}</span> : null}
                    {item.price_label ? <span className="status-chip">{item.price_label}</span> : null}
                    {item.author ? <span className="status-chip">{item.author}</span> : null}
                    {item.seller_name ? <span className="status-chip">{item.seller_name}</span> : null}
                  </div>
                  <div className="hit-match-list">
                    {item.matches.map((match) => (
                      <div key={`${item.id}-${match.keyword_id}-${match.task_id}`} className="hit-match-card">
                        <strong>{match.keyword}</strong>
                        <span>{match.category_name} / {match.subcategory_name}</span>
                        <span>{formatMatchConfidence(match.confidence)}</span>
                        <p>{match.reason || "无命中理由"}</p>
                      </div>
                    ))}
                  </div>
                </button>
                <div className="action-row">
                  <button className="text-link-button" type="button" onClick={() => void openRecordDetail(item.id)}>
                    查看详情
                  </button>
                  {item.link ? (
                    <button className="text-link-button" type="button" onClick={() => void api.openExternal(item.link)}>
                      打开原帖
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

      {selectedRecordId !== null ? (
        <div className="modal-backdrop" onClick={closeDetail}>
          <div className="modal-card wide hit-tracing-modal" onClick={(event) => event.stopPropagation()}>
            <div className="panel-header compact">
              <div>
                <div className="eyebrow">Trace Detail</div>
                <h2>{selectedRecord?.title || "命中详情"}</h2>
              </div>
              <div className="heading-actions">
                {selectedRecord?.link ? (
                  <button className="ghost-button" type="button" onClick={() => void api.openExternal(selectedRecord.link)}>
                    打开原帖
                  </button>
                ) : null}
                <button className="ghost-button" type="button" onClick={closeDetail}>
                  关闭
                </button>
              </div>
            </div>

            {detailLoading ? (
              <div className="empty-state small">正在加载命中详情...</div>
            ) : detailError ? (
              <div className="inline-error subtle">{detailError}</div>
            ) : selectedRecord !== null ? (
              <>
                <div className="summary-strip">
                  <span>{formatSourceType(selectedRecord.platform as JargonSourceType)}</span>
                  <span>任务 #{selectedRecord.source_task_id}</span>
                  <span>{selectedRecord.record_type}</span>
                  <span>序号 {selectedRecord.item_index}</span>
                  <span>{formatDateTime(selectedRecord.created_at)}</span>
                </div>

                {selectedRecord.image_url ? (
                  <div className="hit-detail-image">
                    <img src={selectedRecord.image_url} alt={selectedRecord.title || "命中记录图片"} />
                  </div>
                ) : null}

                <section className="detail-section">
                  <div className="panel-header compact">
                    <div>
                      <div className="eyebrow">Structured Detail</div>
                      <h2>结构化信息</h2>
                    </div>
                  </div>
                  <div className="hit-detail-grid">
                    <div>
                      <span>平台</span>
                      <strong>{formatSourceType(selectedRecord.platform as JargonSourceType)}</strong>
                    </div>
                    <div>
                      <span>采集任务</span>
                      <strong>#{selectedRecord.source_task_id}</strong>
                    </div>
                    <div>
                      <span>采集关键词</span>
                      <strong>{selectedRecord.source_label || "--"}</strong>
                    </div>
                    <div>
                      <span>作者 / 卖家</span>
                      <strong>{selectedRecord.author_name || selectedRecord.seller_name || selectedRecord.author || "--"}</strong>
                    </div>
                    <div>
                      <span>作者 ID</span>
                      <strong>{selectedRecord.author_id || "--"}</strong>
                    </div>
                    <div>
                      <span>地域 / IP</span>
                      <strong>{selectedRecord.location_text || selectedRecord.ip_location || selectedRecord.seller_region || "--"}</strong>
                    </div>
                    <div>
                      <span>发布时间</span>
                      <strong>{selectedRecord.published_text || selectedRecord.publish_time || "--"}</strong>
                    </div>
                    <div>
                      <span>价格</span>
                      <strong>{selectedRecord.price_label || "--"}</strong>
                    </div>
                    <div>
                      <span>互动数据</span>
                      <strong>
                        想要 {selectedRecord.want_count ?? 0} / 浏览 {selectedRecord.view_count ?? 0} / 点赞 {selectedRecord.likes ?? 0} /
                        收藏 {selectedRecord.collects ?? 0} / 评论 {selectedRecord.comment_count ?? 0}
                      </strong>
                    </div>
                    <div>
                      <span>话题</span>
                      <strong>{selectedRecord.topics?.length ? selectedRecord.topics.join(" / ") : "--"}</strong>
                    </div>
                    <div>
                      <span>入库时间</span>
                      <strong>{formatDateTime(selectedRecord.created_at)}</strong>
                    </div>
                    <div>
                      <span>原始链接</span>
                      <strong>{selectedRecord.link || "--"}</strong>
                    </div>
                  </div>
                </section>

                <section className="detail-section">
                  <div className="panel-header compact">
                    <div>
                      <div className="eyebrow">Match Reasons</div>
                      <h2>命中详情</h2>
                    </div>
                  </div>
                  <div className="hit-match-list detail">
                    {selectedRecord.matches.map((match) => (
                      <article key={`${selectedRecord.id}-${match.keyword_id}-${match.task_id}`} className="hit-match-card detail">
                        <div className="inline-between">
                          <strong>{match.keyword}</strong>
                          <span>{formatMatchConfidence(match.confidence)}</span>
                        </div>
                        <span>{match.category_name} / {match.subcategory_name}</span>
                        <p>{match.meaning}</p>
                        <p>命中理由：{match.reason || "无命中理由"}</p>
                        <p>研判时间：{formatDateTime(match.task_completed_at || match.task_created_at)}</p>
                      </article>
                    ))}
                  </div>
                </section>

                <section className="detail-section">
                  <div className="panel-header compact">
                    <div>
                      <div className="eyebrow">Content</div>
                      <h2>正文内容</h2>
                    </div>
                  </div>
                  <div className="detail-copy">
                    <p>{selectedRecord.content || "无正文"}</p>
                  </div>
                </section>

                <section className="detail-section">
                  <div className="panel-header compact">
                    <div>
                      <div className="eyebrow">Visible Texts</div>
                      <h2>可见文本</h2>
                    </div>
                  </div>
                  {selectedRecord.raw_visible_texts.length === 0 ? (
                    <div className="empty-inline">没有保存可见文本。</div>
                  ) : (
                    <div className="raw-text-list">
                      {selectedRecord.raw_visible_texts.map((item, index) => (
                        <div key={`${selectedRecord.id}-${index}`} className="raw-text-item">
                          {item}
                        </div>
                      ))}
                    </div>
                  )}
                </section>

                <section className="hit-json-grid">
                  <div className="detail-section">
                    <div className="panel-header compact">
                      <div>
                        <div className="eyebrow">Metrics</div>
                        <h2>采集指标</h2>
                      </div>
                    </div>
                    <pre className="json-viewer">{formatJson(selectedRecord.metrics)}</pre>
                  </div>

                  <div className="detail-section">
                    <div className="panel-header compact">
                      <div>
                        <div className="eyebrow">Extra</div>
                        <h2>原始扩展字段</h2>
                      </div>
                    </div>
                    <pre className="json-viewer">{formatJson(selectedRecord.extra)}</pre>
                  </div>
                </section>
              </>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
