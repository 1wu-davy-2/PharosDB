import { useEffect, useState, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import api from "../services/api";
import AppLayout from "../components/AppLayout";
import PlanDiffTable from "../components/PlanDiffTable";
import "./QANPage.css";

const DRAWER_TABS = [
  { key: "overview", i18n: "qan.tab_overview" },
  { key: "trend", i18n: "qan.tab_trend" },
  { key: "plan", i18n: "qan.tab_plan" },
  { key: "suggestions", i18n: "qan.tab_suggestions" },
];

const TREND_METRICS = [
  { key: "num_queries", i18n: "qan.trend_num_queries" },
  { key: "total_query_time", i18n: "qan.trend_total_time" },
  { key: "avg_query_time", i18n: "qan.trend_avg_time" },
  { key: "max_query_time", i18n: "qan.trend_max_time" },
  { key: "total_rows_examined", i18n: "qan.trend_rows" },
];

/* ── EXPLAIN JSON 树节点组件 ─────────────────────── */
function PlanNode({ label, data, depth, path, highlightPaths, diffMap }) {
  const [open, setOpen] = useState(depth < 2);
  const currentPath = path || "$";

  if (data == null) return null;

  const isArray = Array.isArray(data);
  const isObject = data && typeof data === "object" && !isArray;
  const changeType = diffMap?.get(currentPath);
  const isHighlighted = changeType || highlightPaths?.has(currentPath);
  const highlightCls = changeType
    ? `plan-node--diff-${changeType}`
    : isHighlighted ? "plan-node--diff-highlight" : "";

  if (isObject) {
    const entries = Object.entries(data);
    return (
      <div className={`plan-node ${highlightCls}`} style={{ marginLeft: depth * 16 }}>
        {label && (
          <button className="plan-node-toggle" onClick={() => setOpen(!open)}>
            <span className={`plan-node-arrow ${open ? "plan-node-arrow--open" : ""}`}>&#9654;</span>
            <span className="plan-node-key">{label}</span>
          </button>
        )}
        {(!label || open) && (
          <div className="plan-node-children">
            {entries.map(([k, v]) => (
              <PlanNode
                key={k} label={k} data={v}
                depth={depth + (label ? 1 : 0)}
                path={`${currentPath}.${k}`}
                highlightPaths={highlightPaths}
                diffMap={diffMap}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  if (isArray) {
    return (
      <div className={`plan-node ${highlightCls}`} style={{ marginLeft: depth * 16 }}>
        <button className="plan-node-toggle" onClick={() => setOpen(!open)}>
          <span className={`plan-node-arrow ${open ? "plan-node-arrow--open" : ""}`}>&#9654;</span>
          <span className="plan-node-key plan-node-key--array">{label} [{data.length}]</span>
        </button>
        {(!label || open) && (
          <div className="plan-node-children">
            {data.map((item, i) => (
              <PlanNode
                key={i} label={`[${i}]`} data={item}
                depth={depth + (label ? 1 : 0) + 1}
                path={`${currentPath}[${i}]`}
                highlightPaths={highlightPaths}
                diffMap={diffMap}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  const cls =
    data === true || data === false ? "plan-node-val--bool" :
    typeof data === "number" ? "plan-node-val--num" :
    "plan-node-val--str";

  return (
    <div className={`plan-node plan-node--leaf ${highlightCls}`} style={{ marginLeft: depth * 16 }}>
      <span className="plan-node-key">{label}</span>
      <span className="plan-node-sep"> = </span>
      <span className={`plan-node-val ${cls}`}>{String(data)}</span>
    </div>
  );
}

/* ── 优化建议规则引擎 ────────────────────────────── */
function buildSuggestions(detail, fmtNum, fmtTime, t) {
  const items = [];
  const checks = [
    { cond: detail.no_index_used_count > 0,  sev: "warning", key: "qan.suggest_no_index",       count: detail.no_index_used_count },
    { cond: detail.full_scan_count > 0,       sev: "warning", key: "qan.suggest_full_scan",       count: detail.full_scan_count },
    { cond: detail.filesort_count > 0,        sev: "info",    key: "qan.suggest_filesort",        count: detail.filesort_count },
    { cond: detail.total_tmp_disk_tables > 0, sev: "warning", key: "qan.suggest_tmp_disk",        count: detail.total_tmp_disk_tables },
    { cond: detail.full_join_count > 0,       sev: "info",    key: "qan.suggest_full_join",       count: detail.full_join_count },
    { cond: detail.no_good_index_used_count > 0, sev: "info", key: "qan.suggest_no_good_index",  count: detail.no_good_index_used_count },
  ];
  for (const c of checks) {
    if (c.cond) items.push({ severity: c.sev, text: t(c.key, { count: fmtNum(c.count) }) });
  }
  if (detail.avg_query_time > 1) {
    items.push({ severity: "warning", text: t("qan.suggest_high_avg_time", { time: fmtTime(detail.avg_query_time) }) });
  }
  return items;
}

/* ── 从 plan_summary 提取关键信息 ──────────────────── */
function extractPlanSummary(summary) {
  try {
    const obj = typeof summary === "string" ? JSON.parse(summary) : summary;
    const table = obj?.query_block?.table || obj?.query_block?.nested_loop?.[0]?.table || {};
    return { access_type: table.access_type || "-", key: table.key || "-" };
  } catch { return { access_type: "?", key: "?" }; }
}

export default function QANPage() {
  const { t } = useTranslation();

  const PERIODS = [
    { value: "1h", label: t("qan.period_1h") },
    { value: "6h", label: t("qan.period_6h") },
    { value: "24h", label: t("qan.period_24h") },
    { value: "7d", label: t("qan.period_7d") },
  ];

  const SORT_OPTIONS = [
    { value: "m_query_time_sum", label: t("qan.sort_total_time") },
    { value: "num_queries", label: t("qan.sort_count") },
    { value: "m_rows_examined_sum", label: t("qan.sort_rows") },
    { value: "m_lock_time_sum", label: t("qan.sort_lock") },
    { value: "m_no_index_used_sum", label: t("qan.sort_no_index") },
  ];

  const LIMIT_OPTIONS = [10, 20, 50, 100];

  const [services, setServices] = useState([]);
  const [selectedService, setSelectedService] = useState("");
  const [period, setPeriod] = useState("1h");
  const [sortBy, setSortBy] = useState("m_query_time_sum");
  const [sortDir, setSortDir] = useState("DESC");
  const [limit, setLimit] = useState(20);
  const [searchText, setSearchText] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [schemaFilter, setSchemaFilter] = useState("");
  const [queries, setQueries] = useState([]);
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(false);

  // drawer
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTab, setDrawerTab] = useState("overview");
  const [detailQuery, setDetailQuery] = useState(null);
  const [detail, setDetail] = useState(null);
  const [trend, setTrend] = useState([]);
  const [trendMetric, setTrendMetric] = useState("num_queries");
  const [detailLoading, setDetailLoading] = useState(false);

  // plan tab
  const [plans, setPlans] = useState([]);
  const [planLoading, setPlanLoading] = useState(false);
  const [planMode, setPlanMode] = useState("view");
  const [selectedPlanId, setSelectedPlanId] = useState(null);
  const [compareA, setCompareA] = useState("");
  const [compareB, setCompareB] = useState("");
  const [compareResult, setCompareResult] = useState(null);
  const [compareLoading, setCompareLoading] = useState(false);
  const [planDetailCache, setPlanDetailCache] = useState({});

  // manual explain
  const [explainSql, setExplainSql] = useState("");
  const [explainLoading, setExplainLoading] = useState(false);
  const [explainResult, setExplainResult] = useState(null);
  const [explainError, setExplainError] = useState("");
  const [showExplainForm, setShowExplainForm] = useState(false);

  const planTimerRef = useRef(null);

  useEffect(() => {
    api.get("/qan/top-queries/")
      .then(({ data }) => {
        setServices(data.services || []);
        if (data.services?.length > 0) setSelectedService(data.services[0]);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedService) return;
    setLoading(true);

    const params = new URLSearchParams({
      service: selectedService,
      period,
      sort: sortBy,
      limit: String(limit),
      order: sortDir,
    });
    if (searchText) params.set("search", searchText);
    if (schemaFilter) params.set("schema", schemaFilter);

    Promise.all([
      api.get(`/qan/top-queries/?${params}`),
      api.get(`/qan/overview/?service=${selectedService}&period=${period}`),
    ])
      .then(([qRes, oRes]) => {
        setQueries(qRes.data.queries || []);
        setOverview(oRes.data.overview || {});
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [selectedService, period, sortBy, sortDir, limit, searchText, schemaFilter]);

  const handleSearch = useCallback(() => {
    setSearchText(searchInput);
  }, [searchInput]);

  const handleSearchKey = useCallback((e) => {
    if (e.key === "Enter") setSearchText(searchInput);
    if (e.key === "Escape") { setSearchInput(""); setSearchText(""); }
  }, [searchInput]);

  const schemas = [...new Set(queries.map((q) => q.schema).filter(Boolean))];

  const loadDetail = async (queryid) => {
    setDetailQuery(queryid);
    setDrawerOpen(true);
    setDrawerTab("overview");
    setDetail(null);
    setTrend([]);
    setPlans([]);
    setPlanDetailCache({});
    setSelectedPlanId(null);
    setCompareResult(null);
    setExplainResult(null);
    setShowExplainForm(false);
    setDetailLoading(true);
    try {
      const [dRes, tRes] = await Promise.all([
        api.get(`/qan/query/${queryid}/?service=${selectedService}&period=${period}`),
        api.get(`/qan/query/${queryid}/trend/?service=${selectedService}&hours=24`),
      ]);
      setDetail(dRes.data);
      setTrend(tRes.data.trend || []);
    } catch {} finally {
      setDetailLoading(false);
    }
  };

  const loadPlans = async (fingerprint) => {
    setPlanLoading(true);
    try {
      const { data } = await api.get(`/qan/plans/?fingerprint=${encodeURIComponent(fingerprint)}&service=${selectedService}`);
      const list = data.plans || [];
      setPlans(list);
      if (list.length > 0) {
        setSelectedPlanId(list[0].plan_id);
        fetchPlanDetail(list[0].plan_id);
      }
    } catch { setPlans([]); } finally {
      setPlanLoading(false);
    }
  };

  const fetchPlanDetail = async (planId) => {
    if (!planId) return;
    if (planDetailCache[planId]) {
      setSelectedPlanId(planId);
      return;
    }
    try {
      const { data } = await api.get(`/qan/plans/${planId}/`);
      setPlanDetailCache((c) => ({ ...c, [planId]: data }));
      setSelectedPlanId(planId);
    } catch {}
  };

  const handleCompare = async () => {
    if (!compareA || !compareB) return;
    setCompareLoading(true);
    try {
      const { data } = await api.get(`/qan/plans/compare/?a=${compareA}&b=${compareB}`);
      setCompareResult(data);
    } catch {} finally {
      setCompareLoading(false);
    }
  };

  const handleManualExplain = async () => {
    if (!detail) return;
    setExplainLoading(true);
    setExplainError("");
    setExplainResult(null);
    try {
      const { data } = await api.post("/qan/explain/", {
        service: selectedService,
        sql: explainSql || detail.example,
      });
      setExplainResult(data);
      planTimerRef.current = setTimeout(() => {
        loadPlans(detail.fingerprint);
      }, 1500);
    } catch (e) {
      setExplainError(e.response?.data?.error || t("qan.plan_collect_failed"));
    } finally {
      setExplainLoading(false);
    }
  };

  const closeDrawer = () => {
    setDrawerOpen(false);
    if (planTimerRef.current) clearTimeout(planTimerRef.current);
    setTimeout(() => {
      setDetailQuery(null); setDetail(null); setPlans([]);
      setPlanDetailCache({}); setSelectedPlanId(null);
      setCompareResult(null); setExplainResult(null);
    }, 300);
  };

  const fmtTime = (seconds) => {
    if (seconds == null) return "-";
    if (seconds < 0.001) return `${(seconds * 1e6).toFixed(0)}μs`;
    if (seconds < 1) return `${(seconds * 1000).toFixed(1)}ms`;
    return `${seconds.toFixed(2)}s`;
  };

  const fmtNum = (n) => {
    if (n == null) return "-";
    if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
    if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
    return String(n);
  };

  const noIndexPct = overview && overview.total_queries > 0
    ? ((overview.no_index_queries / overview.total_queries) * 100).toFixed(1)
    : null;

  const suggestions = detail ? buildSuggestions(detail, fmtNum, fmtTime, t) : [];
  const trendData = TREND_METRICS.find((m) => m.key === trendMetric) || TREND_METRICS[1];
  const trendMax = Math.max(...trend.map((x) => x[trendMetric] || 0), 0);

  // plan computed values
  const viewedPlan = selectedPlanId ? (planDetailCache[selectedPlanId] || plans.find((p) => p.plan_id === selectedPlanId)) : null;
  const diffPaths = compareResult?.diff ? new Set(compareResult.diff.map((d) => d.path)) : null;
  const diffMap = compareResult?.diff
    ? new Map(compareResult.diff.map((d) => [d.path, d.change]))
    : null;

  return (
    <AppLayout title={t("qan.title")}>
      {/* 筛选栏 */}
      <div className="card qan-filters">
        <div className="qan-filter-group">
          <label className="qan-filter-label">{t("qan.filter_service")}</label>
          <select className="form-select qan-filter-select" value={selectedService} onChange={(e) => setSelectedService(e.target.value)}>
            {services.length === 0 && <option>{t("qan.no_service")}</option>}
            {services.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        <div className="qan-filter-group">
          <label className="qan-filter-label">{t("qan.filter_period")}</label>
          <div className="qan-period-tabs">
            {PERIODS.map((p) => (
              <button key={p.value} className={`qan-period-tab ${period === p.value ? "qan-period-tab--active" : ""}`} onClick={() => setPeriod(p.value)}>
                {p.label}
              </button>
            ))}
          </div>
        </div>

        <div className="qan-filter-group">
          <label className="qan-filter-label">{t("qan.filter_sort")}</label>
          <div style={{ display: "flex", gap: 4 }}>
            <select className="form-select qan-filter-select" value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
              {SORT_OPTIONS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
            <button className="qan-sort-dir-btn" onClick={() => setSortDir((d) => d === "DESC" ? "ASC" : "DESC")} title={sortDir === "DESC" ? "↓ DESC" : "↑ ASC"}>
              <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
                {sortDir === "DESC" ? "arrow_downward" : "arrow_upward"}
              </span>
            </button>
          </div>
        </div>

        <div className="qan-filter-group">
          <label className="qan-filter-label">{t("qan.filter_limit")}</label>
          <select className="form-select qan-filter-select qan-filter-narrow" value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
            {LIMIT_OPTIONS.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>

        <div className="qan-filter-group qan-filter-grow">
          <label className="qan-filter-label">{t("qan.filter_search")}</label>
          <div className="qan-search-wrap">
            <span className="material-symbols-outlined qan-search-icon">search</span>
            <input
              className="form-input qan-search-input"
              placeholder={t("qan.search_placeholder")}
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={handleSearchKey}
            />
            {searchInput && (
              <button className="qan-search-clear" onClick={() => { setSearchInput(""); setSearchText(""); }}>
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>close</span>
              </button>
            )}
          </div>
        </div>

        {schemas.length > 0 && (
          <div className="qan-filter-group">
            <label className="qan-filter-label">{t("qan.filter_schema")}</label>
            <select className="form-select qan-filter-select" value={schemaFilter} onChange={(e) => setSchemaFilter(e.target.value)}>
              <option value="">{t("common.all")}</option>
              {schemas.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        )}
      </div>

      {searchText && (
        <div className="qan-search-hint">
          {t("qan.search_hint", { text: searchText })}
          <button className="qan-search-hint-clear" onClick={() => { setSearchInput(""); setSearchText(""); }}>{t("qan.search_clear")}</button>
        </div>
      )}

      {overview && (
        <div className="qan-overview-row">
          <div className="stat-card">
            <div className="stat-card-header"><span className="stat-card-label">{t("qan.unique_queries")}</span></div>
            <div className="stat-card-body"><span className="stat-card-value">{fmtNum(overview.unique_queries)}</span></div>
          </div>
          <div className="stat-card">
            <div className="stat-card-header"><span className="stat-card-label">{t("qan.total_queries")}</span></div>
            <div className="stat-card-body"><span className="stat-card-value">{fmtNum(overview.total_queries)}</span></div>
          </div>
          <div className="stat-card">
            <div className="stat-card-header"><span className="stat-card-label">{t("qan.avg_latency")}</span></div>
            <div className="stat-card-body"><span className="stat-card-value">{fmtTime(overview.avg_query_time)}</span></div>
          </div>
          <div className="stat-card">
            <div className="stat-card-header"><span className="stat-card-label">{t("qan.no_index_queries")}</span></div>
            <div className="stat-card-body">
              <span className="stat-card-value" style={{ color: overview.no_index_queries > 0 ? "var(--color-error-alt)" : undefined }}>
                {fmtNum(overview.no_index_queries)}
              </span>
              {noIndexPct && (
                <span className="stat-card-pct">{noIndexPct}%</span>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="card" style={{ overflow: "hidden" }}>
        <div className="card-header">
          <h2 className="card-title">{t("qan.top_slow")}</h2>
          <span className="qan-result-count">{t("qan.result_count", { count: queries.length })}</span>
        </div>
        {loading ? (
          <div className="loading-wrap"><div className="mini-spinner" /> {t("common.loading")}</div>
        ) : queries.length === 0 ? (
          <div className="empty-state">
            <span className="material-symbols-outlined empty-state-icon">query_stats</span>
            <div className="empty-state-title">{t("qan.no_data")}</div>
            <div className="empty-state-desc">{searchText ? t("qan.no_data_search") : t("qan.no_data_hint")}</div>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="sql-table">
              <thead>
                <tr>
                  <th style={{ width: 40 }}>#</th>
                  <th>{t("qan.col_fingerprint")}</th>
                  <th className="text-right">{t("qan.col_total_time")}</th>
                  <th className="text-right">{t("qan.col_avg_time")}</th>
                  <th className="text-right">{t("qan.col_count")}</th>
                  <th className="text-right">{t("qan.col_rows")}</th>
                  <th className="text-right">{t("qan.col_lock")}</th>
                  <th className="text-right">{t("qan.col_no_index")}</th>
                </tr>
              </thead>
              <tbody>
                {queries.map((q, i) => (
                  <tr key={q.queryid} className={`qan-row ${detailQuery === q.queryid ? "qan-row--active" : ""}`} onClick={() => loadDetail(q.queryid)}>
                    <td className="text-muted">{i + 1}</td>
                    <td>
                      <div className="qan-fingerprint">
                        <span className="qan-fingerprint-text">
                          {q.fingerprint?.substring(0, 80)}{q.fingerprint?.length > 80 ? "..." : ""}
                        </span>
                        {q.fingerprint?.length > 80 && (
                          <span className="qan-fingerprint-full">{q.fingerprint}</span>
                        )}
                      </div>
                      {q.schema && <span className="qan-schema">{q.schema}</span>}
                    </td>
                    <td className="text-right font-medium" style={{ color: i === 0 ? "var(--color-error-alt)" : i < 3 ? "#f59e0b" : undefined }}>
                      {fmtTime(q.total_query_time)}
                    </td>
                    <td className="text-right">{fmtTime(q.avg_query_time)}</td>
                    <td className="text-right">{fmtNum(q.num_queries)}</td>
                    <td className="text-right">{fmtNum(q.total_rows_examined)}</td>
                    <td className="text-right">{fmtTime(q.total_lock_time)}</td>
                    <td className="text-right" style={{ color: q.no_index_used_count > 0 ? "var(--color-error-alt)" : undefined }}>
                      {fmtNum(q.no_index_used_count)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ═══════════════════ Drawer ═══════════════════ */}
      {drawerOpen && <div className="qan-drawer-overlay" onClick={closeDrawer} />}
      <div className={`qan-drawer ${drawerOpen ? "qan-drawer--open" : ""}`}>
        <div className="qan-drawer-header">
          <h2 className="qan-drawer-title">{t("qan.drawer_title")}</h2>
          <button className="qan-drawer-close" onClick={closeDrawer}>
            <span className="material-symbols-outlined" style={{ fontSize: 22 }}>close</span>
          </button>
        </div>

        {/* Tab bar */}
        <div className="qan-drawer-tabs">
          {DRAWER_TABS.map((tab) => (
            <button
              key={tab.key}
              className={`qan-drawer-tab ${drawerTab === tab.key ? "qan-drawer-tab--active" : ""}`}
              onClick={() => {
                setDrawerTab(tab.key);
                if (tab.key === "plan" && detail && plans.length === 0) loadPlans(detail.fingerprint);
              }}
            >
              {t(tab.i18n)}
            </button>
          ))}
        </div>

        <div className="qan-drawer-body">
          {detailLoading ? (
            <div className="loading-wrap"><div className="mini-spinner" /> {t("common.loading")}</div>
          ) : detail ? (
            <>
              {/* Tab: 概览 */}
              {drawerTab === "overview" && (
                <>
                  <div className="qan-detail-section">
                    <div className="qan-detail-label">{t("qan.detail_fingerprint")}</div>
                    <pre className="qan-sql-block">{detail.fingerprint}</pre>
                  </div>
                  {detail.example && (
                    <div className="qan-detail-section">
                      <div className="qan-detail-label">{t("qan.detail_example")}</div>
                      <pre className="qan-sql-block">{detail.example}</pre>
                    </div>
                  )}
                  <div className="qan-detail-grid">
                    {[
                      [t("qan.metric_count"), fmtNum(detail.num_queries)],
                      [t("qan.metric_total_time"), fmtTime(detail.total_query_time)],
                      [t("qan.metric_avg_time"), fmtTime(detail.avg_query_time)],
                      [t("qan.metric_max_time"), fmtTime(detail.max_query_time)],
                      [t("qan.metric_rows_sent"), fmtNum(detail.total_rows_sent)],
                      [t("qan.metric_rows_examined"), fmtNum(detail.total_rows_examined)],
                      [t("qan.metric_lock_time"), fmtTime(detail.total_lock_time)],
                      [t("qan.metric_tmp_tables"), fmtNum(detail.total_tmp_tables)],
                      [t("qan.metric_full_scan"), fmtNum(detail.full_scan_count), detail.full_scan_count > 0],
                      [t("qan.metric_no_index"), fmtNum(detail.no_index_used_count), detail.no_index_used_count > 0],
                      [t("qan.metric_filesort"), fmtNum(detail.filesort_count)],
                      [t("qan.metric_bytes_sent"), fmtNum(detail.total_bytes_sent)],
                    ].map(([label, value, warn]) => (
                      <div key={label} className="qan-metric">
                        <span className="qan-metric-label">{label}</span>
                        <span className="qan-metric-value" style={{ color: warn ? "var(--color-error-alt)" : undefined }}>{value}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}

              {/* Tab: 趋势 */}
              {drawerTab === "trend" && (
                <>
                  <div className="qan-detail-section">
                    <div className="qan-detail-label">{t("qan.trend_metric")}</div>
                    <div className="qan-trend-metric-tabs">
                      {TREND_METRICS.map((m) => (
                        <button
                          key={m.key}
                          className={`qan-period-tab ${trendMetric === m.key ? "qan-period-tab--active" : ""}`}
                          onClick={() => setTrendMetric(m.key)}
                        >
                          {t(m.i18n)}
                        </button>
                      ))}
                    </div>
                  </div>
                  {trend.length > 0 ? (
                    <div className="qan-detail-section">
                      <div className="qan-detail-label">{t("qan.trend_title")} — {t(trendData.i18n)}</div>
                      <div className="qan-trend-chart">
                        {trend.map((tItem, i) => {
                          const height = trendMax > 0 ? (tItem[trendMetric] || 0) / trendMax * 100 : 0;
                          const tipVal = trendMetric.includes("time") ? fmtTime(tItem[trendMetric]) : fmtNum(tItem[trendMetric]);
                          return (
                            <div key={i} className="qan-trend-bar-wrap">
                              <div className="qan-trend-bar" style={{ height: `${Math.max(height, 2)}%` }} title={`${t(trendData.i18n)}: ${tipVal}`} />
                              <span className="qan-trend-label">{new Date(tItem.hour).getHours()}:00</span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ) : (
                    <div className="empty-state" style={{ padding: 24 }}>
                      <span className="material-symbols-outlined empty-state-icon">show_chart</span>
                      <div className="empty-state-title">{t("qan.no_data")}</div>
                      <div className="empty-state-desc">{t("qan.no_data_hint")}</div>
                    </div>
                  )}
                </>
              )}

              {/* Tab: 执行计划 */}
              {drawerTab === "plan" && (
                <>
                  {/* Mode bar */}
                  <div className="qan-plan-mode-bar">
                    <button
                      className={`qan-plan-mode-btn ${planMode === "view" ? "qan-plan-mode-btn--active" : ""}`}
                      onClick={() => { setPlanMode("view"); setCompareResult(null); }}
                    >
                      {t("qan.plan_mode_view")}
                    </button>
                    <button
                      className={`qan-plan-mode-btn ${planMode === "compare" ? "qan-plan-mode-btn--active" : ""}`}
                      onClick={() => setPlanMode("compare")}
                      disabled={plans.length < 2}
                    >
                      {t("qan.plan_mode_compare")}
                    </button>
                    <div className="qan-plan-mode-spacer" />
                    <button
                      className="qan-plan-mode-btn"
                      onClick={() => { setShowExplainForm((v) => !v); setExplainResult(null); setExplainError(""); }}
                    >
                      {t("qan.plan_manual_collect")}
                    </button>
                  </div>

                  {planLoading ? (
                    <div className="loading-wrap"><div className="mini-spinner" /> {t("common.loading")}</div>
                  ) : plans.length === 0 ? (
                    <div className="empty-state" style={{ padding: 24 }}>
                      <span className="material-symbols-outlined empty-state-icon">account_tree</span>
                      <div className="empty-state-title">{t("qan.no_plan")}</div>
                      <div className="empty-state-desc">{t("qan.no_plan_desc")}</div>
                    </div>
                  ) : (
                    <>
                      {/* Manual collect form */}
                      {showExplainForm && (
                        <div className="qan-plan-collect-section">
                          <div className="qan-detail-label">{t("qan.plan_collect_title")}</div>
                          <textarea
                            className="qan-plan-collect-sql"
                            value={explainSql || detail?.example || ""}
                            onChange={(e) => setExplainSql(e.target.value)}
                            placeholder="SELECT ..."
                          />
                          <div className="qan-plan-collect-actions">
                            <button
                              className="qan-plan-collect-submit"
                              onClick={handleManualExplain}
                              disabled={explainLoading}
                            >
                              {explainLoading ? t("common.loading") : t("qan.plan_collect_btn")}
                            </button>
                          </div>
                          {explainError && <div className="lock-error" style={{ marginTop: 8 }}>{explainError}</div>}
                          {explainResult && (
                            <div className="qan-detail-section" style={{ marginTop: 12 }}>
                              <div className="qan-detail-label" style={{ color: "var(--color-success)" }}>{t("qan.plan_collect_success")}</div>
                              <div className="qan-plan-tree">
                                <PlanNode data={explainResult.plan_json} depth={0} />
                              </div>
                            </div>
                          )}
                        </div>
                      )}

                      {/* View mode */}
                      {planMode === "view" && (
                        <div className="qan-detail-section">
                          <div className="qan-detail-label">{t("qan.plan_version_count", { count: plans.length })}</div>
                          <div className="qan-plan-timeline">
                            {plans.map((p) => {
                              const info = extractPlanSummary(p.plan_summary);
                              return (
                                <button
                                  key={p.plan_id}
                                  className={`qan-plan-timeline-item ${selectedPlanId === p.plan_id ? "qan-plan-timeline-item--selected" : ""}`}
                                  onClick={() => fetchPlanDetail(p.plan_id)}
                                >
                                  <span className="qan-plan-timeline-time">
                                    {new Date(p.created_at).toLocaleString()}
                                  </span>
                                  <span className="qan-plan-timeline-ops">
                                    <span className="qan-plan-timeline-badge">
                                      type: {info.access_type}
                                    </span>
                                    <span className="qan-plan-timeline-badge">
                                      key: {info.key}
                                    </span>
                                  </span>
                                </button>
                              );
                            })}
                          </div>

                          {viewedPlan ? (
                            <>
                              <div className="qan-detail-label" style={{ marginTop: 12 }}>{t("qan.plan_view_tree")}</div>
                              <div className="qan-plan-tree">
                                {viewedPlan.plan_json ? (
                                  <PlanNode data={viewedPlan.plan_json} depth={0} />
                                ) : (
                                  <pre className="qan-sql-block" style={{ fontSize: 11 }}>
                                    {JSON.stringify(viewedPlan.plan_summary || viewedPlan, null, 2)}
                                  </pre>
                                )}
                              </div>
                            </>
                          ) : (
                            <div className="empty-state" style={{ padding: 16 }}>
                              <span className="empty-state-title" style={{ fontSize: 13 }}>{t("qan.plan_view_select")}</span>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Compare mode */}
                      {planMode === "compare" && (
                        <div className="qan-detail-section">
                          <div className="qan-plan-compare-selectors">
                            <select className="qan-plan-compare-select" value={compareA} onChange={(e) => setCompareA(e.target.value)}>
                              <option value="">{t("qan.plan_select_a")}</option>
                              {plans.map((p) => (
                                <option key={p.plan_id} value={p.plan_id}>
                                  {new Date(p.created_at).toLocaleString()}
                                </option>
                              ))}
                            </select>
                            <span className="qan-plan-compare-vs">vs</span>
                            <select className="qan-plan-compare-select" value={compareB} onChange={(e) => setCompareB(e.target.value)}>
                              <option value="">{t("qan.plan_select_b")}</option>
                              {plans.map((p) => (
                                <option key={p.plan_id} value={p.plan_id}>
                                  {new Date(p.created_at).toLocaleString()}
                                </option>
                              ))}
                            </select>
                            <button
                              className="qan-plan-compare-btn"
                              onClick={handleCompare}
                              disabled={!compareA || !compareB || compareLoading}
                            >
                              {compareLoading ? t("common.loading") : t("qan.plan_compare_btn")}
                            </button>
                          </div>

                          {compareResult && (
                            <>
                              <PlanDiffTable diff={compareResult.diff} />
                              <div className="qan-plan-section-label">{t("qan.plan_a_label")}</div>
                              <div className="qan-plan-tree">
                                <PlanNode
                                  data={compareResult.plan_a?.plan_json || JSON.parse(compareResult.plan_a?.plan_json || "{}")}
                                  depth={0}
                                  highlightPaths={diffPaths}
                                  diffMap={diffMap}
                                />
                              </div>
                              <div className="qan-plan-section-label" style={{ marginTop: 12 }}>{t("qan.plan_b_label")}</div>
                              <div className="qan-plan-tree">
                                <PlanNode
                                  data={compareResult.plan_b?.plan_json || JSON.parse(compareResult.plan_b?.plan_json || "{}")}
                                  depth={0}
                                  highlightPaths={diffPaths}
                                  diffMap={diffMap}
                                />
                              </div>
                            </>
                          )}
                        </div>
                      )}
                    </>
                  )}
                </>
              )}

              {/* Tab: 优化建议 */}
              {drawerTab === "suggestions" && (
                <div className="qan-detail-section">
                  {suggestions.length === 0 ? (
                    <div className="empty-state" style={{ padding: 24 }}>
                      <span className="material-symbols-outlined empty-state-icon" style={{ color: "var(--color-success)" }}>check_circle</span>
                      <div className="empty-state-title">{t("qan.suggest_empty")}</div>
                      <div className="empty-state-desc">{t("qan.suggest_empty_desc")}</div>
                    </div>
                  ) : (
                    suggestions.map((s, i) => (
                      <div key={i} className={`qan-suggest-card qan-suggest-card--${s.severity}`}>
                        <span className="material-symbols-outlined qan-suggest-icon">
                          {s.severity === "warning" ? "warning" : "info"}
                        </span>
                        <div className="qan-suggest-body">
                          <span className="qan-suggest-badge">
                            {s.severity === "warning" ? t("qan.severity_warning") : t("qan.severity_info")}
                          </span>
                          <span className="qan-suggest-text">{s.text}</span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}
            </>
          ) : null}
        </div>
      </div>
    </AppLayout>
  );
}
