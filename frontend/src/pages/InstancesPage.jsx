import { useEffect, useState } from "react";
import api from "../services/api";
import AppLayout from "../components/AppLayout";
import "./InstancesPage.css";

const DB_TYPES = [
  { value: "mysql", label: "MySQL" },
  { value: "postgresql", label: "PostgreSQL" },
  { value: "mongodb", label: "MongoDB" },
];

const ENV_OPTIONS = [
  { value: "prod", label: "生产" },
  { value: "staging", label: "预发" },
  { value: "dev", label: "开发" },
];

export default function InstancesPage() {
  const [instances, setInstances] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editing, setEditing] = useState(null);
  const [toast, setToast] = useState(null);

  const load = () => {
    setLoading(true);
    api.get("/collector/instances/")
      .then(({ data }) => setInstances(data.results || data))
      .catch(() => showToast("加载失败", "error"))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const showToast = (msg, type = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  const handleDelete = async (id) => {
    if (!confirm("确定删除此实例？")) return;
    try {
      await api.delete(`/collector/instances/${id}/`);
      showToast("已删除");
      load();
    } catch { showToast("删除失败", "error"); }
  };

  const handleTest = async (id) => {
    try {
      const { data } = await api.post(`/collector/instances/${id}/test/`);
      showToast(data.message, data.success ? "success" : "error");
    } catch (e) {
      showToast(e.response?.data?.message || "测试失败", "error");
    }
  };

  const handleCollect = async (id) => {
    try {
      const { data } = await api.post(`/collector/instances/${id}/collect/`);
      showToast(data.message, data.success ? "success" : "error");
      load();
    } catch (e) {
      showToast(e.response?.data?.message || "采集失败", "error");
    }
  };

  return (
    <AppLayout title="实例管理">
      {toast && <div className={`toast toast-${toast.type}`}>{toast.msg}</div>}

      <div className="card">
        <div className="page-toolbar" style={{ marginBottom: 16 }}>
          <div className="page-toolbar-left">
            <span style={{ fontSize: 14, color: "#534434" }}>
              共 {instances.length} 个实例
            </span>
          </div>
          <div className="page-toolbar-right">
            <button className="btn btn-primary" onClick={() => { setEditing(null); setShowModal(true); }}>
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>add</span>
              注册实例
            </button>
          </div>
        </div>

        {loading ? (
          <div className="loading-wrap"><div className="mini-spinner" /> 加载中...</div>
        ) : instances.length === 0 ? (
          <div className="empty-state">
            <span className="material-symbols-outlined empty-state-icon">dns</span>
            <div className="empty-state-title">暂无实例</div>
            <div className="empty-state-desc">点击「注册实例」添加第一个要监控的数据库</div>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="sql-table">
              <thead>
                <tr>
                  <th>名称</th>
                  <th>类型</th>
                  <th>地址</th>
                  <th>环境</th>
                  <th>集群</th>
                  <th>状态</th>
                  <th>上次采集</th>
                  <th style={{ textAlign: "right" }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {instances.map((inst) => (
                  <tr key={inst.id}>
                    <td style={{ fontWeight: 600 }}>{inst.name}</td>
                    <td>
                      <span className="badge badge-info">{inst.db_type.toUpperCase()}</span>
                    </td>
                    <td className="text-mono">{inst.host}:{inst.port}</td>
                    <td>
                      <span className={`badge ${inst.environment === "prod" ? "badge-danger" : inst.environment === "staging" ? "badge-warning" : "badge-muted"}`}>
                        {ENV_OPTIONS.find(e => e.value === inst.environment)?.label || inst.environment}
                      </span>
                    </td>
                    <td>{inst.cluster || "-"}</td>
                    <td>
                      <span className={`badge ${inst.is_active ? "badge-success" : "badge-muted"}`}>
                        {inst.is_active ? "采集" : "停用"}
                      </span>
                    </td>
                    <td className="text-muted" style={{ fontSize: 12 }}>
                      {inst.last_collected_at || "从未采集"}
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <div className="action-group">
                        <button className="btn btn-sm btn-success" onClick={() => handleTest(inst.id)} title="测试连接">
                          连接
                        </button>
                        <button className="btn btn-sm btn-primary" onClick={() => handleCollect(inst.id)} title="手动采集">
                          采集
                        </button>
                        <button className="btn btn-sm" onClick={() => { setEditing(inst); setShowModal(true); }} title="编辑">
                          编辑
                        </button>
                        <button className="btn btn-sm btn-danger" onClick={() => handleDelete(inst.id)} title="删除">
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
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
          onSaved={() => { setShowModal(false); load(); showToast(editing ? "已更新" : "已创建"); }}
        />
      )}
    </AppLayout>
  );
}

/* ═══ 实例编辑模态框 ═══ */
function InstanceModal({ instance, onClose, onSaved }) {
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

  const handleChange = (key, value) => setForm((f) => ({ ...f, [key]: value }));

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
          <span className="modal-title">{instance ? "编辑实例" : "注册实例"}</span>
          <button className="modal-close" onClick={onClose}>
            <span className="material-symbols-outlined" style={{ fontSize: 20 }}>close</span>
          </button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            {error && <div className="alert alert-error">{error}</div>}

            <div className="form-group">
              <label className="form-label">名称</label>
              <input className="form-input" value={form.name} onChange={(e) => handleChange("name", e.target.value)} required placeholder="如: db-prod-01" />
            </div>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">数据库类型</label>
                <select className="form-select" value={form.db_type} onChange={(e) => handleChange("db_type", e.target.value)}>
                  {DB_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">环境</label>
                <select className="form-select" value={form.environment} onChange={(e) => handleChange("environment", e.target.value)}>
                  {ENV_OPTIONS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">主机地址</label>
                <input className="form-input" value={form.host} onChange={(e) => handleChange("host", e.target.value)} required placeholder="192.168.1.100" />
              </div>
              <div className="form-group">
                <label className="form-label">端口</label>
                <input className="form-input" type="number" value={form.port} onChange={(e) => handleChange("port", parseInt(e.target.value))} required />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">用户名</label>
                <input className="form-input" value={form.username} onChange={(e) => handleChange("username", e.target.value)} required />
              </div>
              <div className="form-group">
                <label className="form-label">密码</label>
                <input className="form-input" type="password" value={form.password} onChange={(e) => handleChange("password", e.target.value)} placeholder={instance ? "留空不修改" : ""} />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">集群</label>
                <input className="form-input" value={form.cluster} onChange={(e) => handleChange("cluster", e.target.value)} placeholder="可选" />
              </div>
              <div className="form-group">
                <label className="form-label">采集间隔 (秒)</label>
                <input className="form-input" type="number" value={form.collect_interval} onChange={(e) => handleChange("collect_interval", parseInt(e.target.value))} />
              </div>
            </div>

            <div className="form-group" style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={form.is_active} onChange={(e) => handleChange("is_active", e.target.checked)} id="active-check" />
              <label htmlFor="active-check" style={{ fontSize: 13, cursor: "pointer" }}>启用自动采集</label>
            </div>
          </div>

          <div className="modal-footer">
            <button type="button" className="btn" onClick={onClose}>取消</button>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? "保存中..." : "保存"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
