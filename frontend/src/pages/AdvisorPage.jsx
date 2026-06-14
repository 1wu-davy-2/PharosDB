import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "../services/api";
import AppLayout from "../components/AppLayout";
import "./AdvisorPage.css";

/* ── 严重度映射 ── */
const SEV = {
  critical: { color: "#ef4444", bg: "rgba(239,68,68,.12)", label: "严重" },
  error: { color: "#f87171", bg: "rgba(248,113,113,.10)", label: "错误" },
  warning: { color: "#fbbf24", bg: "rgba(251,191,36,.10)", label: "警告" },
  info: { color: "#60a5fa", bg: "rgba(96,165,250,.10)", label: "提示" },
};

const CAT_LABELS = {
  security: "安全", configuration: "配置", performance: "性能",
};

/* ═══════════════════════════════════════════════════════════════
   AdvisorPage
   ═══════════════════════════════════════════════════════════════ */

export default function AdvisorPage() {
  const { t } = useTranslation();

  const [checks, setChecks] = useState([]);
  const [findings, setFindings] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState(null);

  // filters
  const [filterFamily, setFilterFamily] = useState("");
  const [filterCategory, setFilterCategory] = useState("");
  const [filterSeverity, setFilterSeverity] = useState("");
  const [tab, setTab] = useState("findings"); // findings | checks

  // ── Load ──
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [cr, fr, sr] = await Promise.all([
        api.get("/advisor/checks/"),
        api.get("/advisor/findings/?limit=100"),
        api.get("/advisor/summary/"),
      ]);
      setChecks(cr.data.checks || []);
      setFindings(fr.data.findings || []);
      setSummary(sr.data);
    } catch {
      setMsg({ type: "error", text: t("common.error") });
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => { load(); }, [load]);

  // ── Run all checks ──
  const handleRun = async () => {
    setRunning(true);
    setMsg(null);
    try {
      const { data } = await api.post("/advisor/run/", { action: "all" });
      setMsg({ type: "success", text: `巡检完成：${data.findings} 项发现` });
      await load();
    } catch (e) {
      setMsg({ type: "error", text: e.response?.data?.error || "巡检执行失败" });
    } finally {
      setRunning(false);
    }
  };

  // ── Toggle check ──
  const handleToggle = async (name, enabled) => {
    try {
      await api.post("/advisor/checks/toggle/", { name, enabled: !enabled });
      load();
    } catch {}
  };

  // ── Filters ──
  const families = [...new Set(checks.map((c) => c.family))];
  const categories = [...new Set(checks.map((c) => c.category))];

  let filtered = tab === "checks" ? checks : findings;
  if (filterFamily) filtered = filtered.filter((c) => c.family === filterFamily);
  if (filterCategory) filtered = filtered.filter((c) => c.category === filterCategory);
  if (filterSeverity) filtered = filtered.filter((c) => c.severity === filterSeverity);

  return (
    <AppLayout title={t("nav.advisor")}>
      <div className="advisor-page">
        {/* ── Summary Bar ── */}
        {summary && (
          <div className="advisor-summary">
            <div className="advisor-summary-card advisor-summary-total">
              <span className="advisor-summary-num">{summary.total}</span>
              <span className="advisor-summary-label">活跃发现</span>
            </div>
            <div className="advisor-summary-card advisor-summary-critical">
              <span className="advisor-summary-num">{summary.by_severity?.critical + summary.by_severity?.error || 0}</span>
              <span className="advisor-summary-label">严重/错误</span>
            </div>
            <div className="advisor-summary-card advisor-summary-warning">
              <span className="advisor-summary-num">{summary.by_severity?.warning || 0}</span>
              <span className="advisor-summary-label">警告</span>
            </div>
            <div className="advisor-summary-card advisor-summary-info">
              <span className="advisor-summary-num">{summary.by_severity?.info || 0}</span>
              <span className="advisor-summary-label">提示</span>
            </div>
          </div>
        )}

        {/* ── Actions Bar ── */}
        <div className="advisor-bar">
          <div className="advisor-tabs">
            <button className={`advisor-tab ${tab === "findings" ? "advisor-tab--active" : ""}`} onClick={() => setTab("findings")}>
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>error</span>
              发现 ({findings.length})
            </button>
            <button className={`advisor-tab ${tab === "checks" ? "advisor-tab--active" : ""}`} onClick={() => setTab("checks")}>
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>rule</span>
              规则 ({checks.length})
            </button>
          </div>

          <div className="advisor-filters">
            <select className="advisor-sel" value={filterFamily} onChange={(e) => setFilterFamily(e.target.value)}>
              <option value="">全部类型</option>
              {families.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
            <select className="advisor-sel" value={filterCategory} onChange={(e) => setFilterCategory(e.target.value)}>
              <option value="">全部分类</option>
              {categories.map((c) => <option key={c} value={c}>{CAT_LABELS[c] || c}</option>)}
            </select>
            <select className="advisor-sel" value={filterSeverity} onChange={(e) => setFilterSeverity(e.target.value)}>
              <option value="">全部级别</option>
              {Object.entries(SEV).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </div>

          <button className="advisor-run-btn" onClick={handleRun} disabled={running}>
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
              {running ? "progress_activity" : "play_arrow"}
            </span>
            {running ? "执行中..." : "立即巡检"}
          </button>
        </div>

        {msg && (
          <div className={`advisor-msg advisor-msg--${msg.type}`}>{msg.text}</div>
        )}

        {/* ── Content ── */}
        {loading ? (
          <div className="loading-wrap"><div className="mini-spinner" /> 加载中...</div>
        ) : (
          <>
            {tab === "findings" && (
              filtered.length === 0 ? (
                <div className="empty-state" style={{ padding: 40 }}>
                  <span className="material-symbols-outlined empty-state-icon">verified</span>
                  <div className="empty-state-title">未发现安全问题</div>
                  <div className="empty-state-desc">所有巡检规则均已通过，数据库配置符合安全基准</div>
                </div>
              ) : (
                <div className="advisor-findings-list">
                  {filtered.map((f) => {
                    const sev = SEV[f.severity] || SEV.info;
                    return (
                      <div key={f.id} className="advisor-finding-card" style={{ borderLeftColor: sev.color }}>
                        <div className="advisor-finding-left">
                          <span className="advisor-finding-sev" style={{ background: sev.color }}>{sev.label}</span>
                          <div>
                            <div className="advisor-finding-title">{f.summary}</div>
                            <div className="advisor-finding-meta">
                              <span className="advisor-finding-check">{f.check_display}</span>
                              <span className="advisor-finding-instance">{f.instance_name} ({f.instance_type})</span>
                              <span className="advisor-finding-time">{f.found_at?.replace("T", " ").slice(0, 19)}</span>
                              {f.resolved_at && <span style={{ color: "var(--color-success)" }}>已修复</span>}
                            </div>
                          </div>
                        </div>
                        <div className="advisor-finding-right">
                          <span className="advisor-finding-cat" title={f.category}>{CAT_LABELS[f.category] || f.category}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )
            )}

            {tab === "checks" && (
              <div className="advisor-checks-grid">
                {filtered.map((c) => {
                  const sev = SEV[c.severity] || SEV.info;
                  return (
                    <div key={c.id} className={`advisor-check-card ${!c.enabled ? "advisor-check-card--disabled" : ""}`}>
                      <div className="advisor-check-header">
                        <span className="advisor-check-name">{c.display_name}</span>
                        <label className="advisor-check-toggle">
                          <input
                            type="checkbox"
                            checked={c.enabled}
                            onChange={() => handleToggle(c.name, c.enabled)}
                          />
                          <span className="advisor-check-toggle-slider" />
                        </label>
                      </div>
                      <div className="advisor-check-summary">{c.summary}</div>
                      <div className="advisor-check-meta">
                        <span className="advisor-check-tag" style={{ background: sev.bg, color: sev.color }}>{sev.label}</span>
                        <span className="advisor-check-tag">{c.family}</span>
                        <span className="advisor-check-tag">{CAT_LABELS[c.category] || c.category}</span>
                        <span className="advisor-check-tag">{c.mode === "exists" ? "存在即报" : `阈值 > ${c.threshold}`}</span>
                        {c.active_findings > 0 && (
                          <span className="advisor-check-tag" style={{ background: "rgba(239,68,68,.15)", color: "#f87171" }}>
                            {c.active_findings} 项发现
                          </span>
                        )}
                      </div>
                      {c.description && (
                        <div className="advisor-check-desc">{c.description}</div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>
    </AppLayout>
  );
}
