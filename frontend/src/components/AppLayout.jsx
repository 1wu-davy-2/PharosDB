import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import "./AppLayout.css";

const Icon = ({ name, size = 20 }) => (
  <span className="material-symbols-outlined" style={{ fontSize: size }}>{name}</span>
);

/* ═══ 侧边栏 ═══ */
function Sidebar({ collapsed, onToggle }) {
  const navItems = [
    { icon: "dashboard", label: "监控总览", to: "/" },
    { icon: "query_stats", label: "SQL 分析", to: "/qan" },
    { icon: "storage", label: "实例管理", to: "/instances" },
  ];

  return (
    <aside className={`sidebar ${collapsed ? "sidebar--closed" : ""}`}>
      <div className="sidebar-brand">
        <span className="material-symbols-outlined sidebar-logo" style={{ fontVariationSettings: "'FILL' 1" }}>
          lightbulb
        </span>
        {!collapsed && <span className="sidebar-title">PharosDB</span>}
      </div>

      <nav className="sidebar-nav">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              `sidebar-item ${isActive ? "sidebar-item--active" : ""}`
            }
          >
            <span className="material-symbols-outlined">{item.icon}</span>
            {!collapsed && <span className="sidebar-item-label">{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      <button className="sidebar-toggle" onClick={onToggle}>
        <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
          {collapsed ? "chevron_right" : "chevron_left"}
        </span>
      </button>
    </aside>
  );
}

/* ═══ 顶部栏 ═══ */
function Topbar({ title, onMenuClick }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <header className="topbar">
      <div className="topbar-left">
        <button className="topbar-menu-btn" onClick={onMenuClick}>
          <Icon name="menu" />
        </button>
        <h1 className="topbar-title">{title}</h1>
      </div>
      <div className="topbar-right">
        <div className="topbar-user-wrap">
          <button className="topbar-user" onClick={() => setMenuOpen(!menuOpen)}>
            <div className="topbar-avatar">{user?.username?.[0]?.toUpperCase() || "?"}</div>
            <span className="topbar-username">{user?.username || "User"}</span>
            <Icon name="expand_more" size={18} />
          </button>
          {menuOpen && (
            <div className="topbar-dropdown">
              <button className="topbar-dropdown-item" onClick={handleLogout}>
                <Icon name="logout" size={16} /> 退出登录
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

/* ═══ 主布局 ═══ */
export default function AppLayout({ title, children }) {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="dash-root">
      {mobileOpen && <div className="dash-overlay" onClick={() => setMobileOpen(false)} />}
      <Sidebar
        collapsed={!sidebarOpen && !mobileOpen}
        onToggle={() => setSidebarOpen((v) => !v)}
      />
      <div className="dash-main">
        <Topbar title={title} onMenuClick={() => setMobileOpen((v) => !v)} />
        <main className="dash-content">
          <div className="dash-inner">{children}</div>
        </main>
      </div>
    </div>
  );
}
