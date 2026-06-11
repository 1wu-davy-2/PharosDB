import { useEffect, useState, useCallback } from "react";
import api from "../services/api";
import AppLayout from "../components/AppLayout";
import "./QANPage.css";

const PERIODS = [
  { value: "1h", label: "1 小时" },
  { value: "6h", label: "6 小时" },
  { value: "24h", label: "24 小时" },
  { value: "7d", label: "7 天" },
];

const SORT_OPTIONS = [
  { value: "m_query_time_sum", label: "总耗时" },
  { value: "num_queries", label: "执行次数" },
  { value: "m_rows_examined_sum", label: "扫描行数" },
  { value: "m_lock_time_sum", label: "锁等待" },
  { value: "m_no_index_used_sum", label: "无索引" },
];

const LIMIT_OPTIONS = [10, 20, 50, 100];

export default function QANPage() {
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

  // 加载服务列表
  useEffect(() => {
    api.get("/qan/top-queries/")
      .then(({ data }) => {
        setServices(data.services || []);
        if (data.services?.length > 0) setSelectedService(data.services[0]);
      })
      .catch(() => {});
  }, []);

  // 加载数据
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

  // 搜索提交
  const handleSearch = useCallback(() => {
    setSearchText(searchInput);
  }, [searchInput]);

  const handleSearchKey = useCallback((e) => {
    if (e.key === "Enter") setSearchText(searchInput);
    if (e.key === "Escape") { setSearchInput(""); setSearchText(""); }
  }, [searchInput]);

  // 获取唯一 schema 列表
  const schemas = [...new Set(queries.map((q) => q.schema).filter(Boolean))];

  // 加载查询详情 → 打开侧栏
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
    <AppLayout title="SQL 分析">
      {/* 筛选栏 */}
      <div className="card qan-filters">
        <div className="qan-filter-group">
          <label className="qan-filter-label">服务</label>
          <select className="form-select qan-filter-select" value={selectedService} onChange={(e) => setSelectedService(e.target.value)}>
            {services.length === 0 && <option>暂无服务</option>}
            {services.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        <div className="qan-filter-group">
          <label className="qan-filter-label">时间范围</label>
          <div className="qan-period-tabs">
            {PERIODS.map((p) => (
              <button key={p.value} className={`qan-period-tab ${period === p.value ? "qan-period-tab--active" : ""}`} onClick={() => setPeriod(p.value)}>
                {p.label}
              </button>
            ))}
          </div>
        </div>

        <div className="qan-filter-group">
          <label className="qan-filter-label">排序</label>
          <select className="form-select qan-filter-select" value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
            {SORT_OPTIONS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </div>

        <div className="qan-filter-group">
          <label className="qan-filter-label">条数</label>
          <select className="form-select qan-filter-select qan-filter-narrow" value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
            {LIMIT_OPTIONS.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>

        <div className="qan-filter-group qan-filter-grow">
          <label className="qan-filter-label">SQL 搜索</label>
          <div className="qan-search-wrap">
            <span className="material-symbols-outlined qan-search-icon">search</span>
            <input
              className="form-input qan-search-input"
              placeholder="模糊匹配 SQL 关键词..."
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
            <label className="qan-filter-label">Schema</label>
            <select className="form-select qan-filter-select" value={schemaFilter} onChange={(e) => setSchemaFilter(e.target.value)}>
              <option value="">全部</option>
              {schemas.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        )}
      </div>

      {/* 搜索提示 */}
      {searchText && (
        <div className="qan-search-hint">
          搜索: "<strong>{searchText}</strong>"
          <button className="qan-search-hint-clear" onClick={() => { setSearchInput(""); setSearchText(""); }}>清除</button>
        </div>
      )}

      {/* 概览卡片 */}
      {overview && (
        <div className="qan-overview-row">
          <div className="stat-card">
            <div className="stat-card-header"><span className="stat-card-label">唯一查询</span></div>
            <div className="stat-card-body"><span className="stat-card-value">{fmtNum(overview.unique_queries)}</span></div>
          </div>
          <div className="stat-card">
            <div className="stat-card-header"><span className="stat-card-label">总执行次数</span></div>
            <div className="stat-card-body"><span className="stat-card-value">{fmtNum(overview.total_queries)}</span></div>
          </div>
          <div className="stat-card">
            <div className="stat-card-header"><span className="stat-card-label">平均耗时</span></div>
            <div className="stat-card-body"><span className="stat-card-value">{fmtTime(overview.avg_query_time)}</span></div>
          </div>
          <div className="stat-card">
            <div className="stat-card-header"><span className="stat-card-label">无索引查询</span></div>
            <div className="stat-card-body"><span className="stat-card-value" style={{ color: overview.no_index_queries > 0 ? "#ba1a1a" : undefined }}>{fmtNum(overview.no_index_queries)}</span></div>
          </div>
        </div>
      )}

      {/* 查询列表 */}
      <div className="card" style={{ overflow: "hidden" }}>
        <div className="card-header">
          <h2 className="card-title">Top 慢查询</h2>
          <span className="qan-result-count">{queries.length} 条结果</span>
        </div>
        {loading ? (
          <div className="loading-wrap"><div className="mini-spinner" /> 加载中...</div>
        ) : queries.length === 0 ? (
          <div className="empty-state">
            <span className="material-symbols-outlined empty-state-icon">query_stats</span>
            <div className="empty-state-title">暂无数据</div>
            <div className="empty-state-desc">{searchText ? "未匹配到相关 SQL，请尝试其他关键词" : "请先注册实例并执行采集，数据将在此展示"}</div>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="sql-table">
              <thead>
                <tr>
                  <th style={{ width: 40 }}>#</th>
                  <th>SQL 指纹</th>
                  <th className="text-right">总耗时</th>
                  <th className="text-right">平均耗时</th>
                  <th className="text-right">执行次数</th>
                  <th className="text-right">扫描行数</th>
                  <th className="text-right">锁等待</th>
                  <th className="text-right">无索引</th>
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
                    <td className="text-right font-medium" style={{ color: i === 0 ? "#ba1a1a" : i < 3 ? "#f59e0b" : undefined }}>
                      {fmtTime(q.total_query_time)}
                    </td>
                    <td className="text-right">{fmtTime(q.avg_query_time)}</td>
                    <td className="text-right">{fmtNum(q.num_queries)}</td>
                    <td className="text-right">{fmtNum(q.total_rows_examined)}</td>
                    <td className="text-right">{fmtTime(q.total_lock_time)}</td>
                    <td className="text-right" style={{ color: q.no_index_used_count > 0 ? "#ba1a1a" : undefined }}>
                      {fmtNum(q.no_index_used_count)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 侧栏详情 Drawer */}
      {drawerOpen && <div className="qan-drawer-overlay" onClick={closeDrawer} />}
      <div className={`qan-drawer ${drawerOpen ? "qan-drawer--open" : ""}`}>
        <div className="qan-drawer-header">
          <h2 className="qan-drawer-title">查询详情</h2>
          <button className="qan-drawer-close" onClick={closeDrawer}>
            <span className="material-symbols-outlined" style={{ fontSize: 22 }}>close</span>
          </button>
        </div>

        <div className="qan-drawer-body">
          {detailLoading ? (
            <div className="loading-wrap"><div className="mini-spinner" /> 加载中...</div>
          ) : detail ? (
            <>
              <div className="qan-detail-section">
                <div className="qan-detail-label">SQL 指纹</div>
                <pre className="qan-sql-block">{detail.fingerprint}</pre>
              </div>

              {detail.example && (
                <div className="qan-detail-section">
                  <div className="qan-detail-label">示例 SQL</div>
                  <pre className="qan-sql-block">{detail.example}</pre>
                </div>
              )}

              <div className="qan-detail-grid">
                <div className="qan-metric">
                  <span className="qan-metric-label">执行次数</span>
                  <span className="qan-metric-value">{fmtNum(detail.num_queries)}</span>
                </div>
                <div className="qan-metric">
                  <span className="qan-metric-label">总耗时</span>
                  <span className="qan-metric-value">{fmtTime(detail.total_query_time)}</span>
                </div>
                <div className="qan-metric">
                  <span className="qan-metric-label">平均耗时</span>
                  <span className="qan-metric-value">{fmtTime(detail.avg_query_time)}</span>
                </div>
                <div className="qan-metric">
                  <span className="qan-metric-label">最大耗时</span>
                  <span className="qan-metric-value">{fmtTime(detail.max_query_time)}</span>
                </div>
                <div className="qan-metric">
                  <span className="qan-metric-label">返回行数</span>
                  <span className="qan-metric-value">{fmtNum(detail.total_rows_sent)}</span>
                </div>
                <div className="qan-metric">
                  <span className="qan-metric-label">扫描行数</span>
                  <span className="qan-metric-value">{fmtNum(detail.total_rows_examined)}</span>
                </div>
                <div className="qan-metric">
                  <span className="qan-metric-label">锁等待</span>
                  <span className="qan-metric-value">{fmtTime(detail.total_lock_time)}</span>
                </div>
                <div className="qan-metric">
                  <span className="qan-metric-label">临时表</span>
                  <span className="qan-metric-value">{fmtNum(detail.total_tmp_tables)}</span>
                </div>
                <div className="qan-metric">
                  <span className="qan-metric-label">全表扫描</span>
                  <span className="qan-metric-value" style={{ color: detail.full_scan_count > 0 ? "#ba1a1a" : undefined }}>{fmtNum(detail.full_scan_count)}</span>
                </div>
                <div className="qan-metric">
                  <span className="qan-metric-label">无索引</span>
                  <span className="qan-metric-value" style={{ color: detail.no_index_used_count > 0 ? "#ba1a1a" : undefined }}>{fmtNum(detail.no_index_used_count)}</span>
                </div>
                <div className="qan-metric">
                  <span className="qan-metric-label">Filesort</span>
                  <span className="qan-metric-value">{fmtNum(detail.filesort_count)}</span>
                </div>
                <div className="qan-metric">
                  <span className="qan-metric-label">发送字节</span>
                  <span className="qan-metric-value">{fmtNum(detail.total_bytes_sent)}</span>
                </div>
              </div>

              {trend.length > 0 && (
                <div className="qan-detail-section">
                  <div className="qan-detail-label">24h 趋势</div>
                  <div className="qan-trend-chart">
                    {trend.map((t, i) => {
                      const maxTime = Math.max(...trend.map((x) => x.total_query_time));
                      const height = maxTime > 0 ? (t.total_query_time / maxTime) * 100 : 0;
                      return (
                        <div key={i} className="qan-trend-bar-wrap">
                          <div className="qan-trend-bar" style={{ height: `${Math.max(height, 2)}%` }} title={`${fmtTime(t.avg_query_time)} / ${fmtNum(t.num_queries)}次`} />
                          <span className="qan-trend-label">{new Date(t.hour).getHours()}:00</span>
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
