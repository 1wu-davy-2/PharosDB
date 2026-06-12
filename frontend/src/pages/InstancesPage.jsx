import { useEffect, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import api from "../services/api";
import AppLayout from "../components/AppLayout";
import { resolveDbIcon, resolveDbLabel } from "../assets/DbIcons";
import "./InstancesPage.css";

const fmtDatetime = (val) => {
  if (!val) return "—";
  const d = new Date(val);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} `
    + `${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

const DB_TYPES = [
  { value: "mysql", label: "MySQL" },
  { value: "mariadb", label: "MariaDB" },
  { value: "postgresql", label: "PostgreSQL" },
  { value: "mongodb", label: "MongoDB" },
];

const ENV_OPTIONS = [
  { value: "prod", labelKey: "instances.env_prod" },
  { value: "staging", labelKey: "instances.env_staging" },
  { value: "dev", labelKey: "instances.env_dev" },
];

export default function InstancesPage() {
  const { t } = useTranslation();
  const [instances, setInstances] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState(null);
  const [toast, setToast] = useState(null);
  const [expandedHistory, setExpandedHistory] = useState(null);
  const [historyData, setHistoryData] = useState({});
  const [historyLoading, setHistoryLoading] = useState(false);
  const [schedulerStatus, setSchedulerStatus] = useState({});
  const [search, setSearch] = useState("");
  const [filterType, setFilterType] = useState("");
  const [filterEnv, setFilterEnv] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [visibleCols, setVisibleCols] = useState({
    type: true, env: true, host: true, version: true, lastCollect: true,
  });
  const [colMenuOpen, setColMenuOpen] = useState(false);
  const [errorPopoverId, setErrorPopoverId] = useState(null);

  const loadSchedulerStatus = useCallback(async () => {
    try {
      const { data } = await api.get("/collector/scheduler/status/");
      const map = {};
      (data.collectors || []).forEach((s) => { map[s.instance_id] = s; });
      setSchedulerStatus(map);
    } catch { /* silently ignore */ }
  }, []);

  useEffect(() => {
    loadSchedulerStatus();
    const timer = setInterval(loadSchedulerStatus, 30000);
    return () => clearInterval(timer);
  }, [loadSchedulerStatus]);

  const showToast = (msg, type = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const load = useCallback(() => {
    setLoading(true);
    api.get("/collector/instances/")
      .then(({ data }) => setInstances(data.results || data))
      .catch(() => showToast(t("instances.load_failed"), "error"))
      .finally(() => setLoading(false));
  }, [t]);

  useEffect(() => { load(); }, [load]);

  const filtered = instances.filter((i) => {
    const s = search.toLowerCase();
    if (s && !i.name.toLowerCase().includes(s)
          && !i.host.toLowerCase().includes(s)
          && !(i.db_version || "").toLowerCase().includes(s)) return false;
    if (filterType === "mariadb") {
      if (!(i.db_type === "mysql" && /MariaDB/i.test(i.db_version || ""))) return false;
    } else if (filterType && i.db_type !== filterType) return false;
    if (filterEnv && i.environment !== filterEnv) return false;
    if (filterStatus && i.connection_status !== filterStatus) return false;
    return true;
  });

  const handleDelete = async (id) => {
    if (!confirm(t("common.confirm_delete"))) return;
    try {
      await api.delete(`/collector/instances/${id}/`);
      showToast(t("instances.deleted"));
      load();
    } catch { showToast(t("instances.delete_failed"), "error"); }
  };

  const handleTest = async (id) => {
    try {
      const { data } = await api.post(`/collector/instances/${id}/test/`);
      showToast(data.message, data.success ? "success" : "error");
    } catch {
      showToast(t("instances.test_failed"), "error");
    }
  };

  const handleCollect = async (id) => {
    try {
      const { data } = await api.post(`/collector/instances/${id}/collect/`);
      showToast(data.message, data.success ? "success" : "error");
      load();
      if (expandedHistory === id) loadHistory(id, true);
    } catch {
      showToast(t("instances.collect_failed"), "error");
    }
  };

  const loadHistory = useCallback(async (id, silent = false) => {
    if (!silent) setHistoryLoading(true);
    try {
      const { data } = await api.get(`/collector/instances/${id}/history/?limit=20`);
      setHistoryData((prev) => ({ ...prev, [id]: data }));
    } catch { /* silently ignore */ }
    if (!silent) setHistoryLoading(false);
  }, []);

  const toggleHistory = (id) => {
    if (expandedHistory === id) {
      setExpandedHistory(null);
    } else {
      setExpandedHistory(id);
      loadHistory(id);
    }
  };

  const hasFilters = search || filterType || filterEnv || filterStatus;

  return (
    <AppLayout title={t("instances.title")}>
      {toast && (
        <div className={`toast toast-${toast.type}`}>{toast.msg}</div>
      )}

      <div className="inst-page">
        {/* ── toolbar ── */}
        <div className="inst-toolbar">
          <div className="inst-search-wrap">
            <span className="material-symbols-outlined inst-search-icon">search</span>
            <input
              className="inst-search"
              placeholder={t("instances.search_placeholder")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {search && (
              <button className="inst-search-clear" onClick={() => setSearch("")}>
                <span className="material-symbols-outlined" style={{ fontSize: 18 }}>close</span>
              </button>
            )}
          </div>

          <button className="inst-query-btn" onClick={() => load()}>
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>search</span>
            {t("instances.query")}
          </button>

          <div className="inst-filters">
            <select className="inst-filter" value={filterType} onChange={(e) => setFilterType(e.target.value)}>
              <option value="">{t("instances.filter_type")}</option>
              {DB_TYPES.map((dt) => <option key={dt.value} value={dt.value}>{dt.label}</option>)}
            </select>

            <select className="inst-filter" value={filterEnv} onChange={(e) => setFilterEnv(e.target.value)}>
              <option value="">{t("instances.filter_env")}</option>
              {ENV_OPTIONS.map((e) => (
                <option key={e.value} value={e.value}>{t(e.labelKey)}</option>
              ))}
            </select>

            <select className="inst-filter" value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
              <option value="">{t("instances.filter_status")}</option>
              <option value="connected">{t("instances.conn_connected")}</option>
              <option value="disconnected">{t("instances.conn_disconnected")}</option>
            </select>

            {hasFilters && (
              <button
                className="inst-filter-clear"
                onClick={() => { setSearch(""); setFilterType(""); setFilterEnv(""); setFilterStatus(""); }}
              >
                {t("instances.filter_clear")}
              </button>
            )}
          </div>

          <div className="inst-col-wrap">
            <button className="inst-col-btn" onClick={() => setColMenuOpen(!colMenuOpen)}>
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>view_column</span>
              {t("instances.columns")}
            </button>
            {colMenuOpen && (
              <div className="inst-col-drop">
                {Object.entries({
                  type: t("instances.col_type"),
                  env: t("instances.col_env"),
                  host: t("instances.col_host"),
                  version: t("instances.col_version"),
                  lastCollect: t("instances.col_last_collect"),
                }).map(([key, label]) => (
                  <label key={key} className="inst-col-opt">
                    <input type="checkbox" checked={visibleCols[key]}
                      onChange={(e) => setVisibleCols((v) => ({ ...v, [key]: e.target.checked }))} />
                    {label}
                  </label>
                ))}
              </div>
            )}
          </div>

          <button className="inst-add-btn" onClick={() => { setEditing(null); setShowModal(true); }}>
            <span className="material-symbols-outlined" style={{ fontSize: 18 }}>add</span>
            {t("instances.register")}
          </button>
        </div>

        {/* ── table ── */}
        <div className="inst-table-card">
          {loading ? (
            <div className="inst-loading">{t("common.loading")}</div>
          ) : filtered.length === 0 ? (
            <div className="inst-empty">
              <span className="material-symbols-outlined inst-empty-icon">dns</span>
              <div className="inst-empty-title">{t("instances.no_instances")}</div>
              <div className="inst-empty-desc">{t("instances.no_instances_desc")}</div>
            </div>
          ) : (
            <div className="inst-table-scroll">
              <table className="inst-table">
                <thead>
                  <tr>
                    <th className="inst-th-status" />
                    <th>{t("instances.col_name")}</th>
                    {visibleCols.type        && <th>{t("instances.col_type")}</th>}
                    {visibleCols.env         && <th>{t("instances.col_env")}</th>}
                    {visibleCols.host        && <th>{t("instances.col_host")}</th>}
                    {visibleCols.version     && <th>{t("instances.col_version")}</th>}
                    {visibleCols.lastCollect && <th>{t("instances.col_last_collect")}</th>}
                    <th className="inst-th-actions" />
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((inst) => (
                    <>
                      <tr key={inst.id} className="inst-row">
                        {/* Status — consistent span wrapper for all three states */}
                        <td className="inst-td-status">
                          <span className="inst-status-wrap">
                            {inst.connection_status === "connected" && schedulerStatus[inst.id]?.active ? (
                              <span className="inst-status-label inst-status--live">
                                <span className="inst-dot inst-dot--live" />
                                {t("instances.conn_live")}
                              </span>
                            ) : inst.connection_status === "connected" ? (
                              <span className="inst-status-label inst-status--ok">
                                <span className="inst-dot inst-dot--idle" />
                                {t("instances.conn_connected")}
                              </span>
                            ) : (
                              <span
                                className={`inst-status-label inst-status--err ${inst.last_error ? "inst-status--clickable" : ""}`}
                                role={inst.last_error ? "button" : undefined}
                                tabIndex={inst.last_error ? 0 : undefined}
                                title={inst.last_error ? t("instances.click_for_error") : undefined}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  if (inst.last_error) {
                                    setErrorPopoverId(errorPopoverId === inst.id ? null : inst.id);
                                  }
                                }}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter" || e.key === " ") {
                                    e.preventDefault();
                                    if (inst.last_error) {
                                      setErrorPopoverId(errorPopoverId === inst.id ? null : inst.id);
                                    }
                                  }
                                }}
                              >
                                <span className="inst-dot inst-dot--dead" />
                                {t("instances.conn_disconnected")}
                              </span>
                            )}
                          </span>
                        </td>

                        {/* Name */}
                        <td className="inst-td-name">
                          <span className="inst-name">{inst.name}</span>
                          {inst.cluster && <span className="inst-cluster-tag">{inst.cluster}</span>}
                        </td>

                        {/* Type */}
                        {visibleCols.type && (
                          <td>
                            <span className="inst-type-badge">
                              {(() => { const Icon = resolveDbIcon(inst.db_type, inst.db_version); return <Icon size={16} />; })()}
                              <span className="inst-type-label">{resolveDbLabel(inst.db_type, inst.db_version)}</span>
                            </span>
                          </td>
                        )}

                        {/* Environment */}
                        {visibleCols.env && (
                          <td>
                            <span className={`inst-env-badge inst-env--${inst.environment}`}>
                              {t(ENV_OPTIONS.find((e) => e.value === inst.environment)?.labelKey || "instances.env_prod")}
                            </span>
                          </td>
                        )}

                        {/* Address */}
                        {visibleCols.host && (
                          <td className="inst-td-mono">{inst.host}:{inst.port}</td>
                        )}

                        {/* Version */}
                        {visibleCols.version && (
                          <td className="inst-td-mono inst-td-version" title={inst.db_version || undefined}>
                          {(() => {
                            const v = inst.db_version;
                            if (!v) return "—";
                            const m = v.match(/^(\d+\.\d+)/);
                            return m ? m[1] : v.slice(0, 12);
                          })()}
                          </td>
                        )}

                        {/* Last collection */}
                        {visibleCols.lastCollect && (
                          <td className="inst-td-time">{fmtDatetime(inst.last_collected_at)}</td>
                        )}

                        {/* Actions — icon buttons */}
                        <td className="inst-td-actions">
                          <button
                            className="inst-act-btn inst-act-btn--collect"
                            title={t("instances.btn_collect")}
                            onClick={() => handleCollect(inst.id)}
                          >
                            <span className="material-symbols-outlined">sync</span>
                          </button>
                          <button
                            className={`inst-act-btn ${expandedHistory === inst.id ? "inst-act-btn--on" : ""}`}
                            title={t("instances.btn_history")}
                            onClick={() => toggleHistory(inst.id)}
                          >
                            <span className="material-symbols-outlined">schedule</span>
                          </button>
                          <button
                            className="inst-act-btn"
                            title={t("common.edit")}
                            onClick={() => { setEditing(inst); setShowModal(true); }}
                          >
                            <span className="material-symbols-outlined">edit</span>
                          </button>
                          <button
                            className="inst-act-btn inst-act-btn--del"
                            title={t("common.delete")}
                            onClick={() => handleDelete(inst.id)}
                          >
                            <span className="material-symbols-outlined">delete</span>
                          </button>
                        </td>
                      </tr>

                      {/* History expand */}
                      {expandedHistory === inst.id && (
                        <tr key={`${inst.id}-hist`} className="inst-expand-row">
                          <td colSpan={2 + Object.values(visibleCols).filter(Boolean).length + 1}>
                            <HistoryPanel records={historyData[inst.id]} loading={historyLoading} />
                          </td>
                        </tr>
                      )}

                      {/* Error row — collapsed, click status label to expand */}
                      {inst.connection_status === "disconnected" && inst.last_error && errorPopoverId === inst.id && (
                        <tr key={`${inst.id}-err`} className="inst-err-row">
                          <td colSpan={2 + Object.values(visibleCols).filter(Boolean).length + 1}>
                            <div className="inst-err-popover">
                              <div className="inst-err-popover-head">
                                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>error</span>
                                <span className="inst-err-popover-title">{t("instances.err_detail")}</span>
                                <button
                                  className="inst-err-copy-btn"
                                  onClick={() => {
                                    navigator.clipboard.writeText(inst.last_error);
                                    showToast(t("instances.err_copied"), "success");
                                  }}
                                >
                                  <span className="material-symbols-outlined" style={{ fontSize: 14 }}>content_copy</span>
                                  {t("instances.err_copy")}
                                </button>
                                <button className="inst-err-close-btn" onClick={() => setErrorPopoverId(null)}>
                                  <span className="material-symbols-outlined" style={{ fontSize: 16 }}>close</span>
                                </button>
                              </div>
                              <pre className="inst-err-body">{inst.last_error}</pre>
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {showModal && (
        <InstanceModal
          instance={editing}
          onClose={() => setShowModal(false)}
          onSaved={() => {
            setShowModal(false);
            load();
            showToast(editing ? t("instances.updated") : t("instances.created"));
          }}
        />
      )}
    </AppLayout>
  );
}

/* ═══ History Panel ═══ */
function HistoryPanel({ records, loading }) {
  const { t } = useTranslation();
  if (loading) {
    return <div className="inst-hist-panel"><div className="inst-loading">{t("common.loading")}</div></div>;
  }
  if (!records) return null;
  if (!records.length) {
    return <div className="inst-hist-panel inst-hist-empty">{t("instances.no_history")}</div>;
  }
  return (
    <div className="inst-hist-panel">
      <div className="inst-hist-head">
        {t("instances.btn_history")} &middot; {records.length} records
      </div>
      <table className="inst-hist-table">
        <thead>
          <tr>
            <th>{t("history.col_start")}</th>
            <th>{t("history.col_trigger")}</th>
            <th>{t("history.col_status")}</th>
            <th className="inst-th-r">{t("history.col_duration")}</th>
            <th className="inst-th-r">{t("history.col_queries")}</th>
            <th className="inst-th-r">{t("history.col_rows")}</th>
            <th>{t("history.col_error")}</th>
          </tr>
        </thead>
        <tbody>
          {records.map((r) => (
            <tr key={r.id}>
              <td className="inst-td-mono inst-td-sm">{fmtDatetime(r.started_at)}</td>
              <td>
                <span className={`inst-chp ${r.triggered_by === "manual" ? "inst-chp--manual" : "inst-chp--sched"}`}>
                  {r.triggered_by === "manual" ? t("history.trigger_manual") : t("history.trigger_scheduled")}
                </span>
              </td>
              <td>
                <span className={`inst-chp ${r.status === "success" ? "inst-chp--ok" : r.status === "partial" ? "inst-chp--warn" : "inst-chp--err"}`}>
                  {r.status === "success" ? t("history.status_success") : r.status === "partial" ? t("history.status_partial") : t("history.status_failed")}
                </span>
              </td>
              <td className="inst-td-r">{r.duration_ms != null ? `${r.duration_ms}ms` : "—"}</td>
              <td className="inst-td-r">{r.queries_collected}</td>
              <td className="inst-td-r">{r.rows_written}</td>
              <td className="inst-td-err" title={r.error_message || undefined}>
                {r.error_message || "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ═══ Instance Modal ═══ */
function InstanceModal({ instance, onClose, onSaved }) {
  const { t } = useTranslation();

  const [form, setForm] = useState({
    name: instance?.name || "",
    db_type: instance?.db_type || "mysql",
    host: instance?.host || "",
    port: instance?.port || 3306,
    username: instance?.username || "",
    password: "",
    environment: instance?.environment || "prod",
    cluster: instance?.cluster || "",
    is_active: instance?.is_active ?? true,
    collect_interval: instance?.collect_interval || 60,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [testResult, setTestResult] = useState(null);
  const [testing, setTesting] = useState(false);

  const set = (key, value) => setForm((f) => ({ ...f, [key]: value }));

  const handleTestConfig = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const { data } = await api.post("/collector/instances/test-config/", {
        host: form.host, port: form.port,
        username: form.username, password: form.password,
        db_type: form.db_type,
      });
      setTestResult(data);
    } catch (e) {
      setTestResult({ success: false, message: e.response?.data?.message || "Request failed" });
    } finally {
      setTesting(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const payload = { ...form };
      if (payload.db_type === "mariadb") payload.db_type = "mysql";
      if (instance && !payload.password) delete payload.password;
      if (instance) {
        await api.put(`/collector/instances/${instance.id}/`, payload);
      } else {
        await api.post("/collector/instances/", payload);
      }
      onSaved();
    } catch (err) {
      const msg = err.response?.data;
      setError(typeof msg === "string" ? msg : JSON.stringify(msg));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="inst-modal-backdrop" onClick={onClose}>
      <div className="inst-modal" onClick={(e) => e.stopPropagation()}>
        <div className="inst-modal-head">
          <span className="inst-modal-title">
            {instance ? t("instances.modal_edit") : t("instances.modal_create")}
          </span>
          <button className="inst-modal-x" onClick={onClose}>
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="inst-modal-body">
            {error && <div className="inst-modal-err">{error}</div>}

            <div className="inst-form-g">
              <label className="inst-form-lbl">{t("instances.field_name")}</label>
              <input className="inst-form-in" value={form.name} onChange={(e) => set("name", e.target.value)} required placeholder="db-prod-01" />
            </div>

            <div className="inst-form-r">
              <div className="inst-form-g">
                <label className="inst-form-lbl">{t("instances.field_db_type")}</label>
                <select className="inst-form-sel" value={form.db_type} onChange={(e) => set("db_type", e.target.value)}>
                  {DB_TYPES.map((dt) => <option key={dt.value} value={dt.value}>{dt.label}</option>)}
                </select>
              </div>
              <div className="inst-form-g">
                <label className="inst-form-lbl">{t("instances.field_env")}</label>
                <select className="inst-form-sel" value={form.environment} onChange={(e) => set("environment", e.target.value)}>
                  {ENV_OPTIONS.map((e2) => <option key={e2.value} value={e2.value}>{t(e2.labelKey)}</option>)}
                </select>
              </div>
            </div>

            <div className="inst-form-r">
              <div className="inst-form-g">
                <label className="inst-form-lbl">{t("instances.field_host")}</label>
                <input className="inst-form-in" value={form.host} onChange={(e) => set("host", e.target.value)} required placeholder="192.168.1.100" />
              </div>
              <div className="inst-form-g">
                <label className="inst-form-lbl">{t("instances.field_port")}</label>
                <input className="inst-form-in" type="number" value={form.port} onChange={(e) => set("port", parseInt(e.target.value))} required />
              </div>
            </div>

            <div className="inst-form-r">
              <div className="inst-form-g">
                <label className="inst-form-lbl">{t("instances.field_username")}</label>
                <input className="inst-form-in" value={form.username} onChange={(e) => set("username", e.target.value)} required />
              </div>
              <div className="inst-form-g">
                <label className="inst-form-lbl">{t("instances.field_password")}</label>
                <input className="inst-form-in" type="password" value={form.password}
                  onChange={(e) => set("password", e.target.value)}
                  placeholder={instance ? t("instances.pwd_placeholder") : ""} />
              </div>
            </div>

            <div className="inst-form-r">
              <div className="inst-form-g">
                <label className="inst-form-lbl">{t("instances.field_cluster")}</label>
                <input className="inst-form-in" value={form.cluster}
                  onChange={(e) => set("cluster", e.target.value)}
                  placeholder={t("instances.cluster_optional")} />
              </div>
              <div className="inst-form-g">
                <label className="inst-form-lbl">{t("instances.field_interval")}</label>
                <input className="inst-form-in" type="number" value={form.collect_interval}
                  onChange={(e) => set("collect_interval", parseInt(e.target.value))} />
              </div>
            </div>

            <label className="inst-form-check">
              <input type="checkbox" checked={form.is_active}
                onChange={(e) => set("is_active", e.target.checked)} />
              <span>{t("instances.field_active")}</span>
            </label>

            {testResult && (
              <div className={`inst-test-badge ${testResult.success ? "inst-test-ok" : "inst-test-fail"}`}>
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                  {testResult.success ? "check_circle" : "error"}
                </span>
                {testResult.message}
                {testResult.version && (
                  <span className="inst-test-ver">{testResult.version}</span>
                )}
              </div>
            )}
          </div>

          <div className="inst-modal-foot">
            <button type="button" className="inst-btn-ghost" onClick={onClose}>{t("common.cancel")}</button>
            <button type="button" className="inst-btn-ghost"
              disabled={testing || !form.host || (!instance && !form.password)}
              onClick={handleTestConfig}>
              {testing ? t("common.loading") : t("instances.btn_test")}
            </button>
            <button type="submit" className="inst-btn-primary" disabled={saving}>
              {saving ? t("common.saving") : t("common.save")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
