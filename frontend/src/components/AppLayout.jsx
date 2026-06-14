import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import i18n from "../i18n";
import "./AppLayout.css";

const Icon = ({ name, size = 20 }) => (
  <span className="material-symbols-outlined" style={{ fontSize: size }}>{name}</span>
);

/* ═══ 侧边栏 ═══ */
function Sidebar({ collapsed, onToggle }) {
  const { t } = useTranslation();
  const navItems = [
    { icon: "dashboard", label: t("nav.dashboard"), to: "/" },
    { icon: "query_stats", label: t("nav.qan"), to: "/qan" },
    { icon: "storage", label: t("nav.instances"), to: "/instances" },
    { icon: "device_hub", label: t("nav.locks"), to: "/locks" },
    { icon: "notifications", label: t("nav.alerts"), to: "/alerts" },
    { icon: "verified_user", label: t("nav.advisor"), to: "/advisor" },
    { icon: "tune", label: t("nav.settings"), to: "/settings" },
  ];

  return (
    <aside className={`sidebar ${collapsed ? "sidebar--closed" : ""}`}>
      <div className="sidebar-brand">
        <img src="/lighthouse.svg" alt="PharosDB" className="sidebar-logo" />
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
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  const toggleLang = () => {
    const next = i18n.language === "zh" ? "en" : "zh";
    i18n.changeLanguage(next);
    localStorage.setItem("pharos_lang", next);
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
        {/* 语言切换 */}
        <button
          className="topbar-icon-btn"
          onClick={toggleLang}
          title={i18n.language === "zh" ? "Switch to English" : "切换为中文"}
        >
          <span style={{ fontSize: 13, fontWeight: 600, letterSpacing: 0 }}>
            {i18n.language === "zh" ? "EN" : "中"}
          </span>
        </button>

        {/* 主题切换 */}
        <button
          className="topbar-icon-btn"
          onClick={toggleTheme}
          title={theme === "light" ? "切换暗色" : "Switch to light"}
        >
          <Icon name={theme === "light" ? "dark_mode" : "light_mode"} size={20} />
        </button>

        {/* 用户菜单 */}
        <div className="topbar-user-wrap">
          <button className="topbar-user" onClick={() => setMenuOpen(!menuOpen)}>
            <div className="topbar-avatar">{user?.username?.[0]?.toUpperCase() || "?"}</div>
            <span className="topbar-username">{user?.username || "User"}</span>
            <Icon name="expand_more" size={18} />
          </button>
          {menuOpen && (
            <div className="topbar-dropdown">
              <button className="topbar-dropdown-item" onClick={handleLogout}>
                <Icon name="logout" size={16} /> {t("common.logout")}
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
