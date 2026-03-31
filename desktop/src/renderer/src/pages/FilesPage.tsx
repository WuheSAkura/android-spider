import { useEffect, useMemo, useState } from "react";

import { api, FileEntry, formatDateTime, formatFileSize } from "@/lib/api";

export default function FilesPage(): React.JSX.Element {
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [loading, setLoading] = useState(true);
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

  const summary = useMemo(() => {
    return {
      total: files.length,
      json: files.filter((item) => item.type === "json").length,
      spreadsheets: files.filter((item) => item.type === "spreadsheet").length,
      totalSize: files.reduce((sum, item) => sum + item.size, 0),
    };
  }, [files]);

  useEffect(() => {
    void loadFiles();
  }, []);

  async function loadFiles(): Promise<void> {
    try {
      const data = await api.listFiles();
      setFiles(data);
      setError("");
    } catch (caughtError) {
      setError((caughtError as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleDeleteFile(item: FileEntry): Promise<void> {
    if (!window.confirm(`确定删除文件 ${item.name} 吗？`)) {
      return;
    }
    try {
      await api.deleteFile(item.path);
      await loadFiles();
    } catch (caughtError) {
      setError((caughtError as Error).message);
    }
  }

  return (
    <div className="page-stack">
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
                  <th>文件名</th>
                  <th>目录</th>
                  <th>大小</th>
                  <th>修改时间</th>
                  <th>类型</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {filteredFiles.map((item) => (
                  <tr key={item.path}>
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
                        <button className="text-link-button danger-text" onClick={() => void handleDeleteFile(item)}>
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
    </div>
  );
}
