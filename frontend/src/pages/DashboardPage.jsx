import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import AppLayout from "../components/AppLayout";
import api from "../services/api";
import "./DashboardPage.css";

/* ── 图标组件 ── */
const Icon = ({ name, size = 20 }) => <span className="material-symbols-outlined" style={{ fontSize: size }}>{name}</span>;

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
  const [instances, setInstances] = useState([]);
  const [overview, setOverview] = useState(null);

  useEffect(() => {
    api.get("/collector/instances/")
      .then(({ data }) => setInstances(data.results || data))
      .catch(() => {});

    // 尝试加载第一个服务的概览
    api.get("/qan/top-queries/")
      .then(({ data }) => {
        if (data.services?.length > 0) {
          return api.get(`/qan/overview/?service=${data.services[0]}&period=24h`);
        }
      })
      .then((res) => { if (res) setOverview(res.data.overview); })
      .catch(() => {});
  }, []);

  const activeCount = instances.filter((i) => i.is_active).length;

  return (
    <AppLayout title="监控总览">
      {/* Row 1: 统计卡片 */}
      <div className="stats-row">
        <StatCard label="Active Instances" value={activeCount || "-"} trend={instances.length > 0 ? `${instances.length} total` : undefined} trendUp statusColor="#10b981" />
        <StatCard label="Unique Queries" value={overview?.unique_queries ? String(Math.round(overview.unique_queries)) : "-"} statusColor="#f59e0b" />
        <StatCard label="Avg Latency" value={overview?.avg_query_time ? `${(overview.avg_query_time * 1000).toFixed(0)}ms` : "-"} statusColor="#10b981" />
        <StatCard label="No-Index Queries" value={overview?.no_index_queries ? String(Math.round(overview.no_index_queries)) : "-"} trendUp={false} statusColor={overview?.no_index_queries > 0 ? "#ef4444" : "#10b981"} />
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
    </AppLayout>
  );
}
