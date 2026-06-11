import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import AppLayout from "../components/AppLayout";
import api from "../services/api";
import "./LockPage.css";

// ─── tiny force simulation (no d3 dependency) ────────────────────────────────

function useForceLayout(nodes, edges, width, height) {
  const posRef = useRef({});

  const getPos = useCallback(() => {
    const positions = {};
    const n = nodes.length;
    if (n === 0) return positions;

    nodes.forEach((node, i) => {
      if (posRef.current[node.trx_id]) {
        positions[node.trx_id] = { ...posRef.current[node.trx_id] };
      } else {
        const angle = (2 * Math.PI * i) / n;
        const r = Math.min(width, height) * 0.32;
        positions[node.trx_id] = {
          x: width / 2 + r * Math.cos(angle),
          y: height / 2 + r * Math.sin(angle),
          vx: 0,
          vy: 0,
        };
      }
    });

    // run ~120 ticks of force simulation
    const REPULSION = 4000;
    const SPRING_LEN = 160;
    const SPRING_K = 0.04;
    const DAMPING = 0.8;
    const CENTER_K = 0.01;
    const ids = Object.keys(positions);

    for (let tick = 0; tick < 120; tick++) {
      // repulsion between all pairs
      for (let a = 0; a < ids.length; a++) {
        for (let b = a + 1; b < ids.length; b++) {
          const pa = positions[ids[a]];
          const pb = positions[ids[b]];
          let dx = pb.x - pa.x;
          let dy = pb.y - pa.y;
          const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
          const force = REPULSION / (dist * dist);
          dx /= dist; dy /= dist;
          pa.vx -= force * dx; pa.vy -= force * dy;
          pb.vx += force * dx; pb.vy += force * dy;
        }
      }
      // spring attraction along edges
      for (const edge of edges) {
        const ps = positions[edge.source];
        const pt = positions[edge.target];
        if (!ps || !pt) continue;
        let dx = pt.x - ps.x;
        let dy = pt.y - ps.y;
        const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
        const force = SPRING_K * (dist - SPRING_LEN);
        dx /= dist; dy /= dist;
        ps.vx += force * dx; ps.vy += force * dy;
        pt.vx -= force * dx; pt.vy -= force * dy;
      }
      // gravity toward center
      for (const id of ids) {
        const p = positions[id];
        p.vx += (width / 2 - p.x) * CENTER_K;
        p.vy += (height / 2 - p.y) * CENTER_K;
        p.vx *= DAMPING; p.vy *= DAMPING;
        p.x += p.vx; p.y += p.vy;
        // clamp
        p.x = Math.max(60, Math.min(width - 60, p.x));
        p.y = Math.max(60, Math.min(height - 60, p.y));
      }
    }

    posRef.current = positions;
    return positions;
  }, [nodes, edges, width, height]);

  return getPos;
}

// ─── node colour by type ──────────────────────────────────────────────────────

const NODE_COLORS = {
  blocker:  { fill: "#ef4444", stroke: "#b91c1c" },
  waiter:   { fill: "#f97316", stroke: "#c2410c" },
  both:     { fill: "#a855f7", stroke: "#7e22ce" },
  deadlock: { fill: "#eab308", stroke: "#a16207" },
};

// ─── SVG graph component ──────────────────────────────────────────────────────

function LockGraph({ nodes, edges, onNodeClick }) {
  const W = 780, H = 440;
  const getPos = useForceLayout(nodes, edges, W, H);
  const positions = getPos();

  // arrow marker per colour
  const markerColors = [...new Set(edges.map(e => {
    const src = nodes.find(n => n.trx_id === e.source);
    return NODE_COLORS[src?.type]?.fill || "#6b7280";
  }))];

  return (
    <svg className="lock-graph-svg" viewBox={`0 0 ${W} ${H}`}>
      <defs>
        {markerColors.map(color => (
          <marker
            key={color}
            id={`arrow-${color.replace("#", "")}`}
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
        const srcNode = nodes.find(n => n.trx_id === edge.source);
        const color = NODE_COLORS[srcNode?.type]?.fill || "#6b7280";
        const markerId = `arrow-${color.replace("#", "")}`;
        const dx = pt.x - ps.x, dy = pt.y - ps.y;
        const len = Math.sqrt(dx * dx + dy * dy) || 1;
        // shorten line to not overlap node circle (r=22)
        const ex = pt.x - (dx / len) * 24;
        const ey = pt.y - (dy / len) * 24;
        // label midpoint
        const mx = (ps.x + ex) / 2, my = (ps.y + ey) / 2;
        return (
          <g key={i}>
            <line
              x1={ps.x} y1={ps.y} x2={ex} y2={ey}
              stroke={color} strokeWidth={2} strokeOpacity={0.7}
              markerEnd={`url(#${markerId})`}
            />
            {edge.wait_secs > 0 && (
              <text x={mx} y={my - 4} className="lock-edge-label">
                {edge.wait_secs}s
              </text>
            )}
          </g>
        );
      })}

      {/* nodes */}
      {nodes.map((node) => {
        const p = positions[node.trx_id];
        if (!p) return null;
        const { fill, stroke } = NODE_COLORS[node.type] || { fill: "#6b7280", stroke: "#374151" };
        const label = node.trx_id.length > 8 ? node.trx_id.slice(-6) : node.trx_id;
        return (
          <g
            key={node.trx_id}
            className="lock-graph-node"
            onClick={() => onNodeClick(node)}
            style={{ cursor: "pointer" }}
          >
            <circle cx={p.x} cy={p.y} r={22} fill={fill} stroke={stroke} strokeWidth={2} />
            <text x={p.x} y={p.y + 4} className="lock-node-label">{label}</text>
          </g>
        );
      })}
    </svg>
  );
}

// ─── history table ────────────────────────────────────────────────────────────

function HistoryTable({ rows, onRowClick }) {
  const { t } = useTranslation();
  if (!rows.length) return <p className="lock-empty">{t("locks.no_history")}</p>;

  return (
    <div className="lock-table-wrap">
      <table className="lock-table">
        <thead>
          <tr>
            <th>{t("locks.col_time")}</th>
            <th>{t("locks.col_waiter")}</th>
            <th>{t("locks.col_blocker")}</th>
            <th>{t("locks.col_wait_s")}</th>
            <th>{t("locks.col_lock_mode")}</th>
            <th>{t("locks.col_object")}</th>
            <th>{t("locks.col_deadlock")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="lock-table-row" onClick={() => onRowClick(r)}>
              <td className="lock-td-mono">{new Date(r.ts * 1000).toLocaleString()}</td>
              <td className="lock-td-mono">{r.waiting_trx_id}</td>
              <td className="lock-td-mono">{r.blocking_trx_id}</td>
              <td>{r.waiting_age_seconds}</td>
              <td><span className="lock-badge lock-badge--mode">{r.lock_mode}</span></td>
              <td className="lock-td-truncate">
                {r.lock_object_schema}.{r.lock_object_table}
              </td>
              <td>
                {r.is_deadlock ? (
                  <span className="lock-badge lock-badge--deadlock">✕</span>
                ) : (
                  <span className="lock-badge lock-badge--ok">–</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── detail drawer ────────────────────────────────────────────────────────────

function DetailDrawer({ item, onClose }) {
  const { t } = useTranslation();
  if (!item) return null;

  const isNode = "type" in item;
  return (
    <div className="lock-drawer">
      <div className="lock-drawer-header">
        <span className="lock-drawer-title">
          {isNode ? `TRX ${item.trx_id}` : `${t("locks.detail_lock_info")}`}
        </span>
        <button className="lock-drawer-close" onClick={onClose}>✕</button>
      </div>
      <div className="lock-drawer-body">
        {isNode ? (
          <>
            <div className="lock-drawer-row">
              <span className="lock-drawer-key">Thread ID</span>
              <span className="lock-drawer-val">{item.thread_id}</span>
            </div>
            <div className="lock-drawer-row">
              <span className="lock-drawer-key">Type</span>
              <span className={`lock-badge lock-badge--${item.type}`}>{item.type}</span>
            </div>
            {item.query && (
              <div className="lock-drawer-section">
                <div className="lock-drawer-key">{t("locks.detail_waiting_query")}</div>
                <pre className="lock-drawer-sql">{item.query}</pre>
              </div>
            )}
          </>
        ) : (
          <>
            <div className="lock-drawer-row">
              <span className="lock-drawer-key">{t("locks.col_time")}</span>
              <span className="lock-drawer-val">{new Date(item.ts * 1000).toLocaleString()}</span>
            </div>
            <div className="lock-drawer-row">
              <span className="lock-drawer-key">Lock Mode</span>
              <span className="lock-drawer-val">{item.lock_mode} / {item.lock_type}</span>
            </div>
            <div className="lock-drawer-row">
              <span className="lock-drawer-key">Object</span>
              <span className="lock-drawer-val">
                {item.lock_object_schema}.{item.lock_object_table}
                {item.lock_index ? ` (${item.lock_index})` : ""}
              </span>
            </div>
            {item.waiting_query && (
              <div className="lock-drawer-section">
                <div className="lock-drawer-key">{t("locks.detail_waiting_query")}</div>
                <pre className="lock-drawer-sql">{item.waiting_query}</pre>
              </div>
            )}
            {item.blocking_query && (
              <div className="lock-drawer-section">
                <div className="lock-drawer-key">{t("locks.detail_blocking_query")}</div>
                <pre className="lock-drawer-sql">{item.blocking_query}</pre>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ─── main page ────────────────────────────────────────────────────────────────

export default function LockPage() {
  const { t } = useTranslation();
  const [instances, setInstances] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [tab, setTab] = useState("realtime");
  const [autoRefresh, setAutoRefresh] = useState(true);

  // realtime
  const [topology, setTopology] = useState(null);
  const [topoLoading, setTopoLoading] = useState(false);
  const [topoError, setTopoError] = useState("");

  // history
  const [histRows, setHistRows] = useState([]);
  const [histLoading, setHistLoading] = useState(false);
  const [histHours, setHistHours] = useState(1);
  const [deadlockOnly, setDeadlockOnly] = useState(false);

  const [selectedItem, setSelectedItem] = useState(null);

  // load instances
  useEffect(() => {
    api.get("/collector/instances/").then(res => {
      const list = res.data?.results || res.data || [];
      const active = list.filter(i => i.is_active);
      setInstances(active);
      const first = active.find(i => i.db_type === "mysql") || active[0];
      if (first) setSelectedId(String(first.id));
    });
  }, []);

  const fetchTopology = useCallback(() => {
    if (!selectedId) return;
    setTopoLoading(true);
    setTopoError("");
    api.get(`/locks/topology/?instance_id=${selectedId}`)
      .then(res => setTopology(res.data))
      .catch(e => setTopoError(e.response?.data?.error || t("locks.load_failed")))
      .finally(() => setTopoLoading(false));
  }, [selectedId, t]);

  const fetchHistory = useCallback(() => {
    if (!selectedId) return;
    setHistLoading(true);
    api.get(`/locks/history/?instance_id=${selectedId}&hours=${histHours}&deadlock_only=${deadlockOnly}`)
      .then(res => setHistRows(res.data.rows || []))
      .catch(() => setHistRows([]))
      .finally(() => setHistLoading(false));
  }, [selectedId, histHours, deadlockOnly]);

  // initial fetch + auto-refresh for realtime tab
  useEffect(() => {
    if (!selectedId) return;
    if (tab === "realtime") {
      fetchTopology();
      if (!autoRefresh) return;
      const id = setInterval(fetchTopology, 5000);
      return () => clearInterval(id);
    }
  }, [selectedId, tab, autoRefresh, fetchTopology]);

  useEffect(() => {
    if (tab === "history") fetchHistory();
  }, [tab, fetchHistory]);

  const hasLocks = topology && topology.nodes.length > 0;
  const hasDeadlock = topology?.has_deadlock;

  return (
    <AppLayout title={t("locks.title")}>
      <div className="lock-page">
        {/* ── filter bar ── */}
        <div className="lock-filter-bar">
          <div className="lock-filter-group">
            <label className="lock-filter-label">{t("locks.filter_instance")}</label>
            <select
              className="lock-select"
              value={selectedId}
              onChange={e => { setSelectedId(e.target.value); setSelectedItem(null); }}
            >
              {instances.length === 0 && (
                <option value="">{t("locks.no_instance")}</option>
              )}
              {instances.map(i => (
                <option key={i.id} value={i.id}>{i.name}</option>
              ))}
            </select>
          </div>

          <div className="lock-tabs">
            <button
              className={`lock-tab-btn ${tab === "realtime" ? "lock-tab-btn--active" : ""}`}
              onClick={() => setTab("realtime")}
            >
              {t("locks.tab_realtime")}
            </button>
            <button
              className={`lock-tab-btn ${tab === "history" ? "lock-tab-btn--active" : ""}`}
              onClick={() => setTab("history")}
            >
              {t("locks.tab_history")}
            </button>
          </div>

          {tab === "realtime" && (
            <label className="lock-toggle-label">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={e => setAutoRefresh(e.target.checked)}
              />
              <span>{t("locks.auto_refresh")}</span>
            </label>
          )}

          {tab === "history" && (
            <>
              <select
                className="lock-select lock-select--sm"
                value={histHours}
                onChange={e => setHistHours(Number(e.target.value))}
              >
                {[1, 3, 6, 12, 24].map(h => (
                  <option key={h} value={h}>{t("locks.history_hours", { h })}</option>
                ))}
              </select>
              <label className="lock-toggle-label">
                <input
                  type="checkbox"
                  checked={deadlockOnly}
                  onChange={e => setDeadlockOnly(e.target.checked)}
                />
                <span>{t("locks.deadlock_only")}</span>
              </label>
            </>
          )}

          <button className="lock-refresh-btn" onClick={tab === "realtime" ? fetchTopology : fetchHistory}>
            <span className="material-symbols-outlined" style={{ fontSize: 18 }}>refresh</span>
            {t("locks.refresh")}
          </button>
        </div>

        {/* ── content ── */}
        <div className={`lock-content ${selectedItem ? "lock-content--split" : ""}`}>
          <div className="lock-main">
            {tab === "realtime" && (
              <div className="lock-card">
                <div className="lock-card-header">
                  <span className="lock-card-title">{t("locks.topology_title")}</span>
                  {topology && (
                    <span className={`lock-status-badge ${hasDeadlock ? "lock-status-badge--danger" : hasLocks ? "lock-status-badge--warn" : "lock-status-badge--ok"}`}>
                      {hasDeadlock ? t("locks.has_deadlock") : t("locks.no_deadlock")}
                    </span>
                  )}
                </div>

                {topoLoading && !topology && (
                  <div className="lock-loading">{t("common.loading")}</div>
                )}
                {topoError && <div className="lock-error">{topoError}</div>}

                {!topoLoading && topology && !hasLocks && (
                  <div className="lock-empty-state">
                    <span className="material-symbols-outlined lock-empty-icon">lock_open</span>
                    <p className="lock-empty-title">{t("locks.no_locks")}</p>
                    <p className="lock-empty-desc">{t("locks.no_locks_desc")}</p>
                  </div>
                )}

                {hasLocks && (
                  <>
                    <LockGraph
                      nodes={topology.nodes}
                      edges={topology.edges}
                      onNodeClick={setSelectedItem}
                    />
                    <Legend t={t} />
                  </>
                )}
              </div>
            )}

            {tab === "history" && (
              <div className="lock-card">
                <div className="lock-card-header">
                  <span className="lock-card-title">{t("locks.history_title")}</span>
                </div>
                {histLoading
                  ? <div className="lock-loading">{t("common.loading")}</div>
                  : <HistoryTable rows={histRows} onRowClick={setSelectedItem} />
                }
              </div>
            )}
          </div>

          {selectedItem && (
            <DetailDrawer item={selectedItem} onClose={() => setSelectedItem(null)} />
          )}
        </div>
      </div>
    </AppLayout>
  );
}

function Legend({ t }) {
  const items = [
    { type: "blocker",  label: t("locks.node_blocker") },
    { type: "waiter",   label: t("locks.node_waiter") },
    { type: "both",     label: t("locks.node_both") },
    { type: "deadlock", label: t("locks.node_deadlock") },
  ];
  return (
    <div className="lock-legend">
      <span className="lock-legend-title">{t("locks.legend")}</span>
      {items.map(({ type, label }) => (
        <span key={type} className="lock-legend-item">
          <svg width="14" height="14" viewBox="0 0 14 14">
            <circle cx="7" cy="7" r="6"
              fill={NODE_COLORS[type].fill}
              stroke={NODE_COLORS[type].stroke}
              strokeWidth="1.5"
            />
          </svg>
          {label}
        </span>
      ))}
    </div>
  );
}
