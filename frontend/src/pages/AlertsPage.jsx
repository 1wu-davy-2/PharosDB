import { useCallback, useEffect, useState } from "react";
import api from "../services/api";
import AppLayout from "../components/AppLayout";
import "./AlertsPage.css";

const RULE_TYPES = [
  { value: "slow_query_time", label: "慢查询耗时", unit: "秒", hint: "周期内平均执行时间 > 阈值 的查询条数 > 0 则触发" },
  { value: "no_index_ratio",  label: "无索引比例", unit: "%",  hint: "周期内无索引查询占总查询的百分比 > 阈值" },
  { value: "query_count",     label: "查询总量",   unit: "次", hint: "周期内总查询次数 > 阈值" },
  { value: "custom_sql",      label: "自定义 SQL", unit: "",   hint: "查询返回单个数值与阈值比较" },
];

const SEVERITIES = [
  { value: "warning",  label: "警告",  color: "#f59e0b" },
  { value: "critical", label: "严重",  color: "#ba1a1a" },
];

const PERIODS = [1, 5, 15, 30, 60];

function fmtDatetime(val) {
  if (!val) return "—";
  const d = new Date(val);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function fmtDuration(secs) {
  if (!secs) return "—";
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.floor(secs/60)}m ${secs%60}s`;
  return `${Math.floor(secs/3600)}h ${Math.floor((secs%3600)/60)}m`;
}

export default function AlertsPage() {
  const [tab, setTab] = useState("rules");
  const [rules, setRules] = useState([]);
  const [events, setEvents] = useState([]);
  const [summary, setSummary] = useState({ warning: 0, critical: 0, total: 0 });
  const [instances, setInstances] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState(null);
  const [toast, setToast] = useState(null);
  const [eventFilter, setEventFilter] = useState("firing");

  const showToast = (msg, type = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const loadAll = useCallback(() => {
    setLoading(true);
    Promise.all([
      api.get("/alerts/rules/"),
      api.get("/alerts/events/summary/"),
      api.get("/collector/instances/"),
    ]).then(([rRes, sRes, iRes]) => {
      setRules(rRes.data.results || rRes.data);
      setSummary(sRes.data);
      setInstances(iRes.data.results || iRes.data);
    }).catch(() => showToast("加载失败", "error"))
      .finally(() => setLoading(false));
  }, []);

  const loadEvents = useCallback(() => {
    const params = eventFilter ? `?status=${eventFilter}` : "";
    api.get(`/alerts/events/${params}`)
      .then(({ data }) => setEvents(data.results || data))
      .catch(() => {});
  }, [eventFilter]);

  useEffect(() => { loadAll(); }, [loadAll]);
  useEffect(() => { if (tab === "events") loadEvents(); }, [tab, loadEvents]);

  const handleDelete = async (id) => {
    if (!confirm("确定删除此规则？")) return;
    try {
      await api.delete(`/alerts/rules/${id}/`);
      showToast("已删除");
      loadAll();
    } catch { showToast("删除失败", "error"); }
  };

  const handleToggle = async (id) => {
    try {
      const { data } = await api.post(`/alerts/rules/${id}/toggle/`);
      setRules((prev) => prev.map((r) => r.id === id ? { ...r, is_enabled: data.is_enabled } : r));
    } catch { showToast("操作失败", "error"); }
  };

  const handleTest = async (id) => {
    try {
      const { data } = await api.post(`/alerts/rules/${id}/test/`);
      const lines = data.results.map((r) =>
        `${r.instance}: ${r.metric_value?.toFixed(3) ?? "无数据"} ${r.would_fire ? "🔴 触发" : "✅ 正常"}`
      ).join("\n");
      alert(`规则: ${data.rule}\n\n${lines}`);
    } catch { showToast("测试失败", "error"); }
  };

  return (
    <AppLayout title="告警中心">
      {toast && <div className={`toast toast-${toast.type}`}>{toast.msg}</div>}

      {/* 汇总卡片 */}
      <div className="alert-summary-row">
        <div className="alert-summary-card alert-summary-total">
          <span className="alert-summary-num">{summary.total}</span>
          <span className="alert-summary-label">当前告警</span>
        </div>
        <div className="alert-summary-card alert-summary-warning">
          <span className="alert-summary-num">{summary.warning}</span>
          <span className="alert-summary-label">警告</span>
        </div>
        <div className="alert-summary-card alert-summary-critical">
          <span className="alert-summary-num">{summary.critical}</span>
          <span className="alert-summary-label">严重</span>
        </div>
        <div className="alert-summary-card">
          <span className="alert-summary-num">{rules.filter(r => r.is_enabled).length}</span>
          <span className="alert-summary-label">活跃规则</span>
        </div>
      </div>

      {/* Tab 切换 */}
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <div className="alert-tabs">
          <button className={`alert-tab ${tab === "rules" ? "alert-tab--active" : ""}`} onClick={() => setTab("rules")}>
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>rule</span>
            告警规则
          </button>
          <button className={`alert-tab ${tab === "events" ? "alert-tab--active" : ""}`} onClick={() => setTab("events")}>
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>notifications</span>
            告警事件
            {summary.total > 0 && <span className="alert-badge">{summary.total}</span>}
          </button>
          {tab === "rules" && (
            <button className="btn btn-primary btn-sm" style={{ marginLeft: "auto", marginRight: 16 }}
              onClick={() => { setEditing(null); setShowModal(true); }}>
              <span className="material-symbols-outlined" style={{ fontSize: 15 }}>add</span>
              新建规则
            </button>
          )}
          {tab === "events" && (
            <div style={{ marginLeft: "auto", marginRight: 16, display: "flex", gap: 6 }}>
              {["firing", "resolved", ""].map((s) => (
                <button key={s} className={`btn btn-sm ${eventFilter === s ? "btn-active" : ""}`}
                  onClick={() => setEventFilter(s)}>
                  {s === "firing" ? "告警中" : s === "resolved" ? "已恢复" : "全部"}
                </button>
              ))}
            </div>
          )}
        </div>

        {tab === "rules" && (
          <RulesTable rules={rules} loading={loading}
            onEdit={(r) => { setEditing(r); setShowModal(true); }}
            onDelete={handleDelete}
            onToggle={handleToggle}
            onTest={handleTest}
          />
        )}

        {tab === "events" && (
          <EventsTable events={events} />
        )}
      </div>

      {showModal && (
        <RuleModal
          rule={editing}
          instances={instances}
          onClose={() => setShowModal(false)}
          onSaved={() => { setShowModal(false); loadAll(); showToast(editing ? "已更新" : "已创建"); }}
        />
      )}
    </AppLayout>
  );
}

/* ═══ 规则列表 ═══ */
function RulesTable({ rules, loading, onEdit, onDelete, onToggle, onTest }) {
  if (loading) return <div className="loading-wrap"><div className="mini-spinner" /> 加载中...</div>;
  if (!rules.length) return (
    <div className="empty-state">
      <span className="material-symbols-outlined empty-state-icon">notifications_off</span>
      <div className="empty-state-title">暂无告警规则</div>
      <div className="empty-state-desc">点击「新建规则」创建第一条告警规则</div>
    </div>
  );

  return (
    <div className="table-wrap">
      <table className="sql-table">
        <thead>
          <tr>
            <th>规则名称</th>
            <th>类型</th>
            <th>实例</th>
            <th className="text-right">阈值</th>
            <th className="text-right">周期</th>
            <th>级别</th>
            <th>状态</th>
            <th className="text-right">当前告警</th>
            <th style={{ textAlign: "right" }}>操作</th>
          </tr>
        </thead>
        <tbody>
          {rules.map((r) => (
            <tr key={r.id}>
              <td style={{ fontWeight: 600 }}>{r.name}</td>
              <td><span className="badge badge-info">{RULE_TYPES.find(t => t.value === r.rule_type)?.label || r.rule_type}</span></td>
              <td className="text-muted">{r.instance_name || <span style={{ color: "#534434", fontSize: 11 }}>ALL</span>}</td>
              <td className="text-right font-medium">{r.threshold} {RULE_TYPES.find(t => t.value === r.rule_type)?.unit}</td>
              <td className="text-right text-muted">{r.period} 分钟</td>
              <td>
                <span className="badge" style={{ background: SEVERITIES.find(s => s.value === r.severity)?.color + "22", color: SEVERITIES.find(s => s.value === r.severity)?.color }}>
                  {SEVERITIES.find(s => s.value === r.severity)?.label}
                </span>
              </td>
              <td>
                <span className={`badge ${r.is_enabled ? "badge-success" : "badge-muted"}`}>
                  {r.is_enabled ? "启用" : "禁用"}
                </span>
              </td>
              <td className="text-right">
                {r.firing_count > 0
                  ? <span style={{ color: "#ba1a1a", fontWeight: 700 }}>{r.firing_count}</span>
                  : <span className="text-muted">0</span>}
              </td>
              <td style={{ textAlign: "right" }}>
                <div className="action-group">
                  <button className="btn btn-sm" onClick={() => onTest(r.id)} title="测试规则">测试</button>
                  <button className="btn btn-sm" onClick={() => onToggle(r.id)}>{r.is_enabled ? "禁用" : "启用"}</button>
                  <button className="btn btn-sm" onClick={() => onEdit(r)}>编辑</button>
                  <button className="btn btn-sm btn-danger" onClick={() => onDelete(r.id)}>删除</button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ═══ 事件列表 ═══ */
function EventsTable({ events }) {
  if (!events.length) return (
    <div className="empty-state">
      <span className="material-symbols-outlined empty-state-icon">check_circle</span>
      <div className="empty-state-title">无告警事件</div>
    </div>
  );

  return (
    <div className="table-wrap">
      <table className="sql-table">
        <thead>
          <tr>
            <th>规则名称</th>
            <th>类型</th>
            <th>实例</th>
            <th>级别</th>
            <th className="text-right">指标值</th>
            <th className="text-right">阈值</th>
            <th>状态</th>
            <th>触发时间</th>
            <th>持续时长</th>
          </tr>
        </thead>
        <tbody>
          {events.map((e) => (
            <tr key={e.id}>
              <td style={{ fontWeight: 600 }}>{e.rule_name}</td>
              <td><span className="badge badge-info">{RULE_TYPES.find(t => t.value === e.rule_type)?.label || e.rule_type}</span></td>
              <td className="text-muted">{e.instance_name || "ALL"}</td>
              <td>
                <span className="badge" style={{ background: SEVERITIES.find(s => s.value === e.severity)?.color + "22", color: SEVERITIES.find(s => s.value === e.severity)?.color }}>
                  {SEVERITIES.find(s => s.value === e.severity)?.label}
                </span>
              </td>
              <td className="text-right font-medium" style={{ color: e.status === "firing" ? "#ba1a1a" : undefined }}>
                {e.metric_value?.toFixed(3)}
              </td>
              <td className="text-right text-muted">{e.threshold}</td>
              <td>
                <span className={`badge ${e.status === "firing" ? "badge-danger" : "badge-muted"}`}>
                  {e.status === "firing" ? "告警中" : "已恢复"}
                </span>
              </td>
              <td style={{ fontSize: 12 }}>{fmtDatetime(e.fired_at)}</td>
              <td style={{ fontSize: 12 }}>{fmtDuration(e.duration)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ═══ 规则编辑模态框 ═══ */
function RuleModal({ rule, instances, onClose, onSaved }) {
  const [form, setForm] = useState({
    name:        rule?.name        || "",
    rule_type:   rule?.rule_type   || "slow_query_time",
    instance:    rule?.instance    || null,
    threshold:   rule?.threshold   ?? 1,
    period:      rule?.period      || 5,
    severity:    rule?.severity    || "warning",
    webhook_url: rule?.webhook_url || "",
    custom_sql:  rule?.custom_sql  || "",
    description: rule?.description || "",
    is_enabled:  rule?.is_enabled  ?? true,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const ruleTypeMeta = RULE_TYPES.find(t => t.value === form.rule_type);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const payload = { ...form, instance: form.instance || null };
      if (rule) await api.put(`/alerts/rules/${rule.id}/`, payload);
      else      await api.post("/alerts/rules/", payload);
      onSaved();
    } catch (err) {
      const msg = err.response?.data;
      setError(typeof msg === "object" ? JSON.stringify(msg) : String(msg));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal--wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title">{rule ? "编辑规则" : "新建规则"}</span>
          <button className="modal-close" onClick={onClose}>
            <span className="material-symbols-outlined" style={{ fontSize: 20 }}>close</span>
          </button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            {error && <div className="alert alert-error">{error}</div>}

            <div className="form-group">
              <label className="form-label">规则名称</label>
              <input className="form-input" value={form.name} onChange={(e) => set("name", e.target.value)} required />
            </div>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">规则类型</label>
                <select className="form-select" value={form.rule_type} onChange={(e) => set("rule_type", e.target.value)}>
                  {RULE_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
                {ruleTypeMeta && <div style={{ fontSize: 11, color: "#534434", marginTop: 4 }}>{ruleTypeMeta.hint}</div>}
              </div>
              <div className="form-group">
                <label className="form-label">绑定实例 <span style={{ color: "#534434", fontWeight: 400 }}>(留空=全部)</span></label>
                <select className="form-select" value={form.instance || ""} onChange={(e) => set("instance", e.target.value ? Number(e.target.value) : null)}>
                  <option value="">全部实例</option>
                  {instances.map(i => <option key={i.id} value={i.id}>{i.name}</option>)}
                </select>
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">阈值 {ruleTypeMeta?.unit && <span style={{ color: "#534434" }}>({ruleTypeMeta.unit})</span>}</label>
                <input className="form-input" type="number" step="any" value={form.threshold} onChange={(e) => set("threshold", parseFloat(e.target.value))} required />
              </div>
              <div className="form-group">
                <label className="form-label">统计周期 (分钟)</label>
                <select className="form-select" value={form.period} onChange={(e) => set("period", Number(e.target.value))}>
                  {PERIODS.map(p => <option key={p} value={p}>{p} 分钟</option>)}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">严重级别</label>
                <select className="form-select" value={form.severity} onChange={(e) => set("severity", e.target.value)}>
                  {SEVERITIES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                </select>
              </div>
            </div>

            {form.rule_type === "custom_sql" && (
              <div className="form-group">
                <label className="form-label">自定义 SQL</label>
                <textarea className="form-input" rows={4} value={form.custom_sql}
                  onChange={(e) => set("custom_sql", e.target.value)}
                  placeholder="SELECT count() FROM pharos_db.metrics WHERE service_name = %(service)s AND ..." />
              </div>
            )}

            <div className="form-group">
              <label className="form-label">Webhook URL <span style={{ color: "#534434", fontWeight: 400 }}>(可选)</span></label>
              <input className="form-input" type="url" value={form.webhook_url} onChange={(e) => set("webhook_url", e.target.value)}
                placeholder="https://hooks.example.com/alert" />
            </div>

            <div className="form-group">
              <label className="form-label">描述 <span style={{ color: "#534434", fontWeight: 400 }}>(可选)</span></label>
              <input className="form-input" value={form.description} onChange={(e) => set("description", e.target.value)} />
            </div>

            <div className="form-group" style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input type="checkbox" id="rule-enabled" checked={form.is_enabled} onChange={(e) => set("is_enabled", e.target.checked)} />
              <label htmlFor="rule-enabled" style={{ fontSize: 13, cursor: "pointer" }}>立即启用</label>
            </div>
          </div>

          <div className="modal-footer">
            <button type="button" className="btn" onClick={onClose}>取消</button>
            <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? "保存中..." : "保存"}</button>
          </div>
        </form>
      </div>
    </div>
  );
}
