import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import AppLayout from "../components/AppLayout";
import api from "../services/api";
import useForceLayout, { NODE_COLORS } from "../hooks/useForceLayout";
import "./DashboardPage.css";

/* ═══════════════════════════════════════════════════════════════
   Helpers
   ═══════════════════════════════════════════════════════════════ */

const Icon = ({ name, size = 20, className = "" }) => (
  <span className={`material-symbols-outlined ${className}`} style={{ fontSize: size }}>
    {name}
  </span>
);

function fmtMs(seconds) {
  if (seconds == null) return "-";
  const ms = seconds * 1000;
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms)}ms`;
}

function fmtCount(n) {
  if (n == null) return "-";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

const SEVERITY_ICON = { critical: "error", warning: "warning", info: "info" };

/* ═══════════════════════════════════════════════════════════════
   Custom hook — interval with cleanup
   ═══════════════════════════════════════════════════════════════ */

function useInterval(callback, delayMs, enabled = true) {
  const savedCallback = useRef(callback);
  useEffect(() => { savedCallback.current = callback; }, [callback]);

  useEffect(() => {
    if (!enabled || delayMs == null) return;
    savedCallback.current();
    const id = setInterval(() => savedCallback.current(), delayMs);
    return () => clearInterval(id);
  }, [delayMs, enabled]);
}

/* ═══════════════════════════════════════════════════════════════
   Background Particles (pure CSS rendered via JS to vary params)
   ═══════════════════════════════════════════════════════════════ */

const PARTICLE_COUNT = 30;

const particles = Array.from({ length: PARTICLE_COUNT }, (_, i) => ({
  id: i,
  x: `${Math.random() * 100}%`,
  dur: `${8 + Math.random() * 18}s`,
  delay: `${Math.random() * 10}s`,
  drift: `${(Math.random() - 0.5) * 120}px`,
}));

/* ═══════════════════════════════════════════════════════════════
   Health Score Ring
   ═══════════════════════════════════════════════════════════════ */

function HealthScoreRing({ score }) {
  const { t } = useTranslation();
  const pct = Math.min(100, Math.max(0, score ?? 100));
  const color = pct >= 85 ? "#10b981" : pct >= 60 ? "#f59e0b" : "#ef4444";

  return (
    <div className="beacon-health-ring" style={{ "--score-pct": pct }}>
      <span className="beacon-health-ring-label">{t("dashboard.health_score")}</span>
      <span className="beacon-health-ring-value" style={{ color }}>{pct}</span>
      <span className="beacon-health-ring-unit">/ 100</span>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   Stat Card
   ═══════════════════════════════════════════════════════════════ */

function StatCard({ icon, label, value, sub, statAccent }) {
  return (
    <div className="beacon-stat-card" style={{ "--stat-accent": statAccent, "--stat-accent-bg": `${statAccent}18` }}>
      <div>
        <div className="beacon-stat-header">
          <div className="beacon-stat-icon" style={{ "--stat-accent": statAccent, "--stat-accent-bg": `${statAccent}18` }}>
            <Icon name={icon} size={18} />
          </div>
          <span className="beacon-stat-label">{label}</span>
        </div>
        <div className="beacon-stat-value">{value}</div>
      </div>
      {sub && <div className="beacon-stat-sub">{sub}</div>}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   Lock Topology Graph (SVG force layout)
   ═══════════════════════════════════════════════════════════════ */

function LockTopologyGraph({ nodes, edges, width = 700, height = 380 }) {
  const getPos = useForceLayout(nodes, edges, width, height);
  const positions = getPos();

  const markerColors = useMemo(
    () => [...new Set(edges.map(e => {
      const src = nodes.find(n => (n.trx_id ?? n.id) === e.source);
      return NODE_COLORS[src?.type]?.fill || "#6b7280";
    }))],
    [edges, nodes],
  );

  return (
    <svg className="beacon-topo-svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet">
      <defs>
        {markerColors.map(color => (
          <marker
            key={color}
            id={`da-${color.replace("#", "")}`}
            markerWidth="8" markerHeight="8"
            refX="22" refY="3"
            orient="auto"
          >
            <path d="M0,0 L0,6 L8,3 z" fill={color} />
          </marker>
        ))}
      </defs>

      {/* edges */}
      {edges.map((edge, i) => {
        const ps = positions[edge.source];
        const pt = positions[edge.target];
        if (!ps || !pt) return null;
        const srcNode = nodes.find(n => (n.trx_id ?? n.id) === edge.source);
        const color = NODE_COLORS[srcNode?.type]?.fill || "#6b7280";
        const markerId = `da-${color.replace("#", "")}`;
        const dx = pt.x - ps.x;
        const dy = pt.y - ps.y;
        const len = Math.sqrt(dx * dx + dy * dy) || 1;
        const ex = pt.x - (dx / len) * 24;
        const ey = pt.y - (dy / len) * 24;
        const mx = (ps.x + ex) / 2;
        const my = (ps.y + ey) / 2;
        return (
          <g key={i}>
            <line
              x1={ps.x} y1={ps.y} x2={ex} y2={ey}
              stroke={color} strokeWidth={2} strokeOpacity={0.7}
              markerEnd={`url(#${markerId})`}
            />
            {edge.wait_secs > 0 && (
              <text x={mx} y={my - 4} className="beacon-topo-edge-label">
                {edge.wait_secs}s
              </text>
            )}
          </g>
        );
      })}

      {/* nodes */}
      {nodes.map((node) => {
        const id = node.trx_id ?? node.id;
        const p = positions[id];
        if (!p) return null;
        const { fill, stroke } = NODE_COLORS[node.type] || { fill: "#6b7280", stroke: "#374151" };
        const label = id.length > 8 ? id.slice(-6) : id;
        return (
          <g key={id} className="beacon-topo-node">
            <circle cx={p.x} cy={p.y} r={20} fill={fill} stroke={stroke} strokeWidth={2} />
            <text x={p.x} y={p.y + 4} className="beacon-topo-node-label">{label}</text>
          </g>
        );
      })}
    </svg>
  );
}

/* ═══════════════════════════════════════════════════════════════
   Pharos Radar — adaptive lock topology area
   ═══════════════════════════════════════════════════════════════ */

function PharosRadar({ status, topology, loading, error, instanceName }) {
  const { t } = useTranslation();
  const hasLocks = topology && topology.nodes?.length > 0;
  const hasDeadlock = topology?.has_deadlock;

  let badgeLabel, badgeClass;
  if (hasDeadlock) {
    badgeLabel = t("dashboard.radar_deadlock");
    badgeClass = "beacon-radar-badge--danger";
  } else if (hasLocks) {
    badgeLabel = t("dashboard.radar_active", { count: topology.nodes.length });
    badgeClass = "beacon-radar-badge--warn";
  } else {
    badgeLabel = t("dashboard.radar_idle");
    badgeClass = "beacon-radar-badge--ok";
  }

  return (
    <div className={`beacon-radar ${hasDeadlock ? "beacon-radar--deadlock" : hasLocks ? "beacon-radar--active" : "beacon-radar--idle"}`}>
      {/* header */}
      <div className="beacon-radar-header">
        <span className="beacon-radar-title">
          <Icon name="track_changes" size={18} />
          {t("dashboard.radar_title")}
          {instanceName && <span style={{ fontWeight: 400, fontSize: 12, color: "var(--color-text-dim)" }}>— {instanceName}</span>}
        </span>
        <span className={`beacon-radar-badge ${badgeClass}`}>{badgeLabel}</span>
      </div>

      {/* body */}
      <div className="beacon-radar-body">
        {loading && !topology && (
          <div className="beacon-radar-state">
            <Icon name="progress_activity" size={28} />
            {t("common.loading")}
          </div>
        )}

        {error && !loading && (
          <div className="beacon-radar-state beacon-radar-error">
            <Icon name="error_outline" size={28} />
            {error}
          </div>
        )}

        {!loading && !error && !hasLocks && (
          <div className="beacon-idle">
            <div className="beacon-idle-ring">
              <div className="beacon-idle-core" />
              <div className="beacon-idle-pulse" />
              <div className="beacon-idle-pulse" />
            </div>
            <span className="beacon-idle-text">{t("dashboard.no_locks")}</span>
            <span className="beacon-idle-sub">{t("dashboard.no_locks_desc")}</span>
          </div>
        )}

        {!loading && !error && hasLocks && (
          <LockTopologyGraph nodes={topology.nodes} edges={topology.edges} />
        )}

        {/* deadlock overlay */}
        {hasDeadlock && (
          <div className="beacon-deadlock-overlay">
            <div className="beacon-deadlock-ring" />
            <div className="beacon-deadlock-ring" />
            <div className="beacon-deadlock-ring" />
            <span className="beacon-deadlock-label">{t("dashboard.deadlock_detected")}</span>
          </div>
        )}
      </div>

      {/* legend */}
      {hasLocks && (
        <div className="beacon-radar-legend">
          {[
            { type: "blocker", color: NODE_COLORS.blocker.fill },
            { type: "waiter", color: NODE_COLORS.waiter.fill },
            { type: "both", color: NODE_COLORS.both.fill },
            { type: "deadlock", color: NODE_COLORS.deadlock.fill },
          ].map(({ type, color }) => (
            <span key={type} className="beacon-legend-item">
              <svg width="10" height="10" viewBox="0 0 10 10">
                <circle cx="5" cy="5" r="4" fill={color} />
              </svg>
              {t(`locks.node_${type}`)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   Alert Stream
   ═══════════════════════════════════════════════════════════════ */

function AlertStream({ alerts, loading }) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <div className="beacon-alert-stream">
      <div className="beacon-alert-header">
        <span className="beacon-alert-title">
          <Icon name="notifications_active" size={18} />
          {t("dashboard.recent_alerts")}
          {alerts.length > 0 && (
            <span className="beacon-alert-count">{alerts.length}</span>
          )}
        </span>
        <span className="beacon-alert-link" onClick={() => navigate("/alerts")}>
          {t("dashboard.view_all")} →
        </span>
      </div>

      <div className="beacon-alert-list">
        {loading && alerts.length === 0 && (
          <div className="beacon-alert-empty">
            <Icon name="progress_activity" size={28} />
            {t("common.loading")}
          </div>
        )}

        {!loading && alerts.length === 0 && (
          <div className="beacon-alert-empty">
            <Icon name="check_circle" size={36} />
            {t("dashboard.no_alerts")}
          </div>
        )}

        {alerts.slice(0, 8).map((a, i) => (
          <div key={a.id || i} className="beacon-alert-item" onClick={() => navigate("/alerts")}>
            <span className={`beacon-alert-dot beacon-alert-dot--${a.rule_severity || a.severity || "warning"}`} />
            <div className="beacon-alert-body">
              <div className="beacon-alert-name">{a.rule_name || a.name || `Alert #${i + 1}`}</div>
              {a.instance_name && (
                <div className="beacon-alert-instance">{a.instance_name}</div>
              )}
              <div className="beacon-alert-time">{a.fired_at ? new Date(a.fired_at).toLocaleString() : ""}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   Instance Health Grid
   ═══════════════════════════════════════════════════════════════ */

function InstanceHealthGrid({ instances, onSelect }) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const sorted = useMemo(() => {
    const order = { connected: 0, disconnected: 1 };
    return [...instances].sort((a, b) => {
      const sa = a.is_active ? order[a.connection_status] ?? 2 : 3;
      const sb = b.is_active ? order[b.connection_status] ?? 2 : 3;
      return sa - sb;
    });
  }, [instances]);

  return (
    <div className="beacon-instance-grid">
      <div className="beacon-instance-header">
        <Icon name="dns" size={18} />
        {t("dashboard.instance_health")}
        <span style={{ fontSize: 11, color: "var(--color-text-dim)", fontWeight: 400, marginLeft: "auto" }}>
          {sorted.filter(i => i.connection_status === "connected").length}/{sorted.length} {t("dashboard.online")}
        </span>
      </div>

      {sorted.length === 0 ? (
        <div className="beacon-instance-empty">{t("instances.no_instances")}</div>
      ) : (
        <div className="beacon-instance-list">
          {sorted.map((inst) => {
            let indicatorClass = "beacon-instance-indicator--inactive";
            if (inst.is_active) {
              indicatorClass = inst.connection_status === "connected"
                ? "beacon-instance-indicator--connected"
                : "beacon-instance-indicator--disconnected";
            }

            return (
              <div
                key={inst.id}
                className="beacon-instance-item"
                onClick={() => onSelect?.(String(inst.id))}
                title={inst.last_error || ""}
              >
                <span className={`beacon-instance-indicator ${indicatorClass}`} />
                <div className="beacon-instance-info">
                  <div className="beacon-instance-name">{inst.name}</div>
                  <div className="beacon-instance-meta">
                    <span className="beacon-instance-type">{inst.db_type}</span>
                    <span>{inst.host}:{inst.port}</span>
                    {inst.db_version && <span>v{inst.db_version}</span>}
                  </div>
                </div>
                {inst.connection_status === "disconnected" && inst.last_error && (
                  <Icon name="error_outline" size={16} style={{ color: "var(--color-error-alt)" }} />
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   Slow Query Table
   ═══════════════════════════════════════════════════════════════ */

function SlowQueryTable({ queries, loading, instanceName }) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <div className="beacon-slow-table">
      <div className="beacon-slow-header">
        <span className="beacon-slow-title">
          <Icon name="speed" size={18} />
          {t("dashboard.top_slow")}
          {instanceName && <span style={{ fontWeight: 400, fontSize: 12, color: "var(--color-text-dim)" }}>— {instanceName}</span>}
        </span>
        <span className="beacon-slow-link" onClick={() => navigate("/qan")}>
          {t("qan.title")} →
        </span>
      </div>

      <div className="beacon-table-wrap">
        {loading && queries.length === 0 && (
          <div className="beacon-table-empty">{t("common.loading")}</div>
        )}

        {!loading && queries.length === 0 && (
          <div className="beacon-table-empty">{t("qan.no_data")}</div>
        )}

        {queries.length > 0 && (
          <table className="beacon-table">
            <thead>
              <tr>
                <th>#</th>
                <th>{t("qan.col_fingerprint")}</th>
                <th className="beacon-text-right">{t("qan.col_avg_time")}</th>
                <th className="beacon-text-right">{t("qan.col_count")}</th>
                <th className="beacon-text-right">{t("qan.col_rows")}</th>
                <th className="beacon-text-center">{t("qan.col_no_index")}</th>
              </tr>
            </thead>
            <tbody>
              {queries.slice(0, 10).map((q, i) => {
                const rank = i + 1;
                return (
                  <tr key={q.queryid || i}>
                    <td>
                      <span className={`beacon-table-rank ${rank <= 3 ? `beacon-table-rank--${rank}` : ""}`}>
                        {rank}
                      </span>
                    </td>
                    <td>
                      <div className="beacon-table-fingerprint" title={q.fingerprint}>
                        {q.fingerprint}
                      </div>
                    </td>
                    <td className={`beacon-text-right ${rank <= 3 ? "beacon-text-error" : ""}`}>
                      {fmtMs(q.m_query_time_avg)}
                    </td>
                    <td className="beacon-text-right beacon-text-mono">{fmtCount(q.num_queries)}</td>
                    <td className="beacon-text-right beacon-text-mono">{fmtCount(q.m_rows_examined_sum)}</td>
                    <td className="beacon-text-center">
                      {q.m_no_index_used_sum > 0 && (
                        <span className="beacon-text-warn">{fmtCount(q.m_no_index_used_sum)}</span>
                      )}
                      {!q.m_no_index_used_sum && <span className="beacon-text-muted">-</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════
   Dashboard Page — Main
   ═══════════════════════════════════════════════════════════════ */

export default function DashboardPage() {
  const { t } = useTranslation();

  // ── controls ──
  const [selectedInstance, setSelectedInstance] = useState(""); // "" = all
  const [period, setPeriod] = useState("1h");
  const [autoRefresh, setAutoRefresh] = useState(true);

  // ── data ──
  const [instances, setInstances] = useState([]);
  const [overview, setOverview] = useState(null);
  const [topQueries, setTopQueries] = useState([]);
  const [lockTopology, setLockTopology] = useState(null);  // single instance topology
  const [lockStatus, setLockStatus] = useState("loading"); // loading | idle | active | deadlock
  const [lockError, setLockError] = useState("");
  const [alerts, setAlerts] = useState([]);
  const [alertsSummary, setAlertsSummary] = useState({ critical: 0, warning: 0, total: 0 });
  const [now, setNow] = useState(new Date());

  // loading flags
  const [loadingOverview, setLoadingOverview] = useState(false);
  const [loadingQueries, setLoadingQueries] = useState(false);
  const [loadingLock, setLoadingLock] = useState(false);
  const [loadingAlerts, setLoadingAlerts] = useState(false);

  // ── derived ──
  const mySQLInstances = useMemo(
    () => instances.filter(i => i.db_type === "mysql" && i.is_active && i.connection_status === "connected"),
    [instances],
  );

  const selectedInst = useMemo(
    () => instances.find(i => String(i.id) === selectedInstance) || null,
    [instances, selectedInstance],
  );

  const serviceName = selectedInst ? selectedInst.name : (mySQLInstances[0]?.name || "");

  // ── health score ──
  const healthScore = useMemo(() => {
    let score = 100;
    const connected = instances.filter(i => i.connection_status === "connected").length;
    const total = instances.length;
    if (total > 0) {
      score -= Math.round(((total - connected) / total) * 25);
    }
    if (lockStatus === "deadlock") score -= 30;
    else if (lockStatus === "active") score -= 10;
    if (alertsSummary.critical > 0) score -= alertsSummary.critical * 15;
    if (alertsSummary.warning > 0) score -= alertsSummary.warning * 5;
    if (overview?.no_index_queries > 0 && overview?.total_queries > 0) {
      const ratio = overview.no_index_queries / overview.total_queries;
      score -= Math.round(ratio * 20);
    }
    return Math.max(0, Math.min(100, score));
  }, [instances, lockStatus, alertsSummary, overview]);

  // ── clock tick ──
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  // ── data fetchers ──
  const fetchInstances = useCallback(async () => {
    try {
      const { data } = await api.get("/collector/instances/");
      setInstances(data.results || data || []);
    } catch { /* silent */ }
  }, []);

  const fetchOverview = useCallback(async () => {
    if (!serviceName) return;
    setLoadingOverview(true);
    try {
      const { data } = await api.get(`/qan/overview/?service=${encodeURIComponent(serviceName)}&period=${period}`);
      setOverview(data.overview || null);
    } catch { setOverview(null); }
    finally { setLoadingOverview(false); }
  }, [serviceName, period]);

  const fetchTopQueries = useCallback(async () => {
    const svc = serviceName || (mySQLInstances[0]?.name);
    if (!svc) return;
    setLoadingQueries(true);
    try {
      const { data } = await api.get(
        `/qan/top-queries/?service=${encodeURIComponent(svc)}&period=${period}&sort=m_query_time_sum&limit=10&order=DESC`,
      );
      setTopQueries(data.queries || []);
    } catch { setTopQueries([]); }
    finally { setLoadingQueries(false); }
  }, [serviceName, period, mySQLInstances]);

  const fetchLockTopology = useCallback(async () => {
    setLoadingLock(true);
    try {
      // In global mode, check all MySQL instances; in drill‑down, check the selected one
      const targets = selectedInstance
        ? [selectedInstance]
        : mySQLInstances.map(i => String(i.id));

      if (targets.length === 0) {
        setLockStatus("idle");
        setLockTopology(null);
        setLockError("");
        return;
      }

      // Check each target sequentially — return the first that has locks (worst one first)
      let worstTopo = null;
      let worstStatus = "idle";

      for (const iid of targets) {
        try {
          const { data } = await api.get(`/locks/topology/?instance_id=${iid}`);
          if (data.has_deadlock) {
            setLockTopology(data);
            setLockStatus("deadlock");
            setLockError("");
            return; // deadlock is the worst — stop immediately
          }
          if (data.nodes?.length > 0 && worstStatus !== "active") {
            worstTopo = data;
            worstStatus = "active";
          }
        } catch {
          // skip unreachable instances
        }
      }

      if (worstTopo) {
        setLockTopology(worstTopo);
        setLockStatus("active");
        setLockError("");
      } else {
        setLockTopology(null);
        setLockStatus("idle");
        setLockError("");
      }
    } catch (e) {
      setLockError(e.response?.data?.error || e.message);
      setLockStatus("idle");
    }
    finally { setLoadingLock(false); }
  }, [selectedInstance, mySQLInstances]);

  const fetchAlerts = useCallback(async () => {
    setLoadingAlerts(true);
    try {
      const params = { status: "firing" };
      if (selectedInstance) params.instance_id = selectedInstance;
      const { data } = await api.get("/alerts/events/", { params });
      const list = data.results || data || [];
      setAlerts(list);

      // summary
      try {
        const sumRes = await api.get("/alerts/events/summary/");
        setAlertsSummary(sumRes.data || { critical: 0, warning: 0, total: 0 });
      } catch { /* use what we have */ }
    } catch { setAlerts([]); }
    finally { setLoadingAlerts(false); }
  }, [selectedInstance]);

  // ── polling ──
  useInterval(fetchInstances, 120_000, autoRefresh);
  useInterval(fetchOverview, 30_000, autoRefresh);
  useInterval(fetchTopQueries, 60_000, autoRefresh);
  useInterval(fetchAlerts, 30_000, autoRefresh);

  // Lock polling: adaptive — 5s when active/deadlock, 30s when idle
  const lockInterval = lockStatus === "active" || lockStatus === "deadlock" ? 5_000 : 30_000;
  useInterval(fetchLockTopology, lockInterval, autoRefresh);

  // refetch on dep changes (immediate)
  useEffect(() => { fetchInstances(); }, [fetchInstances]);
  useEffect(() => { fetchOverview(); }, [fetchOverview]);
  useEffect(() => { fetchTopQueries(); }, [fetchTopQueries]);
  useEffect(() => { fetchAlerts(); }, [fetchAlerts]);
  useEffect(() => { fetchLockTopology(); }, [fetchLockTopology]);

  // ── render ──
  const activeCount = instances.filter(i => i.is_active && i.connection_status === "connected").length;
  const totalInstances = instances.length;

  return (
    <AppLayout title={t("dashboard.title")}>
      <div className="beacon-root">

        {/* Background particles */}
        <div className="beacon-bg-layer">
          {particles.map(p => (
            <div
              key={p.id}
              className="beacon-particle"
              style={{ "--x": p.x, "--dur": p.dur, "--delay": p.delay, "--drift": p.drift }}
            />
          ))}
        </div>

        {/* Scanning beam */}
        <div className="beacon-scan" />

        <div className="beacon-inner">

          {/* ═══ Control Bar ═══ */}
          <div className="beacon-control-bar">
            <div className="beacon-ctrl-group">
              <span className="beacon-ctrl-label">{t("qan.filter_service")}</span>
              <select
                className="beacon-select"
                value={selectedInstance}
                onChange={e => setSelectedInstance(e.target.value)}
              >
                <option value="">{t("dashboard.instance_all")} ({totalInstances})</option>
                {instances.filter(i => i.is_active && i.connection_status === "connected").map(i => (
                  <option key={i.id} value={String(i.id)}>
                    {i.name} ({i.db_type})
                  </option>
                ))}
              </select>
            </div>

            <div className="beacon-ctrl-group">
              <span className="beacon-ctrl-label">{t("qan.filter_period")}</span>
              <div className="beacon-period-tabs">
                {["1h", "6h", "24h", "7d"].map(p => (
                  <button
                    key={p}
                    className={`beacon-period-tab ${period === p ? "beacon-period-tab--active" : ""}`}
                    onClick={() => setPeriod(p)}
                  >
                    {t(`qan.period_${p}`)}
                  </button>
                ))}
              </div>
            </div>

            <label className="beacon-toggle">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={e => setAutoRefresh(e.target.checked)}
              />
              <span className="beacon-toggle-track" />
              {t("dashboard.auto_refresh")}
            </label>

            <div className="beacon-ctrl-spacer" />

            <div className="beacon-ctrl-time">
              <span className="beacon-ctrl-dot" />
              {now.toLocaleTimeString()}
            </div>
          </div>

          {/* ═══ Stats Row ═══ */}
          <div className="beacon-stats-row">
            <HealthScoreRing score={healthScore} />
            <StatCard
              icon="dns"
              label={t("dashboard.active_instances")}
              value={`${activeCount}/${totalInstances}`}
              sub={totalInstances > 0 ? `${t("dashboard.online")} ${activeCount}` : t("instances.no_instances")}
              statAccent="#10b981"
            />
            <StatCard
              icon="query_stats"
              label={t("dashboard.unique_queries")}
              value={fmtCount(overview?.unique_queries)}
              sub={overview?.total_queries != null ? `${t("qan.total_queries")}: ${fmtCount(overview.total_queries)}` : undefined}
              statAccent="#3b82f6"
            />
            <StatCard
              icon="timer"
              label={t("dashboard.avg_latency")}
              value={fmtMs(overview?.avg_query_time)}
              sub={overview?.total_queries > 0 && overview?.unique_queries > 0
                ? `${fmtCount(overview.total_query_time)}s ${t("qan.metric_total_time")}`
                : undefined}
              statAccent="#f59e0b"
            />
            <StatCard
              icon="warning"
              label={t("dashboard.active_alerts")}
              value={alertsSummary.total || 0}
              sub={
                <span style={{ display: "flex", gap: 8 }}>
                  {alertsSummary.critical > 0 && (
                    <span className="beacon-stat-trend-up">● {alertsSummary.critical} critical</span>
                  )}
                  {alertsSummary.warning > 0 && (
                    <span style={{ color: "#f59e0b" }}>● {alertsSummary.warning} warning</span>
                  )}
                </span>
              }
              statAccent={alertsSummary.critical > 0 ? "#ef4444" : "#f59e0b"}
            />
          </div>

          {/* ═══ Main Stage ═══ */}
          <div className="beacon-main-stage">
            <PharosRadar
              status={lockStatus}
              topology={lockTopology}
              loading={loadingLock}
              error={lockError}
              instanceName={selectedInst?.name}
            />
            <AlertStream alerts={alerts} loading={loadingAlerts} />
          </div>

          {/* ═══ Bottom Row ═══ */}
          <div className="beacon-bottom-row">
            <InstanceHealthGrid
              instances={instances}
              onSelect={id => setSelectedInstance(prev => prev === id ? "" : id)}
            />
            <SlowQueryTable
              queries={topQueries}
              loading={loadingQueries}
              instanceName={selectedInst?.name}
            />
          </div>

        </div>
      </div>
    </AppLayout>
  );
}
