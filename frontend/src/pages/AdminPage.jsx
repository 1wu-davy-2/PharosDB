import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useAuth, usePerm } from "../context/AuthContext";
import api from "../services/api";
import AppLayout from "../components/AppLayout";
import "./AdminPage.css";

export default function AdminPage() {
  const { t, i18n } = useTranslation();
  const { user: me } = useAuth();
  const navigate = useNavigate();
  const isZh = i18n.language === "zh";

  const canManageUsers = usePerm("system:users");
  const canView = usePerm("system:view");

  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [roles, setRoles] = useState([]);
  const [msg, setMsg] = useState(null);

  // Create user modal
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);

  // Reset password modal
  const [resetOpen, setResetOpen] = useState(false);
  const [resetUser, setResetUser] = useState(null);
  const [resetting, setResetting] = useState(false);

  // ── Guard: need system:view permission ──
  useEffect(() => {
    if (me && !canView && !me.is_superuser) {
      navigate("/", { replace: true });
    }
  }, [me, navigate, canView]);

  // ── Load users ──
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [usersRes, rolesRes] = await Promise.all([
        api.get("/auth/users/"),
        api.get("/auth/roles/"),
      ]);
      setUsers(usersRes.data.users || []);
      setRoles(rolesRes.data.roles || []);
    } catch {
      setMsg({ type: "error", text: isZh ? "加载用户列表失败" : "Failed to load users" });
    } finally {
      setLoading(false);
    }
  }, [isZh]);

  useEffect(() => { if (me && canView) load(); }, [load, me, canView]);

  // ── Create user ──
  const handleCreate = async (e) => {
    e.preventDefault();
    setCreating(true);
    const form = e.target;
    const username = form.username.value.trim();
    const email = form.email.value.trim();
    const password = form.password.value;
    const is_superuser = form.is_superuser.checked;

    if (!username || !password) { setCreating(false); return; }

    try {
      await api.post("/auth/users/", { username, email, password, is_superuser });
      setMsg({ type: "success", text: `用户 ${username} 创建成功` });
      setCreateOpen(false);
      form.reset();
      load();
    } catch (e) {
      setMsg({ type: "error", text: e.response?.data?.error || (e.response?.data?.username?.[0]) || "创建失败" });
    } finally {
      setCreating(false);
    }
  };

  // ── Reset password ──
  const openReset = (user) => { setResetUser(user); setResetOpen(true); };

  const handleReset = async (e) => {
    e.preventDefault();
    setResetting(true);
    const new_password = e.target.new_password.value;
    if (!new_password || new_password.length < 6) { setResetting(false); return; }

    try {
      await api.put(`/auth/users/${resetUser.id}/reset-password/`, { new_password });
      setMsg({ type: "success", text: `用户 ${resetUser.username} 密码已重置` });
      setResetting(false);
      setResetOpen(false);
      setResetUser(null);
    } catch (e) {
      setMsg({ type: "error", text: e.response?.data?.error || "重置失败" });
    } finally {
      setResetting(false);
    }
  };

  // ── Unlock ──
  const handleUnlock = async (user) => {
    try {
      const { data } = await api.post(`/auth/users/${user.id}/unlock/`);
      setMsg({ type: "success", text: data.detail || "已解锁" });
      load();
    } catch {
      setMsg({ type: "error", text: isZh ? "解锁失败" : "Unlock failed" });
    }
  };

  // ── Delete / Deactivate ──
  const handleDelete = async (user) => {
    const label = isZh
      ? `确定要删除用户 ${user.username} 吗？此操作不可逆。`
      : `Delete user ${user.username}? This cannot be undone.`;
    if (!window.confirm(label)) return;

    try {
      await api.delete(`/auth/users/${user.id}/`);
      setMsg({ type: "success", text: isZh ? `用户 ${user.username} 已删除` : `User ${user.username} deleted` });
      load();
    } catch (e) {
      setMsg({ type: "error", text: e.response?.data?.error || "删除失败" });
    }
  };

  const handleToggleActive = async (user) => {
    const next = !user.is_active;
    const label = next
      ? (isZh ? `启用用户 ${user.username}？` : `Enable user ${user.username}?`)
      : (isZh ? `禁用用户 ${user.username}？` : `Disable user ${user.username}?`);
    if (!window.confirm(label)) return;

    try {
      if (next) {
        // Re-enable: set is_active=True
        await api.patch(`/auth/users/${user.id}/`, { is_active: true });
      } else {
        // Deactivate
        await api.delete(`/auth/users/${user.id}/?action=deactivate`);
      }
      load();
    } catch {
      setMsg({ type: "error", text: "操作失败" });
    }
  };

  const formatTime = (dt) => {
    if (!dt) return "—";
    return dt.replace("T", " ").slice(0, 19);
  };

  // ── Role assignment ──
  const handleAssignRole = async (userId, roleId) => {
    try {
      if (roleId === "") {
        await api.delete(`/auth/users/${userId}/role/`);
      } else {
        await api.put(`/auth/users/${userId}/role/`, { role_id: roleId });
      }
      load();
    } catch (e) {
      setMsg({ type: "error", text: e.response?.data?.error || "角色分配失败" });
    }
  };

  if (!me?.is_superuser && !canView) return null;

  return (
    <AppLayout title={isZh ? "系统管理" : "System Admin"}>
      <div className="admin-page">
        {msg && (
          <div className={`admin-msg admin-msg--${msg.type}`}>
            {msg.text}
            <button className="admin-msg-close" onClick={() => setMsg(null)}>
              <span className="material-symbols-outlined" style={{ fontSize: 14 }}>close</span>
            </button>
          </div>
        )}

        {/* ── Toolbar ── */}
        <div className="admin-toolbar">
          <span className="admin-toolbar-count">
            {isZh ? `共 ${users.length} 个用户` : `${users.length} users total`}
          </span>
          {canManageUsers && (
            <button className="admin-btn admin-btn--primary" onClick={() => { setCreateOpen(true); setMsg(null); }}>
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>person_add</span>
              {isZh ? "创建用户" : "Create User"}
            </button>
          )}
        </div>

        {/* ── User table ── */}
        {loading ? (
          <div className="loading-wrap"><div className="mini-spinner" /> {t("common.loading")}</div>
        ) : (
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>{isZh ? "用户名" : "Username"}</th>
                  <th>{isZh ? "邮箱" : "Email"}</th>
                  <th>{isZh ? "角色" : "Role"}</th>
                  <th>{isZh ? "状态" : "Status"}</th>
                  <th>{isZh ? "上次登录" : "Last Login"}</th>
                  <th>{isZh ? "注册时间" : "Joined"}</th>
                  <th>{isZh ? "失败尝试" : "Failures"}</th>
                  <th>{isZh ? "操作" : "Actions"}</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} className={!u.is_active ? "admin-row--disabled" : ""}>
                    <td>
                      <span className="admin-username">{u.username}</span>
                      {u.id === me.id && (
                        <span className="admin-tag admin-tag--me">{isZh ? "我" : "me"}</span>
                      )}
                    </td>
                    <td className="admin-email">{u.email || "—"}</td>
                    <td className="admin-role-cell">
                      {canManageUsers ? (
                        <select
                          className="admin-role-sel"
                          value={u.role_id || ""}
                          onChange={(e) => handleAssignRole(u.id, e.target.value ? parseInt(e.target.value, 10) : "")}
                        >
                          <option value="">—</option>
                          {roles.map((r) => (
                            <option key={r.id} value={r.id}>{r.display_name}</option>
                          ))}
                        </select>
                      ) : (
                        <span className="admin-tag admin-tag--user">
                          {u.role_name || (isZh ? "无角色" : "None")}
                        </span>
                      )}
                    </td>
                    <td>
                      <span className={`admin-status ${u.is_active ? "admin-status--active" : "admin-status--disabled"}`}>
                        {u.is_active ? (isZh ? "启用" : "Active") : (isZh ? "禁用" : "Disabled")}
                      </span>
                    </td>
                    <td className="admin-time">{formatTime(u.last_login)}</td>
                    <td className="admin-time">{formatTime(u.date_joined)}</td>
                    <td>
                      {u.failed_attempts > 0 ? (
                        <span className="admin-failures">{u.failed_attempts}</span>
                      ) : (
                        <span className="admin-failures-zero">0</span>
                      )}
                    </td>
                    <td>
                      {canManageUsers && (
                        <div className="admin-actions">
                          {u.failed_attempts > 0 && (
                            <button className="admin-action-btn admin-action-btn--unlock" onClick={() => handleUnlock(u)} title={isZh ? "解锁" : "Unlock"}>
                              <span className="material-symbols-outlined" style={{ fontSize: 15 }}>lock_open</span>
                            </button>
                          )}
                          <button className="admin-action-btn admin-action-btn--reset" onClick={() => openReset(u)} title={isZh ? "重置密码" : "Reset PW"}>
                            <span className="material-symbols-outlined" style={{ fontSize: 15 }}>key</span>
                          </button>
                          {u.id !== me.id && (
                            <>
                              <button className="admin-action-btn" onClick={() => handleToggleActive(u)} title={u.is_active ? (isZh ? "禁用" : "Disable") : (isZh ? "启用" : "Enable")}>
                                <span className="material-symbols-outlined" style={{ fontSize: 15 }}>
                                  {u.is_active ? "block" : "check_circle"}
                                </span>
                              </button>
                              <button className="admin-action-btn admin-action-btn--danger" onClick={() => handleDelete(u)} title={isZh ? "删除" : "Delete"}>
                                <span className="material-symbols-outlined" style={{ fontSize: 15 }}>delete</span>
                              </button>
                            </>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* ═══ Create User Modal ═══ */}
        {createOpen && (
          <div className="admin-modal-overlay" onClick={() => setCreateOpen(false)}>
            <form className="admin-modal" onClick={(e) => e.stopPropagation()} onSubmit={handleCreate}>
              <div className="admin-modal-header">
                <span className="admin-modal-title">{isZh ? "创建用户" : "Create User"}</span>
                <button type="button" className="admin-modal-close" onClick={() => setCreateOpen(false)}>
                  <span className="material-symbols-outlined">close</span>
                </button>
              </div>
              <div className="admin-modal-body">
                <label className="admin-modal-label">{isZh ? "用户名" : "Username"} *</label>
                <input name="username" className="admin-modal-input" placeholder={isZh ? "登录用户名" : "Login username"} required autoFocus />
                <label className="admin-modal-label">{isZh ? "邮箱" : "Email"}</label>
                <input name="email" type="email" className="admin-modal-input" placeholder="user@example.com" />
                <label className="admin-modal-label">{isZh ? "密码" : "Password"} *</label>
                <input name="password" type="password" className="admin-modal-input" placeholder={isZh ? "至少 6 位" : "Min 6 chars"} required />
                <label className="admin-modal-check-label">
                  <input name="is_superuser" type="checkbox" />
                  <span>{isZh ? "设为超级管理员" : "Grant superuser role"}</span>
                </label>
              </div>
              <div className="admin-modal-footer">
                <button type="button" className="admin-modal-cancel" onClick={() => setCreateOpen(false)}>
                  {t("common.cancel")}
                </button>
                <button type="submit" className="admin-btn admin-btn--primary" disabled={creating}>
                  {creating ? (isZh ? "创建中..." : "Creating...") : t("common.save")}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* ═══ Reset Password Modal ═══ */}
        {resetOpen && resetUser && (
          <div className="admin-modal-overlay" onClick={() => { setResetOpen(false); setResetUser(null); }}>
            <form className="admin-modal" onClick={(e) => e.stopPropagation()} onSubmit={handleReset}>
              <div className="admin-modal-header">
                <span className="admin-modal-title">
                  {isZh ? `重置密码 — ${resetUser.username}` : `Reset Password — ${resetUser.username}`}
                </span>
                <button type="button" className="admin-modal-close" onClick={() => { setResetOpen(false); setResetUser(null); }}>
                  <span className="material-symbols-outlined">close</span>
                </button>
              </div>
              <div className="admin-modal-body">
                <label className="admin-modal-label">{isZh ? "新密码" : "New Password"} *</label>
                <input name="new_password" type="password" className="admin-modal-input" placeholder={isZh ? "至少 6 位" : "Min 6 chars"} required autoFocus />
              </div>
              <div className="admin-modal-footer">
                <button type="button" className="admin-modal-cancel" onClick={() => { setResetOpen(false); setResetUser(null); }}>
                  {t("common.cancel")}
                </button>
                <button type="submit" className="admin-btn admin-btn--primary" disabled={resetting}>
                  {resetting ? (isZh ? "重置中..." : "Resetting...") : (isZh ? "重置密码" : "Reset")}
                </button>
              </div>
            </form>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
