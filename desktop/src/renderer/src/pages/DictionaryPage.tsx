import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  api,
  Keyword,
  KeywordCategory,
  KeywordSubcategory,
} from "@/lib/api";

const EMPTY_CATEGORY_FORM = { name: "", description: "", sort_order: 0 };
const EMPTY_SUBCATEGORY_FORM = { name: "", description: "", sort_order: 0 };
const EMPTY_KEYWORD_FORM = { keyword: "", meaning: "", sort_order: 0, subcategory_id: 0 };

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

  useEffect(() => {
    void loadCategories();
  }, []);

  useEffect(() => {
    if (editingKeywordId !== null) {
      return;
    }
    setKeywordForm((state) => ({
      ...state,
      subcategory_id: selectedSubcategory?.id ?? selectedCategory?.subcategories[0]?.id ?? 0,
    }));
  }, [editingKeywordId, selectedCategory, selectedSubcategory]);

  async function loadCategories(nextCategoryId?: number | null, nextSubcategoryId?: number | null): Promise<void> {
    try {
      const data = await api.listKeywordCategories();
      setCategories(data);
      setError("");

      const fallbackCategoryId = data[0]?.id ?? null;
      const categoryId =
        data.find((item) => item.id === nextCategoryId) !== undefined
          ? nextCategoryId ?? fallbackCategoryId
          : data.find((item) => item.id === selectedCategoryId)?.id ?? fallbackCategoryId;
      setSelectedCategoryId(categoryId);

      const currentCategory = data.find((item) => item.id === categoryId) ?? null;
      const fallbackSubcategoryId = currentCategory?.subcategories[0]?.id ?? null;
      const subcategoryId =
        currentCategory?.subcategories.find((item) => item.id === nextSubcategoryId) !== undefined
          ? nextSubcategoryId ?? fallbackSubcategoryId
          : currentCategory?.subcategories.find((item) => item.id === selectedSubcategoryId)?.id ?? fallbackSubcategoryId;
      setSelectedSubcategoryId(subcategoryId);
    } catch (caughtError) {
      setError((caughtError as Error).message);
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
    setKeywordForm({
      ...EMPTY_KEYWORD_FORM,
      subcategory_id: selectedSubcategory?.id ?? selectedCategory?.subcategories[0]?.id ?? 0,
    });
  }

  async function handleCategorySubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    try {
      if (editingCategoryId !== null) {
        await api.updateKeywordCategory(editingCategoryId, categoryForm);
        setSuccessMessage("一级分类已更新");
        await loadCategories(editingCategoryId, selectedSubcategoryId);
      } else {
        const item = await api.createKeywordCategory(categoryForm);
        setSuccessMessage("一级分类已创建");
        await loadCategories(item.id, item.subcategories[0]?.id ?? null);
      }
      resetCategoryForm();
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleSubcategorySubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (selectedCategory === null) {
      return;
    }
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
      resetSubcategoryForm();
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleKeywordSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const targetSubcategoryId = keywordForm.subcategory_id || selectedSubcategory?.id;
    if (selectedCategory === null || targetSubcategoryId === undefined) {
      return;
    }
    try {
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
      resetKeywordForm();
      await loadCategories(selectedCategory.id, targetSubcategoryId);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleDeleteCategory(categoryId: number): Promise<void> {
    if (!window.confirm("确定删除这个一级分类及其下全部黑话吗？")) {
      return;
    }
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
    try {
      await api.deleteKeywordSubcategory(subcategoryId);
      setSuccessMessage("二级分类已删除");
      resetSubcategoryForm();
      resetKeywordForm();
      await loadCategories(selectedCategory?.id ?? null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  async function handleDeleteKeyword(keywordId: number): Promise<void> {
    if (!window.confirm("确定删除这个黑话词条吗？")) {
      return;
    }
    try {
      await api.deleteKeyword(keywordId);
      setSuccessMessage("黑话词条已删除");
      resetKeywordForm();
      await loadCategories(selectedCategory?.id ?? null, selectedSubcategory?.id ?? null);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  function startEditCategory(item: KeywordCategory): void {
    setEditingCategoryId(item.id);
    setCategoryForm({
      name: item.name,
      description: item.description,
      sort_order: item.sort_order,
    });
  }

  function startEditSubcategory(item: KeywordSubcategory): void {
    setEditingSubcategoryId(item.id);
    setSubcategoryForm({
      name: item.name,
      description: item.description,
      sort_order: item.sort_order,
    });
  }

  function startEditKeyword(item: Keyword): void {
    setEditingKeywordId(item.id);
    setKeywordForm({
      keyword: item.keyword,
      meaning: item.meaning,
      sort_order: item.sort_order,
      subcategory_id: item.subcategory_id,
    });
  }

  return (
    <div className="page-stack">
      <section className="section-heading">
        <div>
          <div className="eyebrow">Jargon Dictionary</div>
          <h1>黑话字典</h1>
        </div>
        <button className="ghost-button" onClick={() => void loadCategories()}>
          刷新
        </button>
      </section>

      {error ? <div className="inline-error">{error}</div> : null}
      {successMessage ? <div className="inline-success">{successMessage}</div> : null}

      <section className="panel-grid three">
        <div className="panel">
          <div className="panel-header compact">
            <div>
              <div className="eyebrow">Level 1</div>
              <h2>一级分类</h2>
            </div>
          </div>
          {loading ? <div className="empty-inline">正在加载字典...</div> : null}
          <div className="stack-list">
            {categories.map((item) => (
              <button
                key={item.id}
                className={`stack-card ${item.id === selectedCategoryId ? "active" : ""}`}
                onClick={() => {
                  setSelectedCategoryId(item.id);
                  setSelectedSubcategoryId(item.subcategories[0]?.id ?? null);
                }}
              >
                <strong>{item.name}</strong>
                <span>{item.keywords.length} 个黑话</span>
              </button>
            ))}
          </div>
          <form className="inline-form" onSubmit={(event) => void handleCategorySubmit(event)}>
            <input
              placeholder="一级分类名称"
              value={categoryForm.name}
              onChange={(event) => setCategoryForm((state) => ({ ...state, name: event.target.value }))}
            />
            <textarea
              placeholder="分类说明"
              rows={3}
              value={categoryForm.description}
              onChange={(event) => setCategoryForm((state) => ({ ...state, description: event.target.value }))}
            />
            <input
              type="number"
              placeholder="排序"
              value={categoryForm.sort_order}
              onChange={(event) =>
                setCategoryForm((state) => ({ ...state, sort_order: Number(event.target.value || 0) }))
              }
            />
            <div className="action-row">
              <button className="primary-button" type="submit">
                {editingCategoryId !== null ? "保存一级分类" : "新增一级分类"}
              </button>
              {editingCategoryId !== null ? (
                <button className="ghost-button" type="button" onClick={resetCategoryForm}>
                  取消
                </button>
              ) : null}
            </div>
          </form>
          {selectedCategory !== null ? (
            <div className="action-row top-space">
              <button className="ghost-button" onClick={() => startEditCategory(selectedCategory)}>
                编辑当前分类
              </button>
              <button className="danger-button" onClick={() => void handleDeleteCategory(selectedCategory.id)}>
                删除当前分类
              </button>
            </div>
          ) : null}
        </div>

        <div className="panel">
          <div className="panel-header compact">
            <div>
              <div className="eyebrow">Level 2</div>
              <h2>二级分类</h2>
            </div>
          </div>
          {selectedCategory === null ? (
            <div className="empty-state small">先选择一级分类。</div>
          ) : (
            <>
              <div className="stack-list">
                {selectedCategory.subcategories.map((item) => (
                  <button
                    key={item.id}
                    className={`stack-card ${item.id === selectedSubcategoryId ? "active" : ""}`}
                    onClick={() => setSelectedSubcategoryId(item.id)}
                  >
                    <strong>{item.name}</strong>
                    <span>{item.keywords.length} 个黑话</span>
                  </button>
                ))}
              </div>
              <form className="inline-form" onSubmit={(event) => void handleSubcategorySubmit(event)}>
                <input
                  placeholder="二级分类名称"
                  value={subcategoryForm.name}
                  onChange={(event) =>
                    setSubcategoryForm((state) => ({ ...state, name: event.target.value }))
                  }
                />
                <textarea
                  placeholder="二级分类说明"
                  rows={3}
                  value={subcategoryForm.description}
                  onChange={(event) =>
                    setSubcategoryForm((state) => ({ ...state, description: event.target.value }))
                  }
                />
                <input
                  type="number"
                  placeholder="排序"
                  value={subcategoryForm.sort_order}
                  onChange={(event) =>
                    setSubcategoryForm((state) => ({ ...state, sort_order: Number(event.target.value || 0) }))
                  }
                />
                <div className="action-row">
                  <button className="primary-button" type="submit">
                    {editingSubcategoryId !== null ? "保存二级分类" : "新增二级分类"}
                  </button>
                  {editingSubcategoryId !== null ? (
                    <button className="ghost-button" type="button" onClick={resetSubcategoryForm}>
                      取消
                    </button>
                  ) : null}
                </div>
              </form>
              {selectedSubcategory !== null ? (
                <div className="action-row top-space">
                  <button className="ghost-button" onClick={() => startEditSubcategory(selectedSubcategory)}>
                    编辑当前二级分类
                  </button>
                  <button className="danger-button" onClick={() => void handleDeleteSubcategory(selectedSubcategory.id)}>
                    删除当前二级分类
                  </button>
                </div>
              ) : null}
            </>
          )}
        </div>

        <div className="panel">
          <div className="panel-header compact">
            <div>
              <div className="eyebrow">Keywords</div>
              <h2>黑话词条</h2>
            </div>
          </div>
          {selectedCategory === null ? (
            <div className="empty-state small">先选择分类。</div>
          ) : (
            <>
              <form className="inline-form" onSubmit={(event) => void handleKeywordSubmit(event)}>
                <select
                  value={keywordForm.subcategory_id || selectedSubcategory?.id || ""}
                  onChange={(event) =>
                    setKeywordForm((state) => ({ ...state, subcategory_id: Number(event.target.value || 0) }))
                  }
                >
                  {selectedCategory.subcategories.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
                <input
                  placeholder="黑话名称"
                  value={keywordForm.keyword}
                  onChange={(event) => setKeywordForm((state) => ({ ...state, keyword: event.target.value }))}
                />
                <textarea
                  placeholder="黑话含义"
                  rows={3}
                  value={keywordForm.meaning}
                  onChange={(event) => setKeywordForm((state) => ({ ...state, meaning: event.target.value }))}
                />
                <input
                  type="number"
                  placeholder="排序"
                  value={keywordForm.sort_order}
                  onChange={(event) =>
                    setKeywordForm((state) => ({ ...state, sort_order: Number(event.target.value || 0) }))
                  }
                />
                <div className="action-row">
                  <button className="primary-button" type="submit">
                    {editingKeywordId !== null ? "保存黑话词条" : "新增黑话词条"}
                  </button>
                  {editingKeywordId !== null ? (
                    <button className="ghost-button" type="button" onClick={resetKeywordForm}>
                      取消
                    </button>
                  ) : null}
                </div>
              </form>
              <div className="table-scroll top-space">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>黑话</th>
                      <th>含义</th>
                      <th>二级分类</th>
                      <th>排序</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {selectedCategory.keywords.length === 0 ? (
                      <tr>
                        <td colSpan={5}>
                          <div className="empty-inline">当前分类还没有黑话词条。</div>
                        </td>
                      </tr>
                    ) : (
                      selectedCategory.keywords.map((item) => (
                        <tr key={item.id}>
                          <td>{item.keyword}</td>
                          <td>{item.meaning}</td>
                          <td>{item.subcategory_name}</td>
                          <td>{item.sort_order}</td>
                          <td>
                            <div className="action-row compact-end">
                              <button className="text-link-button" onClick={() => startEditKeyword(item)}>
                                编辑
                              </button>
                              <button className="text-link-button danger-text" onClick={() => void handleDeleteKeyword(item.id)}>
                                删除
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </section>
    </div>
  );
}
