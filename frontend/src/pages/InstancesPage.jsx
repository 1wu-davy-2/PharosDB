import { useEffect, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import api from "../services/api";
import AppLayout from "../components/AppLayout";
import "./InstancesPage.css";

function fmtDatetime(val) {
  if (!val) return "—";
  const d = new Date(val);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} `
       + `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

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
  const [filterType, setFilterType]       = useState("");
  const [filterEnv, setFilterEnv]         = useState("");
  const [filterStatus, setFilterStatus]   = useState("");

  const loadSchedulerStatus = useCallback(async () => {
    try {
      const { data } = await api.get("/collector/scheduler/status/");
      const map = {};
      (data.schedulers || []).forEach((s) => { map[s.instance_id] = s; });
      setSchedulerStatus(map);
    } catch {}
  }, []);

  // 每 30s 刷新调度器状态
  useEffect(() => {
    loadSchedulerStatus();
    const timer = setInterval(loadSchedulerStatus, 30000);
    return () => clearInterval(timer);
  }, [loadSchedulerStatus]);

  const DB_TYPES = [
    { value: "mysql", label: "MySQL" },
    { value: "postgresql", label: "PostgreSQL" },
    { value: "mongodb", label: "MongoDB" },
  ];

  const ENV_OPTIONS = [
    { value: "prod", label: t("instances.env_prod") },
    { value: "staging", label: t("instances.env_staging") },
    { value: "dev", label: t("instances.env_dev") },
  ];

  const load = () => {
    setLoading(true);
    api.get("/collector/instances/")
      .then(({ data }) => setInstances(data.results || data))
      .catch(() => showToast(t("instances.load_failed"), "error"))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const showToast = (msg, type = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const filteredInstances = instances.filter((i) => {
    if (filterType   && i.db_type           !== filterType)   return false;
    if (filterEnv    && i.environment       !== filterEnv)    return false;
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
    } catch (e) {
      showToast(e.response?.data?.message || t("instances.test_failed"), "error");
    }
  };

  const handleCollect = async (id) => {
    try {
      const { data } = await api.post(`/collector/instances/${id}/collect/`);
      showToast(data.message, data.success ? "success" : "error");
      load();
      if (expandedHistory === id) loadHistory(id, true);
    } catch (e) {
      showToast(e.response?.data?.message || t("instances.collect_failed"), "error");
    }
  };

  const loadHistory = useCallback(async (id, silent = false) => {
    if (!silent) setHistoryLoading(true);
    try {
      const { data } = await api.get(`/collector/instances/${id}/history/?limit=20`);
      setHistoryData((prev) => ({ ...prev, [id]: data }));
    } catch {}
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

  return (
    <AppLayout title={t("instances.title")}>
      {toast && <div className={`toast toast-${toast.type}`}>{toast.msg}</div>}

      <div className="card">
        <div className="inst-toolbar">
          <div className="inst-toolbar-left">
            <span className="inst-count">{t("instances.total", { count: filteredInstances.length })}</span>

            <select className="inst-filter-select" value={filterType} onChange={(e) => setFilterType(e.target.value)}>
              <option value="">{t("instances.col_type")}</option>
              {DB_TYPES.map((dt) => <option key={dt.value} value={dt.value}>{dt.label}</option>)}
            </select>

            <select className="inst-filter-select" value={filterEnv} onChange={(e) => setFilterEnv(e.target.value)}>
              <option value="">{t("instances.col_env")}</option>
              {ENV_OPTIONS.map((e) => <option key={e.value} value={e.value}>{e.label}</option>)}
            </select>

            <select className="inst-filter-select" value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
              <option value="">{t("instances.col_connection")}</option>
              <option value="connected">{t("instances.conn_connected")}</option>
              <option value="disconnected">{t("instances.conn_disconnected")}</option>
            </select>

            {(filterType || filterEnv || filterStatus) && (
              <button className="btn btn-sm" onClick={() => { setFilterType(""); setFilterEnv(""); setFilterStatus(""); }}>
                {t("qan.search_clear")}
              </button>
            )}
          </div>

          <div className="inst-toolbar-right">
            <button className="btn btn-primary" onClick={() => { setEditing(null); setShowModal(true); }}>
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>add</span>
              {t("instances.register")}
            </button>
          </div>
        </div>

        {loading ? (
          <div className="loading-wrap"><div className="mini-spinner" /> {t("common.loading")}</div>
        ) : filteredInstances.length === 0 ? (
          <div className="empty-state">
            <span className="material-symbols-outlined empty-state-icon">dns</span>
            <div className="empty-state-title">{t("instances.no_instances")}</div>
            <div className="empty-state-desc">{t("instances.no_instances_desc")}</div>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="sql-table">
              <thead>
                <tr>
                  <th>{t("instances.col_name")}</th>
                  <th>{t("instances.col_type")}</th>
                  <th>{t("instances.col_host")}</th>
                  <th>{t("instances.col_version")}</th>
                  <th>{t("instances.col_env")}</th>
                  <th>{t("instances.col_cluster")}</th>
                  <th>{t("instances.col_status")}</th>
                  <th>{t("instances.col_last_collect")}</th>
                  <th style={{ textAlign: "right" }}>{t("instances.col_actions")}</th>
                </tr>
              </thead>
              <tbody>
                {filteredInstances.map((inst) => (
                  <>
                    <tr key={inst.id}>
                      <td style={{ fontWeight: 600 }}>{inst.name}</td>
                      <td>
                        <span className="badge badge-info">{inst.db_type.toUpperCase()}</span>
                      </td>
                      <td className="text-mono">{inst.host}:{inst.port}</td>
                      <td className="text-mono" style={{ fontSize: 12 }}>
                        {inst.db_version || "-"}
                      </td>
                      <td>
                        <span className={`badge ${inst.environment === "prod" ? "badge-danger" : inst.environment === "staging" ? "badge-warning" : "badge-muted"}`}>
                          {ENV_OPTIONS.find(e => e.value === inst.environment)?.label || inst.environment}
                        </span>
                      </td>
                      <td>{inst.cluster || "-"}</td>
                      <td>
                        <div className="sched-status-cell">
                          {inst.connection_status === "disconnected" ? (
                            <span className="badge badge-danger" title={inst.last_error || undefined}>
                              {t("instances.conn_disconnected")}
                            </span>
                          ) : (
                            <span className={`badge ${inst.is_active ? "badge-success" : "badge-muted"}`}>
                              {inst.is_active ? t("instances.status_active") : t("instances.status_inactive")}
                            </span>
                          )}
                          {inst.is_active && (
                            <span
                              className={`sched-dot ${schedulerStatus[inst.id]?.active ? "sched-dot--running" : "sched-dot--idle"}`}
                              title={schedulerStatus[inst.id]?.active
                                ? `定时采集中 / 间隔 ${schedulerStatus[inst.id]?.interval}s`
                                : "调度器未运行"}
                            />
                          )}
                        </div>
                      </td>
                      <td className="text-muted" style={{ fontSize: 12 }}>
                        {fmtDatetime(inst.last_collected_at)}
                      </td>
                      <td style={{ textAlign: "right" }}>
                        <div className="action-group">
                          <button className="btn btn-sm btn-success" onClick={() => handleTest(inst.id)}>{t("instances.btn_test")}</button>
                          <button className="btn btn-sm btn-primary" onClick={() => handleCollect(inst.id)}>{t("instances.btn_collect")}</button>
                          <button
                            className={`btn btn-sm ${expandedHistory === inst.id ? "btn-active" : ""}`}
                            onClick={() => toggleHistory(inst.id)}
                          >
                            {t("instances.btn_history")}
                          </button>
                          <button className="btn btn-sm" onClick={() => { setEditing(inst); setShowModal(true); }}>{t("common.edit")}</button>
                          <button className="btn btn-sm btn-danger" onClick={() => handleDelete(inst.id)}>{t("common.delete")}</button>
                        </div>
                      </td>
                    </tr>
                    {expandedHistory === inst.id && (
                      <tr key={`${inst.id}-history`} className="history-row">
                        <td colSpan={9} style={{ padding: 0 }}>
                          <HistoryPanel
                            records={historyData[inst.id]}
                            loading={historyLoading}
                          />
                        </td>
                      </tr>
                    )}
                    {inst.connection_status === "disconnected" && inst.last_error && (
                      <tr key={`${inst.id}-error`} className="error-row">
                        <td colSpan={9} className="error-row-cell">
                          <span className="material-symbols-outlined" style={{ fontSize: 14, color: "var(--color-error)" }}>error</span>
                          <span className="error-row-text">{inst.last_error}</span>
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

/* ═══ 采集历史面板 ═══ */
function HistoryPanel({ records, loading }) {
  const { t } = useTranslation();
  if (loading) {
    return <div className="history-panel"><div className="loading-wrap"><div className="mini-spinner" /> {t("common.loading")}</div></div>;
  }
  if (!records) return null;
  if (records.length === 0) {
    return <div className="history-panel history-empty">{t("instances.no_history")}</div>;
  }

  return (
    <div className="history-panel">
      <table className="history-table">
        <thead>
          <tr>
            <th>{t("history.col_start")}</th>
            <th>{t("history.col_trigger")}</th>
            <th>{t("history.col_status")}</th>
            <th className="text-right">{t("history.col_duration")}</th>
            <th className="text-right">{t("history.col_queries")}</th>
            <th className="text-right">{t("history.col_rows")}</th>
            <th>{t("history.col_error")}</th>
          </tr>
        </thead>
        <tbody>
          {records.map((r) => (
            <tr key={r.id}>
              <td className="text-mono" style={{ fontSize: 12 }}>{fmtDatetime(r.started_at)}</td>
              <td>
                <span className={`badge ${r.triggered_by === "manual" ? "badge-warning" : "badge-muted"}`}>
                  {r.triggered_by === "manual" ? t("history.trigger_manual") : t("history.trigger_scheduled")}
                </span>
              </td>
              <td>
                <span className={`badge ${r.status === "success" ? "badge-success" : r.status === "partial" ? "badge-warning" : "badge-danger"}`}>
                  {r.status === "success" ? t("history.status_success") : r.status === "partial" ? t("history.status_partial") : t("history.status_failed")}
                </span>
              </td>
              <td className="text-right" style={{ fontSize: 12 }}>
                {r.duration_ms != null ? `${r.duration_ms} ms` : "—"}
              </td>
              <td className="text-right">{r.queries_collected}</td>
              <td className="text-right">{r.rows_written}</td>
              <td style={{ fontSize: 11, color: "var(--color-error-alt)", maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {r.error_message || "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ═══ 实例编辑模态框 ═══ */
function InstanceModal({ instance, onClose, onSaved }) {
  const { t } = useTranslation();
  const DB_TYPES = [
    { value: "mysql", label: "MySQL" },
    { value: "postgresql", label: "PostgreSQL" },
    { value: "mongodb", label: "MongoDB" },
  ];
  const ENV_OPTIONS = [
    { value: "prod", label: t("instances.env_prod") },
    { value: "staging", label: t("instances.env_staging") },
    { value: "dev", label: t("instances.env_dev") },
  ];

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

  const handleChange = (key, value) => setForm((f) => ({ ...f, [key]: value }));

  const handleTestConfig = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const { data } = await api.post("/collector/instances/test-config/", {
        host: form.host,
        port: form.port,
        username: form.username,
        password: form.password,
        db_type: form.db_type,
      });
      setTestResult(data);
    } catch (e) {
      setTestResult({
        success: false,
        message: e.response?.data?.message || "请求失败",
      });
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
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title">{instance ? t("instances.modal_edit") : t("instances.modal_create")}</span>
          <button className="modal-close" onClick={onClose}>
            <span className="material-symbols-outlined" style={{ fontSize: 20 }}>close</span>
          </button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            {error && <div className="alert alert-error">{error}</div>}

            <div className="form-group">
              <label className="form-label">{t("instances.field_name")}</label>
              <input className="form-input" value={form.name} onChange={(e) => handleChange("name", e.target.value)} required placeholder="db-prod-01" />
            </div>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{t("instances.field_db_type")}</label>
                <select className="form-select" value={form.db_type} onChange={(e) => handleChange("db_type", e.target.value)}>
                  {DB_TYPES.map((t2) => <option key={t2.value} value={t2.value}>{t2.label}</option>)}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">{t("instances.field_env")}</label>
                <select className="form-select" value={form.environment} onChange={(e) => handleChange("environment", e.target.value)}>
                  {ENV_OPTIONS.map((t2) => <option key={t2.value} value={t2.value}>{t2.label}</option>)}
                </select>
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{t("instances.field_host")}</label>
                <input className="form-input" value={form.host} onChange={(e) => handleChange("host", e.target.value)} required placeholder="192.168.1.100" />
              </div>
              <div className="form-group">
                <label className="form-label">{t("instances.field_port")}</label>
                <input className="form-input" type="number" value={form.port} onChange={(e) => handleChange("port", parseInt(e.target.value))} required />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{t("instances.field_username")}</label>
                <input className="form-input" value={form.username} onChange={(e) => handleChange("username", e.target.value)} required />
              </div>
              <div className="form-group">
                <label className="form-label">{t("instances.field_password")}</label>
                <input className="form-input" type="password" value={form.password} onChange={(e) => handleChange("password", e.target.value)} placeholder={instance ? t("instances.pwd_placeholder") : ""} />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">{t("instances.field_cluster")}</label>
                <input className="form-input" value={form.cluster} onChange={(e) => handleChange("cluster", e.target.value)} placeholder={t("instances.cluster_optional")} />
              </div>
              <div className="form-group">
                <label className="form-label">{t("instances.field_interval")}</label>
                <input className="form-input" type="number" value={form.collect_interval} onChange={(e) => handleChange("collect_interval", parseInt(e.target.value))} />
              </div>
            </div>

            <div className="form-group" style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={form.is_active} onChange={(e) => handleChange("is_active", e.target.checked)} id="active-check" />
              <label htmlFor="active-check" style={{ fontSize: 13, cursor: "pointer", color: "var(--color-text)" }}>{t("instances.field_active")}</label>
            </div>

            {testResult && (
              <div className={`test-result-banner ${testResult.success ? "test-result-ok" : "test-result-fail"}`}>
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                  {testResult.success ? "check_circle" : "error"}
                </span>
                <span>{testResult.message}</span>
                {testResult.version && (
                  <span className="test-result-version">{testResult.version}</span>
                )}
              </div>
            )}
          </div>

          <div className="modal-footer">
            <button type="button" className="btn" onClick={onClose}>{t("common.cancel")}</button>
            <button type="button" className="btn btn-success" disabled={testing || !form.host || (!instance && !form.password)}
              onClick={handleTestConfig}>
              {testing ? t("common.loading") : t("instances.btn_test")}
            </button>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? t("common.saving") : t("common.save")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
