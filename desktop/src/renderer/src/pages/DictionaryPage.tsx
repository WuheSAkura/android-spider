import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  api,
  formatDateTime,
  Keyword,
  KeywordCategory,
  KeywordSubcategory,
} from "@/lib/api";

const EMPTY_CATEGORY_FORM = { name: "", description: "", sort_order: 0 };
const EMPTY_SUBCATEGORY_FORM = { name: "", description: "", sort_order: 0 };
const EMPTY_KEYWORD_FORM = { keyword: "", meaning: "", sort_order: 0, subcategory_id: 0 };

type FormModalProps = {
  children: React.ReactNode;
  error: string;
  onClose: () => void;
  open: boolean;
  title: string;
};

function FormModal({ children, error, onClose, open, title }: FormModalProps): React.JSX.Element | null {
  if (!open) {
    return null;
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card dictionary-modal-card" onClick={(event) => event.stopPropagation()}>
        <div className="panel-header compact">
          <div>
            <div className="eyebrow">Dictionary Form</div>
            <h2>{title}</h2>
          </div>
          <button className="ghost-button" type="button" onClick={onClose}>
            关闭
          </button>
        </div>
        {error ? <div className="inline-error subtle">{error}</div> : null}
        {children}
      </div>
    </div>
  );
}

export default function DictionaryPage(): React.JSX.Element {
  const [categories, setCategories] = useState<KeywordCategory[]>([]);
  const [selectedCategoryId, setSelectedCategoryId] = useState<number | null>(null);
  const [selectedSubcategoryId, setSelectedSubcategoryId] = useState<number | null>(null);
  const [categoryForm, setCategoryForm] = useState(EMPTY_CATEGORY_FORM);
  const [subcategoryForm, setSubcategoryForm] = useState(EMPTY_SUBCATEGORY_FORM);
  const [keywordForm, setKeywordForm] = useState(EMPTY_KEYWORD_FORM);
  const [editingCategoryId, setEditingCategoryId] = useState<number | null>(null);
  const [editingSubcategoryId, setEditingSubcategoryId] = useState<number | null>(null);
  const [editingKeywordId, setEditingKeywordId] = useState<number | null>(null);
  const [categoryModalOpen, setCategoryModalOpen] = useState(false);
  const [subcategoryModalOpen, setSubcategoryModalOpen] = useState(false);
  const [keywordModalOpen, setKeywordModalOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const selectedCategory = useMemo(
    () => categories.find((item) => item.id === selectedCategoryId) ?? null,
    [categories, selectedCategoryId],
  );
  const selectedSubcategory = useMemo(
    () => selectedCategory?.subcategories.find((item) => item.id === selectedSubcategoryId) ?? null,
    [selectedCategory, selectedSubcategoryId],
  );
  const displayedKeywords = useMemo(() => {
    if (selectedCategory === null) {
      return [];
    }

    const subcategoryMeta = new Map(selectedCategory.subcategories.map((item) => [item.id, item]));

    return selectedCategory.subcategories
      .flatMap((subcategory) => subcategory.keywords)
      .filter((item) => selectedSubcategoryId === null || item.subcategory_id === selectedSubcategoryId)
      .sort((left, right) => {
        const leftSubcategory = subcategoryMeta.get(left.subcategory_id);
        const rightSubcategory = subcategoryMeta.get(right.subcategory_id);
        const subcategorySortOrder = (leftSubcategory?.sort_order ?? 0) - (rightSubcategory?.sort_order ?? 0);
        if (subcategorySortOrder !== 0) {
          return subcategorySortOrder;
        }

        const subcategoryIdOrder = (leftSubcategory?.id ?? 0) - (rightSubcategory?.id ?? 0);
        if (subcategoryIdOrder !== 0) {
          return subcategoryIdOrder;
        }

        const keywordSortOrder = left.sort_order - right.sort_order;
        if (keywordSortOrder !== 0) {
          return keywordSortOrder;
        }

        return left.id - right.id;
      });
  }, [selectedCategory, selectedSubcategoryId]);

  useEffect(() => {
    void loadCategories();
  }, []);

  function clearFeedback(): void {
    setError("");
    setSuccessMessage("");
  }

  async function loadCategories(nextCategoryId?: number | null, nextSubcategoryId?: number | null): Promise<void> {
    setLoading(true);
    try {
      const data = await api.listKeywordCategories();
      setCategories(data);
      setError("");

      const fallbackCategoryId = data[0]?.id ?? null;
      const resolvedCategoryId =
        nextCategoryId !== undefined
          ? data.some((item) => item.id === nextCategoryId)
            ? nextCategoryId
            : fallbackCategoryId
          : data.some((item) => item.id === selectedCategoryId)
            ? selectedCategoryId
            : fallbackCategoryId;
      setSelectedCategoryId(resolvedCategoryId);

      const currentCategory = data.find((item) => item.id === resolvedCategoryId) ?? null;
      if (currentCategory === null) {
        setSelectedSubcategoryId(null);
        return;
      }

      if (nextSubcategoryId !== undefined) {
        const resolvedSubcategoryId =
          nextSubcategoryId === null
            ? null
            : currentCategory.subcategories.some((item) => item.id === nextSubcategoryId)
              ? nextSubcategoryId
              : null;
        setSelectedSubcategoryId(resolvedSubcategoryId);
        return;
      }

      const shouldKeepCurrentSubcategory =
        selectedCategoryId === resolvedCategoryId
        && selectedSubcategoryId !== null
        && currentCategory.subcategories.some((item) => item.id === selectedSubcategoryId);
      setSelectedSubcategoryId(shouldKeepCurrentSubcategory ? selectedSubcategoryId : null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
      setSuccessMessage("");
    } finally {
      setLoading(false);
    }
  }

  function resetCategoryForm(): void {
    setEditingCategoryId(null);
    setCategoryForm(EMPTY_CATEGORY_FORM);
  }

  function resetSubcategoryForm(): void {
    setEditingSubcategoryId(null);
    setSubcategoryForm(EMPTY_SUBCATEGORY_FORM);
  }

  function resetKeywordForm(): void {
    setEditingKeywordId(null);
    setKeywordForm(EMPTY_KEYWORD_FORM);
  }

  function closeCategoryModal(): void {
    setCategoryModalOpen(false);
    resetCategoryForm();
  }

  function closeSubcategoryModal(): void {
    setSubcategoryModalOpen(false);
    resetSubcategoryForm();
  }

  function closeKeywordModal(): void {
    setKeywordModalOpen(false);
    resetKeywordForm();
  }

  function openCreateCategoryModal(): void {
    clearFeedback();
    resetCategoryForm();
    setCategoryModalOpen(true);
  }

  function openEditCategoryModal(item: KeywordCategory): void {
    clearFeedback();
    setEditingCategoryId(item.id);
    setCategoryForm({
      name: item.name,
      description: item.description,
      sort_order: item.sort_order,
    });
    setCategoryModalOpen(true);
  }

  function openCreateSubcategoryModal(): void {
    if (selectedCategory === null) {
      return;
    }
    clearFeedback();
    resetSubcategoryForm();
    setSubcategoryForm((state) => ({
      ...state,
      sort_order: selectedCategory.subcategories.length,
    }));
    setSubcategoryModalOpen(true);
  }

  function openEditSubcategoryModal(item: KeywordSubcategory): void {
    clearFeedback();
    setEditingSubcategoryId(item.id);
    setSubcategoryForm({
      name: item.name,
      description: item.description,
      sort_order: item.sort_order,
    });
    setSubcategoryModalOpen(true);
  }

  function openCreateKeywordModal(): void {
    if (selectedCategory === null) {
      return;
    }

    const targetSubcategory = selectedSubcategory ?? selectedCategory.subcategories[0] ?? null;
    if (targetSubcategory === null) {
      setError("请先为当前一级分类创建至少一个二级分类。");
      setSuccessMessage("");
      return;
    }

    clearFeedback();
    resetKeywordForm();
    setKeywordForm({
      ...EMPTY_KEYWORD_FORM,
      sort_order: targetSubcategory.keywords.length,
      subcategory_id: targetSubcategory.id,
    });
    setKeywordModalOpen(true);
  }

  function openEditKeywordModal(item: Keyword): void {
    clearFeedback();
    setEditingKeywordId(item.id);
    setKeywordForm({
      keyword: item.keyword,
      meaning: item.meaning,
      sort_order: item.sort_order,
      subcategory_id: item.subcategory_id,
    });
    setKeywordModalOpen(true);
  }

  async function handleCategorySubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    clearFeedback();

    try {
      if (editingCategoryId !== null) {
        await api.updateKeywordCategory(editingCategoryId, categoryForm);
        setSuccessMessage("一级分类已更新");
        await loadCategories(editingCategoryId, selectedSubcategoryId);
      } else {
        const item = await api.createKeywordCategory(categoryForm);
        setSuccessMessage("一级分类已创建");
        await loadCategories(item.id, null);
      }
      closeCategoryModal();
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleSubcategorySubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (selectedCategory === null) {
      return;
    }

    clearFeedback();

    try {
      if (editingSubcategoryId !== null) {
        await api.updateKeywordSubcategory(editingSubcategoryId, subcategoryForm);
        setSuccessMessage("二级分类已更新");
        await loadCategories(selectedCategory.id, editingSubcategoryId);
      } else {
        const item = await api.createKeywordSubcategory(selectedCategory.id, subcategoryForm);
        setSuccessMessage("二级分类已创建");
        await loadCategories(selectedCategory.id, item.id);
      }
      closeSubcategoryModal();
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleKeywordSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (keywordForm.subcategory_id === 0) {
      setError("请先选择黑话所属的二级分类。");
      setSuccessMessage("");
      return;
    }

    clearFeedback();

    try {
      const targetSubcategoryId = keywordForm.subcategory_id;
      const targetCategoryId =
        categories.find((item) => item.subcategories.some((subItem) => subItem.id === targetSubcategoryId))?.id
        ?? selectedCategory?.id
        ?? null;

      if (editingKeywordId !== null) {
        await api.updateKeyword(editingKeywordId, keywordForm);
        setSuccessMessage("黑话词条已更新");
      } else {
        await api.createKeyword(targetSubcategoryId, {
          keyword: keywordForm.keyword,
          meaning: keywordForm.meaning,
          sort_order: keywordForm.sort_order,
        });
        setSuccessMessage("黑话词条已创建");
      }

      closeKeywordModal();
      await loadCategories(targetCategoryId, targetSubcategoryId);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleDeleteCategory(categoryId: number): Promise<void> {
    if (!window.confirm("确定删除这个一级分类及其下全部黑话吗？")) {
      return;
    }

    clearFeedback();

    try {
      await api.deleteKeywordCategory(categoryId);
      setSuccessMessage("一级分类已删除");
      resetCategoryForm();
      resetSubcategoryForm();
      resetKeywordForm();
      await loadCategories();
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleDeleteSubcategory(subcategoryId: number): Promise<void> {
    if (!window.confirm("确定删除这个二级分类及其下全部黑话吗？")) {
      return;
    }

    clearFeedback();

    try {
      await api.deleteKeywordSubcategory(subcategoryId);
      setSuccessMessage("二级分类已删除");
      resetSubcategoryForm();
      resetKeywordForm();
      await loadCategories(selectedCategory?.id ?? null, null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleDeleteKeyword(keywordId: number): Promise<void> {
    if (!window.confirm("确定删除这个黑话词条吗？")) {
      return;
    }

    clearFeedback();

    try {
      await api.deleteKeyword(keywordId);
      setSuccessMessage("黑话词条已删除");
      resetKeywordForm();
      await loadCategories(selectedCategory?.id ?? null, selectedSubcategoryId);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  return (
    <div className="page-stack dictionary-page">
      <section className="section-heading">
        <div>
          <div className="eyebrow">Jargon Dictionary</div>
          <h1>黑话字典</h1>
        </div>
        <div className="heading-actions dictionary-page-actions">
          <button className="ghost-button" type="button" onClick={() => void loadCategories(selectedCategoryId, selectedSubcategoryId)}>
            刷新
          </button>
          <button className="ghost-button" type="button" onClick={openCreateCategoryModal}>
            新增一级分类
          </button>
          <button
            className="ghost-button"
            type="button"
            disabled={selectedCategory === null}
            onClick={openCreateSubcategoryModal}
          >
            新增二级分类
          </button>
          <button
            className="primary-button"
            type="button"
            disabled={selectedCategory === null || selectedCategory.subcategories.length === 0}
            onClick={openCreateKeywordModal}
          >
            新增黑话
          </button>
        </div>
      </section>

      {error ? <div className="inline-error">{error}</div> : null}
      {successMessage ? <div className="inline-success">{successMessage}</div> : null}

      <section className="dictionary-layout">
        <aside className="panel dictionary-sidebar">
          <div className="dictionary-filter-section">
            <div className="panel-header compact">
              <div>
                <div className="eyebrow">Level 1</div>
                <h2>一级分类</h2>
              </div>
            </div>
            {loading ? (
              <div className="empty-inline">正在加载分类...</div>
            ) : categories.length === 0 ? (
              <div className="empty-inline">还没有一级分类。</div>
            ) : (
              <div className="dictionary-category-list">
                {categories.map((item) => (
                  <button
                    key={item.id}
                    className={`stack-card ${item.id === selectedCategoryId ? "active" : ""}`}
                    type="button"
                    onClick={() => {
                      setSelectedCategoryId(item.id);
                      setSelectedSubcategoryId(null);
                    }}
                  >
                    <strong>{item.name}</strong>
                    <span>{item.keywords.length} 个黑话</span>
                  </button>
                ))}
              </div>
            )}
            {selectedCategory !== null ? (
              <div className="action-row">
                <button className="ghost-button" type="button" onClick={() => openEditCategoryModal(selectedCategory)}>
                  编辑一级分类
                </button>
                <button className="danger-button" type="button" onClick={() => void handleDeleteCategory(selectedCategory.id)}>
                  删除一级分类
                </button>
              </div>
            ) : null}
          </div>

          <div className="dictionary-divider" />

          <div className="dictionary-filter-section">
            <div className="panel-header compact">
              <div>
                <div className="eyebrow">Level 2</div>
                <h2>二级分类</h2>
              </div>
            </div>
            {selectedCategory === null ? (
              <div className="empty-inline">先选择一级分类。</div>
            ) : (
              <>
                <div className="dictionary-chip-list">
                  <button
                    className={`dictionary-filter-chip ${selectedSubcategoryId === null ? "active" : ""}`}
                    type="button"
                    onClick={() => setSelectedSubcategoryId(null)}
                  >
                    全部
                  </button>
                  {selectedCategory.subcategories.map((item) => (
                    <button
                      key={item.id}
                      className={`dictionary-filter-chip ${item.id === selectedSubcategoryId ? "active" : ""}`}
                      type="button"
                      onClick={() => setSelectedSubcategoryId(item.id)}
                    >
                      {item.name}
                      <span>{item.keywords.length}</span>
                    </button>
                  ))}
                </div>
                {selectedCategory.subcategories.length === 0 ? (
                  <div className="empty-inline">当前一级分类下还没有二级分类。</div>
                ) : null}
              </>
            )}
            {selectedSubcategory !== null ? (
              <div className="action-row">
                <button className="ghost-button" type="button" onClick={() => openEditSubcategoryModal(selectedSubcategory)}>
                  编辑二级分类
                </button>
                <button
                  className="danger-button"
                  type="button"
                  onClick={() => void handleDeleteSubcategory(selectedSubcategory.id)}
                >
                  删除二级分类
                </button>
              </div>
            ) : null}
          </div>
        </aside>

        <section className="panel dictionary-content">
          <div className="dictionary-content-header">
            <div>
              <div className="eyebrow">Keyword Ledger</div>
              <h2>{selectedCategory?.name ?? "请选择一级分类"}</h2>
              <p>
                {selectedCategory === null
                  ? "左侧先选择一级分类，再按需要切换二级分类筛选。"
                  : selectedSubcategory === null
                    ? `当前查看 ${selectedCategory.name} 下全部二级分类的黑话词条。`
                    : `当前查看 ${selectedSubcategory.name} 分类下的黑话词条。`}
              </p>
            </div>
          </div>

          {selectedCategory !== null ? (
            <div className="summary-strip dictionary-summary-strip">
              <span>{selectedCategory.keywords.length} 个黑话词条</span>
              <span>{selectedCategory.subcategories.length} 个二级分类</span>
              <span>{selectedSubcategory?.name ?? "全部二级分类"}</span>
            </div>
          ) : null}

          {loading ? (
            <div className="empty-state small">正在加载黑话词条...</div>
          ) : selectedCategory === null ? (
            <div className="empty-state">暂无一级分类，请先创建分类。</div>
          ) : displayedKeywords.length === 0 ? (
            <div className="empty-state">当前筛选下没有黑话词条。</div>
          ) : (
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>黑话</th>
                    <th>含义</th>
                    <th>二级分类</th>
                    <th>排序</th>
                    <th>更新时间</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {displayedKeywords.map((item) => (
                    <tr key={item.id}>
                      <td>{item.keyword}</td>
                      <td>{item.meaning}</td>
                      <td>{item.subcategory_name}</td>
                      <td>{item.sort_order}</td>
                      <td>{formatDateTime(item.updated_at)}</td>
                      <td>
                        <div className="action-row compact-end">
                          <button className="text-link-button" type="button" onClick={() => openEditKeywordModal(item)}>
                            编辑
                          </button>
                          <button
                            className="text-link-button danger-text"
                            type="button"
                            onClick={() => void handleDeleteKeyword(item.id)}
                          >
                            删除
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </section>

      <FormModal
        error={error}
        onClose={closeCategoryModal}
        open={categoryModalOpen}
        title={editingCategoryId !== null ? "编辑一级分类" : "新增一级分类"}
      >
        <form className="dictionary-form" onSubmit={(event) => void handleCategorySubmit(event)}>
          <label className="field">
            <span>分类名称</span>
            <input
              required
              placeholder="输入一级分类名称"
              value={categoryForm.name}
              onChange={(event) => setCategoryForm((state) => ({ ...state, name: event.target.value }))}
            />
          </label>
          <label className="field">
            <span>分类说明</span>
            <textarea
              placeholder="补充这个一级分类的用途"
              rows={4}
              value={categoryForm.description}
              onChange={(event) => setCategoryForm((state) => ({ ...state, description: event.target.value }))}
            />
          </label>
          <label className="field">
            <span>排序</span>
            <input
              type="number"
              value={categoryForm.sort_order}
              onChange={(event) =>
                setCategoryForm((state) => ({ ...state, sort_order: Number(event.target.value || 0) }))
              }
            />
          </label>
          <div className="dictionary-form-actions">
            <button className="ghost-button" type="button" onClick={closeCategoryModal}>
              取消
            </button>
            <button className="primary-button" type="submit">
              {editingCategoryId !== null ? "保存一级分类" : "创建一级分类"}
            </button>
          </div>
        </form>
      </FormModal>

      <FormModal
        error={error}
        onClose={closeSubcategoryModal}
        open={subcategoryModalOpen}
        title={editingSubcategoryId !== null ? "编辑二级分类" : "新增二级分类"}
      >
        <form className="dictionary-form" onSubmit={(event) => void handleSubcategorySubmit(event)}>
          <label className="field">
            <span>二级分类名称</span>
            <input
              required
              placeholder="输入二级分类名称"
              value={subcategoryForm.name}
              onChange={(event) => setSubcategoryForm((state) => ({ ...state, name: event.target.value }))}
            />
          </label>
          <label className="field">
            <span>分类说明</span>
            <textarea
              placeholder="补充这个二级分类的用途"
              rows={4}
              value={subcategoryForm.description}
              onChange={(event) => setSubcategoryForm((state) => ({ ...state, description: event.target.value }))}
            />
          </label>
          <label className="field">
            <span>排序</span>
            <input
              type="number"
              value={subcategoryForm.sort_order}
              onChange={(event) =>
                setSubcategoryForm((state) => ({ ...state, sort_order: Number(event.target.value || 0) }))
              }
            />
          </label>
          <div className="dictionary-form-actions">
            <button className="ghost-button" type="button" onClick={closeSubcategoryModal}>
              取消
            </button>
            <button className="primary-button" type="submit">
              {editingSubcategoryId !== null ? "保存二级分类" : "创建二级分类"}
            </button>
          </div>
        </form>
      </FormModal>

      <FormModal
        error={error}
        onClose={closeKeywordModal}
        open={keywordModalOpen}
        title={editingKeywordId !== null ? "编辑黑话词条" : "新增黑话词条"}
      >
        <form className="dictionary-form" onSubmit={(event) => void handleKeywordSubmit(event)}>
          <label className="field">
            <span>所属二级分类</span>
            <select
              value={keywordForm.subcategory_id || ""}
              onChange={(event) =>
                setKeywordForm((state) => ({ ...state, subcategory_id: Number(event.target.value || 0) }))
              }
            >
              {(selectedCategory?.subcategories ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>黑话名称</span>
            <input
              required
              placeholder="输入黑话名称"
              value={keywordForm.keyword}
              onChange={(event) => setKeywordForm((state) => ({ ...state, keyword: event.target.value }))}
            />
          </label>
          <label className="field">
            <span>黑话含义</span>
            <textarea
              required
              placeholder="输入黑话含义"
              rows={4}
              value={keywordForm.meaning}
              onChange={(event) => setKeywordForm((state) => ({ ...state, meaning: event.target.value }))}
            />
          </label>
          <label className="field">
            <span>排序</span>
            <input
              type="number"
              value={keywordForm.sort_order}
              onChange={(event) =>
                setKeywordForm((state) => ({ ...state, sort_order: Number(event.target.value || 0) }))
              }
            />
          </label>
          <div className="dictionary-form-actions">
            <button className="ghost-button" type="button" onClick={closeKeywordModal}>
              取消
            </button>
            <button className="primary-button" type="submit">
              {editingKeywordId !== null ? "保存黑话词条" : "创建黑话词条"}
            </button>
          </div>
        </form>
      </FormModal>
    </div>
  );
}
