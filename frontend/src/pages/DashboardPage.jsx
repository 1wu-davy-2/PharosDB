import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import "./DashboardPage.css";

/* ── 图标组件 ── */
const Icon = ({ name, size = 20 }) => <span className="material-symbols-outlined" style={{ fontSize: size }}>{name}</span>;

/* ═══════════════════ 侧边栏 ═══════════════════ */
function Sidebar({ collapsed, onToggle }) {
  const navItems = [
    { icon: "dashboard", label: "监控总览", active: true },
    { icon: "query_stats", label: "SQL 分析" },
    { icon: "account_tree", label: "锁等待拓扑" },
    { icon: "storage", label: "实例管理" },
    { icon: "analytics", label: "诊断报告" },
    { icon: "settings", label: "系统设置", bottom: true },
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
          <a
            key={item.label}
            className={`sidebar-item ${item.active ? "sidebar-item--active" : ""} ${item.bottom ? "sidebar-item--bottom" : ""}`}
            href="#"
            onClick={(e) => e.preventDefault()}
          >
            <span className="material-symbols-outlined">{item.icon}</span>
            {!collapsed && <span className="sidebar-item-label">{item.label}</span>}
          </a>
        ))}
      </nav>

      {!collapsed && (
        <button className="sidebar-cta">Create Alert</button>
      )}

      <button className="sidebar-toggle" onClick={onToggle} title={collapsed ? "展开菜单" : "收起菜单"}>
        <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
          {collapsed ? "chevron_right" : "chevron_left"}
        </span>
      </button>
    </aside>
  );
}

/* ═══════════════════ 顶部栏 ═══════════════════ */
function Topbar({ onMenuClick, user, onLogout }) {
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  return (
    <header className="topbar">
      <div className="topbar-left">
        <button className="topbar-menu-btn" onClick={onMenuClick}>
          <Icon name="menu" />
        </button>
        <h1 className="topbar-title">监控总览</h1>
      </div>

      <div className="topbar-right">
        <button className="topbar-icon-btn topbar-notif">
          <Icon name="notifications" />
          <span className="topbar-badge" />
        </button>
        <button className="topbar-icon-btn">
          <Icon name="help" />
        </button>
        <div className="topbar-user-wrap">
          <button className="topbar-user" onClick={() => setUserMenuOpen(!userMenuOpen)}>
            <div className="topbar-avatar">{user?.username?.[0]?.toUpperCase() || "?"}</div>
            <span className="topbar-username">{user?.username || "User"}</span>
            <Icon name="expand_more" size={18} />
          </button>
          {userMenuOpen && (
            <div className="topbar-dropdown">
              <button className="topbar-dropdown-item" onClick={() => { setUserMenuOpen(false); onLogout(); }}>
                <Icon name="logout" size={16} />
                退出登录
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

/* ═══════════════════ 统计卡片 ═══════════════════ */
function StatCard({ label, value, trend, trendUp, statusColor }) {
  return (
    <div className="stat-card">
      <div className="stat-card-header">
        <span className="stat-card-label">{label}</span>
        <span className="stat-card-dot" style={{ background: statusColor }} />
      </div>
      <div className="stat-card-body">
        <span className="stat-card-value">{value}</span>
        {trend && (
          <span className={`stat-card-trend ${trendUp ? "trend-up" : "trend-down"}`}>
            <Icon name={trendUp ? "trending_up" : "trending_down"} size={16} />
            {trend}
          </span>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════ 告警列表 ═══════════════════ */
const alertsData = [
  { severity: "critical", title: "High CPU Utilization", detail: "Instance db-prod-01 reached 95% CPU", time: "2 mins ago" },
  { severity: "warning", title: "Slow Query Spike", detail: "Detected >100 queries over 2s limit", time: "15 mins ago" },
  { severity: "critical", title: "Connection Pool Exhausted", detail: "Max connections (500) reached on db-prod-02", time: "1 hour ago" },
  { severity: "info", title: "Backup Completed", detail: "Daily automated backup finished", time: "3 hours ago" },
];

const severityColor = { critical: "#ef4444", warning: "#f59e0b", info: "#3b82f6" };

/* ═══════════════════ 慢查询表格 ═══════════════════ */
const slowQueries = [
  { rank: 1, fingerprint: "SELECT * FROM users WHERE status = ? AND last_login < ?...", avgTime: "4.2s", execCount: "12,450", trend: "up" },
  { rank: 2, fingerprint: "UPDATE orders SET state = ? WHERE order_id IN (...)", avgTime: "2.8s", execCount: "3,120", trend: "flat" },
  { rank: 3, fingerprint: "DELETE FROM session_logs WHERE created_at < ?", avgTime: "1.5s", execCount: "850", trend: "down" },
];

/* ═══════════════════ 主仪表盘 ═══════════════════ */
export default function DashboardPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileOpen, setMobileOpen] = useState(false);

  const toggleSidebar = () => setSidebarOpen((v) => !v);
  const toggleMobile = () => setMobileOpen((v) => !v);

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="dash-root">
      {mobileOpen && <div className="dash-overlay" onClick={toggleMobile} />}

      <Sidebar collapsed={!sidebarOpen && !mobileOpen} onToggle={toggleSidebar} />

      <div className="dash-main">
        <Topbar onMenuClick={toggleMobile} user={user} onLogout={handleLogout} />

        <main className="dash-content">
          <div className="dash-inner">
            {/* Row 1: 统计卡片 */}
            <div className="stats-row">
              <StatCard label="Active Instances" value="42" trend="2%" trendUp statusColor="#10b981" />
              <StatCard label="Slow Queries" value="1,247" trend="12%" trendUp={false} statusColor="#f59e0b" />
              <StatCard label="Avg Latency" value="23ms" trend="5ms" trendUp statusColor="#10b981" />
              <StatCard label="Active Alerts" value="3" trend="Critical" trendUp={false} statusColor="#ef4444" />
            </div>

            {/* Row 2: 图表 + 告警 */}
            <div className="charts-row">
              <div className="card chart-card">
                <div className="card-header">
                  <h2 className="card-title">数据库健康概览</h2>
                  <div className="chart-tabs">
                    <span className="chart-tab">1H</span>
                    <span className="chart-tab chart-tab--active">24H</span>
                    <span className="chart-tab">7D</span>
                  </div>
                </div>
                <div className="chart-area">
                  <div className="chart-bars">
                    {[1 / 3, 1 / 2, 2 / 3, 1 / 4, 3 / 4, 1 / 2].map((h, i) => (
                      <div key={i} className="chart-bar" style={{ height: `${h * 100}%` }} />
                    ))}
                  </div>
                  <svg className="chart-line" preserveAspectRatio="none" viewBox="0 0 600 200">
                    <path d="M0 200 L100 150 L200 180 L300 100 L400 120 L500 50 L600 80" fill="none" stroke="#f59e0b" strokeWidth="2" />
                  </svg>
                </div>
              </div>

              <div className="card alerts-card">
                <div className="card-header">
                  <h2 className="card-title">最近告警</h2>
                  <span className="card-link">View All</span>
                </div>
                <div className="alerts-list">
                  {alertsData.map((a, i) => (
                    <div key={i} className="alert-item">
                      <span className="alert-dot" style={{ background: severityColor[a.severity] }} />
                      <div>
                        <div className="alert-title">{a.title}</div>
                        <div className="alert-detail">{a.detail}</div>
                        <div className="alert-time">{a.time}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Row 3: 慢查询表格 */}
            <div className="card table-card">
              <h2 className="card-title" style={{ marginBottom: 16 }}>Top 10 慢查询</h2>
              <div className="table-wrap">
                <table className="sql-table">
                  <thead>
                    <tr>
                      <th>Rank</th>
                      <th>SQL Fingerprint</th>
                      <th className="text-right">Avg Time</th>
                      <th className="text-right">Exec Count</th>
                      <th className="text-center">Trend</th>
                    </tr>
                  </thead>
                  <tbody>
                    {slowQueries.map((q) => (
                      <tr key={q.rank}>
                        <td className="text-muted">{q.rank}</td>
                        <td className="text-mono">{q.fingerprint}</td>
                        <td className={`text-right font-medium ${q.rank === 1 ? "text-error" : "text-warning"}`}>{q.avgTime}</td>
                        <td className="text-right">{q.execCount}</td>
                        <td className="text-center">
                          <Icon
                            name={q.trend === "up" ? "trending_up" : q.trend === "down" ? "trending_down" : "trending_flat"}
                            size={16}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
