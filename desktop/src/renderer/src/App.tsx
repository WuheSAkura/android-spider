import { HashRouter, Link, NavLink, Route, Routes } from "react-router-dom";

import DashboardPage from "@/pages/DashboardPage";
import HistoryPage from "@/pages/HistoryPage";
import RunDetailPage from "@/pages/RunDetailPage";
import SettingsPage from "@/pages/SettingsPage";

function Shell(): React.JSX.Element {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-mark">AS</div>
          <div>
            <strong>Android Spider</strong>
            <span>桌面控制台</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          <NavLink to="/" end className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
            发起任务
          </NavLink>
          <NavLink to="/history" className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
            运行历史
          </NavLink>
          <NavLink to="/settings" className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
            系统设置
          </NavLink>
        </nav>

        <div className="sidebar-footnote">
          <div>当前版本先聚焦单任务串行。</div>
          <Link to="/history" className="text-link">
            查看最近任务
          </Link>
        </div>
      </aside>

      <main className="content-frame">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/runs/:runId" element={<RunDetailPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App(): React.JSX.Element {
  return (
    <HashRouter>
      <Shell />
    </HashRouter>
  );
}
