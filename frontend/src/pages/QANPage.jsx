import { useEffect, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import api from "../services/api";
import AppLayout from "../components/AppLayout";
import "./QANPage.css";

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
  const [limit, setLimit] = useState(20);
  const [searchText, setSearchText] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [schemaFilter, setSchemaFilter] = useState("");
  const [queries, setQueries] = useState([]);
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [detailQuery, setDetailQuery] = useState(null);
  const [detail, setDetail] = useState(null);
  const [trend, setTrend] = useState([]);
  const [detailLoading, setDetailLoading] = useState(false);

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
  }, [selectedService, period, sortBy, limit, searchText, schemaFilter]);

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
    setDetail(null);
    setTrend([]);
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

  const closeDrawer = () => {
    setDrawerOpen(false);
    setTimeout(() => { setDetailQuery(null); setDetail(null); }, 300);
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
          <select className="form-select qan-filter-select" value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
            {SORT_OPTIONS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
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
            <div className="stat-card-body"><span className="stat-card-value" style={{ color: overview.no_index_queries > 0 ? "var(--color-error-alt)" : undefined }}>{fmtNum(overview.no_index_queries)}</span></div>
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
                      <div className="qan-fingerprint" title={q.fingerprint}>
                        {q.fingerprint?.substring(0, 80)}{q.fingerprint?.length > 80 ? "..." : ""}
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

      {drawerOpen && <div className="qan-drawer-overlay" onClick={closeDrawer} />}
      <div className={`qan-drawer ${drawerOpen ? "qan-drawer--open" : ""}`}>
        <div className="qan-drawer-header">
          <h2 className="qan-drawer-title">{t("qan.drawer_title")}</h2>
          <button className="qan-drawer-close" onClick={closeDrawer}>
            <span className="material-symbols-outlined" style={{ fontSize: 22 }}>close</span>
          </button>
        </div>

        <div className="qan-drawer-body">
          {detailLoading ? (
            <div className="loading-wrap"><div className="mini-spinner" /> {t("common.loading")}</div>
          ) : detail ? (
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

              {trend.length > 0 && (
                <div className="qan-detail-section">
                  <div className="qan-detail-label">{t("qan.trend_title")}</div>
                  <div className="qan-trend-chart">
                    {trend.map((tItem, i) => {
                      const maxTime = Math.max(...trend.map((x) => x.total_query_time));
                      const height = maxTime > 0 ? (tItem.total_query_time / maxTime) * 100 : 0;
                      return (
                        <div key={i} className="qan-trend-bar-wrap">
                          <div className="qan-trend-bar" style={{ height: `${Math.max(height, 2)}%` }} title={`${fmtTime(tItem.avg_query_time)} / ${fmtNum(tItem.num_queries)}次`} />
                          <span className="qan-trend-label">{new Date(tItem.hour).getHours()}:00</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </>
          ) : null}
        </div>
      </div>
    </AppLayout>
  );
}
