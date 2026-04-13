import { useEffect, useMemo, useState } from "react";

import {
  ACTIVE_JARGON_TASK_STATUSES,
  api,
  formatDateTime,
  formatSourceType,
  formatStatus,
  JargonSourceDataset,
  JargonSourceType,
  JargonTask,
  JargonTaskResultItem,
  KeywordCategory,
} from "@/lib/api";
import { usePersistentState } from "@/lib/persistentState";

type TaskResultsState = {
  task: JargonTask;
  items: JargonTaskResultItem[];
} | null;

type JargonAnalysisDraft = {
  sourceType: JargonSourceType;
  sourceTaskId: number | null;
  categoryId: number | null;
  subcategoryId: number | null;
  keywordId: number | null;
};

const DEFAULT_JARGON_ANALYSIS_DRAFT: JargonAnalysisDraft = {
  sourceType: "xianyu",
  sourceTaskId: null,
  categoryId: null,
  subcategoryId: null,
  keywordId: null,
};

function normalizeJargonAnalysisDraft(
  currentDraft: JargonAnalysisDraft,
  sources: JargonSourceDataset[],
  categories: KeywordCategory[],
): JargonAnalysisDraft {
  const filteredSources = sources.filter((item) => item.source_type === currentDraft.sourceType);
  const selectedCategory = categories.find((item) => item.id === currentDraft.categoryId) ?? categories[0] ?? null;
  const selectedSubcategory =
    selectedCategory?.subcategories.find((item) => item.id === currentDraft.subcategoryId) ??
    selectedCategory?.subcategories[0] ??
    null;
  const keywordOptions = selectedSubcategory?.keywords ?? selectedCategory?.keywords ?? [];

  return {
    sourceType: currentDraft.sourceType,
    sourceTaskId:
      currentDraft.sourceTaskId !== null &&
      filteredSources.some((item) => item.source_task_id === currentDraft.sourceTaskId)
        ? currentDraft.sourceTaskId
        : filteredSources[0]?.source_task_id ?? null,
    categoryId: selectedCategory?.id ?? null,
    subcategoryId: selectedSubcategory?.id ?? null,
    keywordId:
      currentDraft.keywordId !== null && keywordOptions.some((item) => item.id === currentDraft.keywordId)
        ? currentDraft.keywordId
        : keywordOptions[0]?.id ?? null,
  };
}

export default function JargonAnalysisPage(): React.JSX.Element {
  const [sources, setSources] = useState<JargonSourceDataset[]>([]);
  const [categories, setCategories] = useState<KeywordCategory[]>([]);
  const [tasks, setTasks] = useState<JargonTask[]>([]);
  const [draft, setDraft] = usePersistentState<JargonAnalysisDraft>(
    "pages/jargon-analysis/filters",
    DEFAULT_JARGON_ANALYSIS_DRAFT,
  );
  const [taskResults, setTaskResults] = useState<TaskResultsState>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const { sourceType: selectedSourceType, sourceTaskId: selectedSourceTaskId } = draft;
  const { categoryId: selectedCategoryId, subcategoryId: selectedSubcategoryId, keywordId: selectedKeywordId } = draft;

  const filteredSources = useMemo(
    () => sources.filter((item) => item.source_type === selectedSourceType),
    [sources, selectedSourceType],
  );
  const selectedCategory = useMemo(
    () => categories.find((item) => item.id === selectedCategoryId) ?? null,
    [categories, selectedCategoryId],
  );
  const selectedSubcategory = useMemo(
    () => selectedCategory?.subcategories.find((item) => item.id === selectedSubcategoryId) ?? null,
    [selectedCategory, selectedSubcategoryId],
  );
  const isPolling = useMemo(() => tasks.some((item) => ACTIVE_JARGON_TASK_STATUSES.has(item.status)), [tasks]);

  useEffect(() => {
    void loadPageData();
  }, []);

  useEffect(() => {
    if (!isPolling) {
      return;
    }
    const timer = window.setInterval(() => {
      void loadTasks();
    }, 4000);
    return () => window.clearInterval(timer);
  }, [isPolling]);

  async function loadPageData(): Promise<void> {
    try {
      const [sourceItems, categoryItems, taskData] = await Promise.all([
        api.listJargonSources(),
        api.listKeywordCategories(),
        api.listJargonTasks(),
      ]);
      setSources(sourceItems);
      setCategories(categoryItems);
      setTasks(taskData.items);
      setError("");
      setDraft((currentDraft) => normalizeJargonAnalysisDraft(currentDraft, sourceItems, categoryItems));
    } catch (caughtError) {
      setError((caughtError as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function loadTasks(): Promise<void> {
    try {
      const data = await api.listJargonTasks();
      setTasks(data.items);
      setError("");
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleCreateTask(): Promise<void> {
    if (selectedSourceTaskId === null || selectedKeywordId === null) {
      setError("请先选择数据源和黑话词条");
      return;
    }
    try {
      const task = await api.createJargonTask({
        source_type: selectedSourceType,
        source_task_id: selectedSourceTaskId,
        keyword_id: selectedKeywordId,
      });
      setSuccessMessage(`已创建研判任务 #${task.id}`);
      await loadTasks();
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function openTaskResults(task: JargonTask): Promise<void> {
    try {
      const data = await api.getJargonTaskResults(task.id);
      setTaskResults(data);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  return (
    <div className="page-stack">
      <section className="section-heading">
        <div>
          <div className="eyebrow">Jargon Analysis</div>
          <h1>黑话研判</h1>
        </div>
        <button className="ghost-button" onClick={() => void loadPageData()}>
          刷新
        </button>
      </section>

      {error ? <div className="inline-error">{error}</div> : null}
      {successMessage ? <div className="inline-success">{successMessage}</div> : null}

      <section className="detail-grid">
        <div className="panel">
          <div className="panel-header compact">
            <div>
              <div className="eyebrow">Workflow</div>
              <h2>创建研判任务</h2>
            </div>
          </div>

          {loading ? (
            <div className="empty-state small">正在加载数据源和词典...</div>
          ) : (
            <div className="field-grid field-grid-two">
              <label className="field">
                <span>平台</span>
                <select
                  value={selectedSourceType}
                  onChange={(event) => {
                    const nextType = event.target.value as JargonSourceType;
                    const nextSource = sources.find((item) => item.source_type === nextType) ?? null;
                    setDraft((currentDraft) => ({
                      ...currentDraft,
                      sourceType: nextType,
                      sourceTaskId: nextSource?.source_task_id ?? null,
                    }));
                  }}
                >
                  <option value="xianyu">闲鱼</option>
                  <option value="xhs">小红书</option>
                </select>
              </label>

              <label className="field">
                <span>数据源任务</span>
                <select
                  value={selectedSourceTaskId ?? ""}
                  onChange={(event) =>
                    setDraft((currentDraft) => ({
                      ...currentDraft,
                      sourceTaskId: Number(event.target.value || 0) || null,
                    }))
                  }
                >
                  {filteredSources.length === 0 ? <option value="">暂无可分析数据</option> : null}
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
                  value={selectedCategoryId ?? ""}
                  onChange={(event) => {
                    const nextCategoryId = Number(event.target.value || 0) || null;
                    const nextCategory = categories.find((item) => item.id === nextCategoryId) ?? null;
                    const nextSubcategory = nextCategory?.subcategories[0] ?? null;
                    setDraft((currentDraft) => ({
                      ...currentDraft,
                      categoryId: nextCategoryId,
                      subcategoryId: nextSubcategory?.id ?? null,
                      keywordId: nextSubcategory?.keywords[0]?.id ?? nextCategory?.keywords[0]?.id ?? null,
                    }));
                  }}
                >
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
                  value={selectedSubcategoryId ?? ""}
                  onChange={(event) => {
                    const nextSubcategoryId = Number(event.target.value || 0) || null;
                    const nextSubcategory =
                      selectedCategory?.subcategories.find((item) => item.id === nextSubcategoryId) ?? null;
                    setDraft((currentDraft) => ({
                      ...currentDraft,
                      subcategoryId: nextSubcategoryId,
                      keywordId: nextSubcategory?.keywords[0]?.id ?? null,
                    }));
                  }}
                >
                  {selectedCategory?.subcategories.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field">
                <span>黑话词条</span>
                <select
                  value={selectedKeywordId ?? ""}
                  onChange={(event) =>
                    setDraft((currentDraft) => ({
                      ...currentDraft,
                      keywordId: Number(event.target.value || 0) || null,
                    }))
                  }
                >
                  {(selectedSubcategory?.keywords ?? selectedCategory?.keywords ?? []).map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.keyword} / {item.meaning}
                    </option>
                  ))}
                </select>
              </label>

              <div className="panel-note">
                <div className="eyebrow">Current Scope</div>
                <p>闲鱼只分析 `listing`，小红书只分析 `note`。评论暂不纳入本轮迁移范围。</p>
              </div>
            </div>
          )}

          <div className="top-space">
            <button className="primary-button" onClick={() => void handleCreateTask()}>
              创建研判任务
            </button>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header compact">
            <div>
              <div className="eyebrow">Recent Tasks</div>
              <h2>任务概览</h2>
            </div>
          </div>

          <div className="stack-list">
            {tasks.slice(0, 6).map((item) => {
              const progress = item.total_records > 0 ? Math.round((item.processed_records / item.total_records) * 100) : 0;
              return (
                <article key={item.id} className="stack-card plain">
                  <div className="inline-between">
                    <strong>#{item.id} {item.keyword_name}</strong>
                    <span>{formatStatus(item.status)}</span>
                  </div>
                  <span>
                    {formatSourceType(item.source_type)} / {item.source_task_name}
                  </span>
                  <div className="progress-track">
                    <div className="progress-bar" style={{ width: `${progress}%` }} />
                  </div>
                  <span>
                    {item.processed_records}/{item.total_records}，命中 {item.matched_records}
                  </span>
                </article>
              );
            })}
            {tasks.length === 0 ? <div className="empty-inline">还没有黑话研判任务。</div> : null}
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header compact">
          <div>
            <div className="eyebrow">Task Ledger</div>
            <h2>任务列表</h2>
          </div>
        </div>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>平台</th>
                <th>数据源</th>
                <th>黑话</th>
                <th>状态</th>
                <th>进度</th>
                <th>命中</th>
                <th>时间</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {tasks.length === 0 ? (
                <tr>
                  <td colSpan={9}>
                    <div className="empty-inline">还没有黑话研判任务。</div>
                  </td>
                </tr>
              ) : (
                tasks.map((item) => (
                  <tr key={item.id}>
                    <td>#{item.id}</td>
                    <td>{formatSourceType(item.source_type)}</td>
                    <td>{item.source_task_name}</td>
                    <td>{item.keyword_name}</td>
                    <td>{formatStatus(item.status)}</td>
                    <td>
                      {item.processed_records}/{item.total_records}
                    </td>
                    <td>{item.matched_records}</td>
                    <td>{formatDateTime(item.created_at)}</td>
                    <td>
                      <button className="text-link-button" onClick={() => void openTaskResults(item)}>
                        查看结果
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {taskResults !== null ? (
        <div className="modal-backdrop" onClick={() => setTaskResults(null)}>
          <div className="modal-card wide" onClick={(event) => event.stopPropagation()}>
            <div className="panel-header compact">
              <div>
                <div className="eyebrow">Task Result</div>
                <h2>
                  任务 #{taskResults.task.id} / {taskResults.task.keyword_name}
                </h2>
              </div>
              <button className="ghost-button" onClick={() => setTaskResults(null)}>
                关闭
              </button>
            </div>
            <div className="summary-strip">
              <span>{formatSourceType(taskResults.task.source_type)}</span>
              <span>{taskResults.task.source_task_name}</span>
              <span>命中 {taskResults.task.matched_records}</span>
              <span>总计 {taskResults.task.total_records}</span>
            </div>
            <div className="stack-list max-list">
              {taskResults.items.map((item) => (
                <article key={item.id} className={`result-card ${item.is_match ? "matched" : ""}`}>
                  <div className="inline-between">
                    <strong>{item.record.title || "无标题"}</strong>
                    <span>{item.is_match ? "命中" : "未命中"}</span>
                  </div>
                  <p>{item.record.content || "无正文"}</p>
                  <div className="chip-row">
                    <span className="status-chip">置信度 {Math.round(item.confidence)}</span>
                    <span className="status-chip">{item.reason || "无理由说明"}</span>
                  </div>
                </article>
              ))}
              {taskResults.items.length === 0 ? <div className="empty-inline">当前任务还没有返回结果。</div> : null}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
