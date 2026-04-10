import { useEffect, useMemo, useState } from "react";

import { api, FileEntry, formatDateTime, formatFileSize } from "@/lib/api";

export default function FilesPage(): React.JSX.Element {
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");

  const filteredFiles = useMemo(() => {
    return files.filter((item) => {
      if (search && !item.name.toLowerCase().includes(search.toLowerCase())) {
        return false;
      }
      if (typeFilter && item.type !== typeFilter) {
        return false;
      }
      return true;
    });
  }, [files, search, typeFilter]);

  const selectedFiles = useMemo(
    () => filteredFiles.filter((item) => selectedPaths.has(item.path)),
    [filteredFiles, selectedPaths],
  );

  const summary = useMemo(() => {
    return {
      total: files.length,
      json: files.filter((item) => item.type === "json").length,
      spreadsheets: files.filter((item) => item.type === "spreadsheet").length,
      totalSize: files.reduce((sum, item) => sum + item.size, 0),
    };
  }, [files]);

  const allFilteredSelected = filteredFiles.length > 0 && filteredFiles.every((item) => selectedPaths.has(item.path));
  const hasAnySelection = selectedPaths.size > 0;

  useEffect(() => {
    void loadFiles();
  }, []);

  async function loadFiles(showLoading = true): Promise<void> {
    try {
      if (showLoading) {
        setLoading(true);
      }
      const data = await api.listFiles();
      setFiles(data);
      setSelectedPaths((state) => {
        const next = new Set<string>();
        const validPaths = new Set(data.map((item) => item.path));
        state.forEach((item) => {
          if (validPaths.has(item)) {
            next.add(item);
          }
        });
        return next;
      });
      setError("");
    } catch (caughtError) {
      setError((caughtError as Error).message);
    } finally {
      setLoading(false);
    }
  }

  function toggleSelection(path: string): void {
    setSelectedPaths((state) => {
      const next = new Set(state);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  }

  function toggleSelectAllFiltered(): void {
    setSelectedPaths((state) => {
      const next = new Set(state);
      if (allFilteredSelected) {
        filteredFiles.forEach((item) => next.delete(item.path));
      } else {
        filteredFiles.forEach((item) => next.add(item.path));
      }
      return next;
    });
  }

  function clearSelection(): void {
    setSelectedPaths(new Set());
  }

  async function handleDeleteFile(item: FileEntry): Promise<void> {
    if (!window.confirm(`确定删除文件 ${item.name} 吗？`)) {
      return;
    }

    try {
      setDeleting(true);
      await api.deleteFile(item.path);
      await loadFiles(false);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    } finally {
      setDeleting(false);
    }
  }

  async function handleBatchDelete(): Promise<void> {
    const paths = Array.from(selectedPaths);
    if (paths.length === 0) {
      return;
    }
    if (!window.confirm(`确定批量删除已选中的 ${paths.length} 个文件吗？`)) {
      return;
    }

    try {
      setDeleting(true);
      await api.deleteFiles(paths);
      setSelectedPaths(new Set());
      await loadFiles(false);
    } catch (caughtError) {
      setError((caughtError as Error).message);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="page-stack files-page">
      <section className="section-heading">
        <div>
          <div className="eyebrow">Local File Desk</div>
          <h1>本地文件管理</h1>
        </div>
        <button className="ghost-button" onClick={() => void loadFiles()}>
          刷新
        </button>
      </section>

      {error ? <div className="inline-error">{error}</div> : null}

      <section className="stats-grid">
        <div className="panel stat-card">
          <span>总文件数</span>
          <strong>{summary.total}</strong>
        </div>
        <div className="panel stat-card">
          <span>JSON 文件</span>
          <strong>{summary.json}</strong>
        </div>
        <div className="panel stat-card">
          <span>表格文件</span>
          <strong>{summary.spreadsheets}</strong>
        </div>
        <div className="panel stat-card">
          <span>总大小</span>
          <strong>{formatFileSize(summary.totalSize)}</strong>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header compact">
          <div>
            <div className="eyebrow">Search</div>
            <h2>文件列表</h2>
          </div>
        </div>
        <div className="field-grid field-grid-two">
          <label className="field">
            <span>搜索文件名</span>
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="输入文件名关键词" />
          </label>
          <label className="field">
            <span>文件类型</span>
            <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
              <option value="">全部类型</option>
              <option value="json">JSON</option>
              <option value="spreadsheet">表格</option>
              <option value="text">文本</option>
              <option value="image">图片</option>
              <option value="xml">XML</option>
            </select>
          </label>
        </div>
        <div className="files-batch-toolbar">
          <div className="action-row">
            <button className="ghost-button" type="button" disabled={filteredFiles.length === 0} onClick={toggleSelectAllFiltered}>
              {allFilteredSelected ? "取消全选当前结果" : "全选当前结果"}
            </button>
            <button className="ghost-button" type="button" disabled={!hasAnySelection} onClick={clearSelection}>
              清空选择
            </button>
            <button className="danger-button" type="button" disabled={!hasAnySelection || deleting} onClick={() => void handleBatchDelete()}>
              批量删除已选
            </button>
          </div>
          <span className="muted-text">
            已选 {selectedPaths.size} 个文件，当前筛选结果 {filteredFiles.length} 个
          </span>
        </div>
      </section>

      <section className="panel">
        {loading ? (
          <div className="empty-state small">正在扫描本地文件...</div>
        ) : filteredFiles.length === 0 ? (
          <div className="empty-state small">当前没有匹配的本地文件。</div>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th className="files-checkbox-col">
                    <input
                      type="checkbox"
                      aria-label="全选当前筛选结果"
                      checked={allFilteredSelected}
                      onChange={toggleSelectAllFiltered}
                    />
                  </th>
                  <th>文件名</th>
                  <th>目录</th>
                  <th>大小</th>
                  <th>修改时间</th>
                  <th>类型</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {filteredFiles.map((item) => {
                  const checked = selectedPaths.has(item.path);
                  return (
                    <tr key={item.path} className={checked ? "table-row-selected" : ""}>
                      <td className="files-checkbox-col">
                        <input
                          type="checkbox"
                          aria-label={`选择文件 ${item.name}`}
                          checked={checked}
                          onChange={() => toggleSelection(item.path)}
                        />
                      </td>
                      <td>{item.name}</td>
                      <td>{item.relative_path}</td>
                      <td>{formatFileSize(item.size)}</td>
                      <td>{formatDateTime(item.time)}</td>
                      <td>{item.type}</td>
                      <td>
                        <div className="action-row compact-end">
                          <button className="text-link-button" onClick={() => void api.openPath(item.path)}>
                            打开
                          </button>
                          <button
                            className="text-link-button danger-text"
                            disabled={deleting}
                            onClick={() => void handleDeleteFile(item)}
                          >
                            删除
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {selectedFiles.length > 0 ? (
          <div className="files-selection-summary">
            当前筛选结果中已选 {selectedFiles.length} 个文件，总大小 {formatFileSize(selectedFiles.reduce((sum, item) => sum + item.size, 0))}
          </div>
        ) : null}
      </section>
    </div>
  );
}
