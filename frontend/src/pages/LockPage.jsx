import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import AppLayout from "../components/AppLayout";
import api from "../services/api";
import useForceLayout, { NODE_COLORS } from "../hooks/useForceLayout";
import "./LockPage.css";

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
            onClick={() => onNodeClick?.(node)}
            style={{ cursor: onNodeClick ? "pointer" : "default" }}
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

function DetailDrawer({ item, onClose, snapshotTopo, snapshotLoading }) {
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

            {/* snapshot topology */}
            {snapshotLoading ? (
              <div className="lock-loading" style={{ padding: 16 }}>{t("common.loading")}</div>
            ) : snapshotTopo && snapshotTopo.nodes?.length > 0 ? (
              <div className="lock-drawer-section">
                <div className="lock-drawer-key">{t("locks.topology_title")}</div>
                <LockGraph
                  nodes={snapshotTopo.nodes}
                  edges={snapshotTopo.edges}
                />
              </div>
            ) : null}

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
  const [histError, setHistError] = useState("");
  const [histHours, setHistHours] = useState(1);
  const [deadlockOnly, setDeadlockOnly] = useState(false);

  const [selectedItem, setSelectedItem] = useState(null);
  const [snapshotTopo, setSnapshotTopo] = useState(null);
  const [snapshotLoading, setSnapshotLoading] = useState(false);

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
    setHistError("");
    api.get(`/locks/history/?instance_id=${selectedId}&hours=${histHours}&deadlock_only=${deadlockOnly}`)
      .then(res => setHistRows(res.data.rows || []))
      .catch(err => { setHistRows([]); setHistError(err.response?.data?.error || err.message); })
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

  // fetch snapshot topology when a history row is selected
  useEffect(() => {
    if (!selectedItem || selectedItem.type) { setSnapshotTopo(null); return; }
    // history row — has ts (unix timestamp) but no type
    const inst = instances.find(i => String(i.id) === selectedId);
    if (!inst || !selectedItem.ts) return;
    setSnapshotLoading(true);
    api.get(`/locks/history-snapshot/?service_name=${encodeURIComponent(inst.name)}&ts=${selectedItem.ts}`)
      .then(res => setSnapshotTopo(res.data))
      .catch(() => setSnapshotTopo(null))
      .finally(() => setSnapshotLoading(false));
  }, [selectedItem, selectedId, instances]);

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
                  <Legend t={t} />
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
                  <LockGraph
                    nodes={topology.nodes}
                    edges={topology.edges}
                    onNodeClick={setSelectedItem}
                  />
                )}
              </div>
            )}

            {tab === "history" && (
              <div className="lock-card">
                <div className="lock-card-header">
                  <span className="lock-card-title">{t("locks.history_title")}</span>
                </div>
                {histError
                  ? <div className="lock-error">{histError}</div>
                  : histLoading
                    ? <div className="lock-loading">{t("common.loading")}</div>
                    : <HistoryTable rows={histRows} onRowClick={setSelectedItem} />
                }
              </div>
            )}
          </div>

          {selectedItem && (
            <DetailDrawer item={selectedItem} onClose={() => setSelectedItem(null)} snapshotTopo={snapshotTopo} snapshotLoading={snapshotLoading} />
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
