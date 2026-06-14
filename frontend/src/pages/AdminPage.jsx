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

  const [adminTab, setAdminTab] = useState("users");
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [permGroups, setPermGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState(null);

  // User modals
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [resetUser, setResetUser] = useState(null);
  const [resetting, setResetting] = useState(false);

  // Role modal
  const [roleModalOpen, setRoleModalOpen] = useState(false);
  const [editingRole, setEditingRole] = useState(null);

  // ── Guard ──
  useEffect(() => {
    if (me && !canView && !me.is_superuser) { navigate("/", { replace: true }); }
  }, [me, navigate, canView]);

  // ── Load ──
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [usersRes, rolesRes, permsRes] = await Promise.all([
        api.get("/auth/users/"),
        api.get("/auth/roles/"),
        api.get("/auth/permissions/"),
      ]);
      setUsers(usersRes.data.users || []);
      setRoles(rolesRes.data.roles || []);
      setPermGroups(permsRes.data.groups || []);
    } catch {
      setMsg({ type: "error", text: isZh ? "加载数据失败" : "Failed to load" });
    } finally {
      setLoading(false);
    }
  }, [isZh]);

  useEffect(() => { if (me && canView) load(); }, [load, me, canView]);

  // ═══ User handlers ═══
  const handleCreate = async (e) => {
    e.preventDefault();
    setCreating(true);
    const form = e.target;
    const username = form.username.value.trim();
    const email = form.email.value.trim();
    const password = form.password.value;
    if (!username || !password) { setCreating(false); return; }
    try {
      await api.post("/auth/users/", { username, email, password, is_superuser: form.is_superuser.checked });
      setMsg({ type: "success", text: `用户 ${username} 创建成功` });
      setCreateOpen(false); form.reset(); load();
    } catch (e) {
      setMsg({ type: "error", text: e.response?.data?.error || "创建失败" });
    } finally { setCreating(false); }
  };

  const openReset = (user) => { setResetUser(user); setResetOpen(true); };

  const handleReset = async (e) => {
    e.preventDefault();
    setResetting(true);
    const pw = e.target.new_password.value;
    if (!pw || pw.length < 6) { setResetting(false); return; }
    try {
      await api.put(`/auth/users/${resetUser.id}/reset-password/`, { new_password: pw });
      setMsg({ type: "success", text: `用户 ${resetUser.username} 密码已重置` });
      setResetOpen(false); setResetUser(null);
    } catch (e) {
      setMsg({ type: "error", text: e.response?.data?.error || "重置失败" });
    } finally { setResetting(false); }
  };

  const handleUnlock = async (user) => {
    try {
      const { data } = await api.post(`/auth/users/${user.id}/unlock/`);
      setMsg({ type: "success", text: data.detail || "已解锁" }); load();
    } catch { setMsg({ type: "error", text: isZh ? "解锁失败" : "Unlock failed" }); }
  };

  const handleDeleteUser = async (user) => {
    if (!window.confirm(isZh ? `确定删除 ${user.username}？` : `Delete ${user.username}?`)) return;
    try {
      await api.delete(`/auth/users/${user.id}/`);
      setMsg({ type: "success", text: isZh ? `${user.username} 已删除` : `${user.username} deleted` }); load();
    } catch (e) { setMsg({ type: "error", text: e.response?.data?.error || "删除失败" }); }
  };

  const handleToggleActive = async (user) => {
    const next = !user.is_active;
    if (!window.confirm(next ? (isZh ? `启用 ${user.username}？` : `Enable ${user.username}?`) : (isZh ? `禁用 ${user.username}？` : `Disable ${user.username}?`))) return;
    try {
      if (next) await api.patch(`/auth/users/${user.id}/`, { is_active: true });
      else await api.delete(`/auth/users/${user.id}/?action=deactivate`);
      load();
    } catch { setMsg({ type: "error", text: "操作失败" }); }
  };

  const handleAssignRole = async (userId, roleId) => {
    try {
      if (roleId === "") await api.delete(`/auth/users/${userId}/role/`);
      else await api.put(`/auth/users/${userId}/role/`, { role_id: roleId });
      load();
    } catch (e) { setMsg({ type: "error", text: e.response?.data?.error || "角色分配失败" }); }
  };

  // ═══ Role handlers ═══
  const openRoleEdit = (role) => {
    setEditingRole({ ...role, _perms: [...(role.permissions || [])] });
    setRoleModalOpen(true);
  };

  const openRoleCreate = () => {
    setEditingRole({ name: "", display_name: "", description: "", is_builtin: false, _perms: [], _isNew: true });
    setRoleModalOpen(true);
  };

  const togglePermInRole = (code) => {
    setEditingRole((prev) => {
      const perms = [...(prev._perms || [])];
      const idx = perms.indexOf(code);
      if (idx >= 0) perms.splice(idx, 1);
      else perms.push(code);
      return { ...prev, _perms: perms };
    });
  };

  const handleSaveRole = async () => {
    const r = editingRole;
    if (!r || !r.display_name.trim()) return;
    try {
      if (r._isNew) {
        const name = r.name.trim() || r.display_name.trim().toLowerCase().replace(/\s+/g, "_");
        await api.post("/auth/roles/", { name, display_name: r.display_name.trim(), description: r.description || "", permissions: r._perms });
        setMsg({ type: "success", text: isZh ? "角色已创建" : "Role created" });
      } else {
        await api.put(`/auth/roles/${r.id}/`, { display_name: r.display_name?.trim(), description: r.description || "", permissions: r._perms });
        setMsg({ type: "success", text: isZh ? "角色已更新" : "Role updated" });
      }
      setRoleModalOpen(false); setEditingRole(null); load();
    } catch (e) { setMsg({ type: "error", text: e.response?.data?.error || "保存失败" }); }
  };

  const handleDeleteRole = async (role) => {
    if (!window.confirm(isZh ? `确定删除角色「${role.display_name}」？` : `Delete role "${role.display_name}"?`)) return;
    try {
      await api.delete(`/auth/roles/${role.id}/`);
      setMsg({ type: "success", text: isZh ? "角色已删除" : "Role deleted" }); load();
    } catch (e) { setMsg({ type: "error", text: e.response?.data?.error || "删除失败" }); }
  };

  const formatTime = (dt) => dt ? dt.replace("T", " ").slice(0, 19) : "—";

  if (!me?.is_superuser && !canView) return null;

  return (
    <AppLayout title={isZh ? "系统管理" : "System Admin"}>
      <div className="admin-page">
        {/* ── Message ── */}
        {msg && (
          <div className={`admin-msg admin-msg--${msg.type}`}>
            {msg.text}
            <button className="admin-msg-close" onClick={() => setMsg(null)}>
              <span className="material-symbols-outlined" style={{ fontSize: 14 }}>close</span>
            </button>
          </div>
        )}

        {/* ── Tabs ── */}
        <div className="admin-tabs-bar">
          <div className="admin-tabs">
            <button className={`admin-tab ${adminTab === "users" ? "admin-tab--active" : ""}`} onClick={() => setAdminTab("users")}>
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>people</span>
              {isZh ? "用户管理" : "Users"}
            </button>
            <button className={`admin-tab ${adminTab === "roles" ? "admin-tab--active" : ""}`} onClick={() => setAdminTab("roles")}>
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>admin_panel_settings</span>
              {isZh ? "角色配置" : "Roles"}
            </button>
          </div>

          <div className="admin-toolbar-right">
            {adminTab === "users" && canManageUsers && (
              <button className="admin-btn admin-btn--primary" onClick={() => { setCreateOpen(true); setMsg(null); }}>
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>person_add</span>
                {isZh ? "创建用户" : "Create User"}
              </button>
            )}
            {adminTab === "roles" && canManageUsers && (
              <button className="admin-btn admin-btn--primary" onClick={openRoleCreate}>
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>add</span>
                {isZh ? "创建角色" : "Create Role"}
              </button>
            )}
          </div>
        </div>

        {loading ? (
          <div className="loading-wrap"><div className="mini-spinner" /> {t("common.loading")}</div>
        ) : (
          <>
            {/* ═══ USERS TAB ═══ */}
            {adminTab === "users" && (
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
                      <th>{isZh ? "失败" : "Fail"}</th>
                      <th>{isZh ? "操作" : "Actions"}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u) => (
                      <tr key={u.id} className={!u.is_active ? "admin-row--disabled" : ""}>
                        <td>
                          <span className="admin-username">{u.username}</span>
                          {u.id === me.id && <span className="admin-tag admin-tag--me">{isZh ? "我" : "me"}</span>}
                        </td>
                        <td className="admin-email">{u.email || "—"}</td>
                        <td className="admin-role-cell">
                          {canManageUsers ? (
                            <select className="admin-role-sel" value={u.role_id || ""} onChange={(e) => handleAssignRole(u.id, e.target.value ? parseInt(e.target.value, 10) : "")}>
                              <option value="">—</option>
                              {roles.map((r) => <option key={r.id} value={r.id}>{r.display_name}</option>)}
                            </select>
                          ) : (
                            <span className="admin-tag admin-tag--user">{u.role_name || (isZh ? "无角色" : "None")}</span>
                          )}
                        </td>
                        <td>
                          <span className={`admin-status ${u.is_active ? "admin-status--active" : "admin-status--disabled"}`}>
                            {u.is_active ? (isZh ? "启用" : "Active") : (isZh ? "禁用" : "Disabled")}
                          </span>
                        </td>
                        <td className="admin-time">{formatTime(u.last_login)}</td>
                        <td className="admin-time">{formatTime(u.date_joined)}</td>
                        <td>{u.failed_attempts > 0 ? <span className="admin-failures">{u.failed_attempts}</span> : <span className="admin-failures-zero">0</span>}</td>
                        <td>
                          {canManageUsers && (
                            <div className="admin-actions">
                              {u.failed_attempts > 0 && (
                                <button className="admin-action-btn admin-action-btn--unlock" onClick={() => handleUnlock(u)} title={isZh ? "解锁" : "Unlock"}><span className="material-symbols-outlined" style={{ fontSize: 15 }}>lock_open</span></button>
                              )}
                              <button className="admin-action-btn admin-action-btn--reset" onClick={() => openReset(u)} title={isZh ? "重置密码" : "Reset PW"}><span className="material-symbols-outlined" style={{ fontSize: 15 }}>key</span></button>
                              {u.id !== me.id && (
                                <>
                                  <button className="admin-action-btn" onClick={() => handleToggleActive(u)} title={u.is_active ? (isZh ? "禁用" : "Disable") : (isZh ? "启用" : "Enable")}><span className="material-symbols-outlined" style={{ fontSize: 15 }}>{u.is_active ? "block" : "check_circle"}</span></button>
                                  <button className="admin-action-btn admin-action-btn--danger" onClick={() => handleDeleteUser(u)} title={isZh ? "删除" : "Delete"}><span className="material-symbols-outlined" style={{ fontSize: 15 }}>delete</span></button>
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

            {/* ═══ ROLES TAB ═══ */}
            {adminTab === "roles" && (
              <div className="admin-roles-grid">
                {roles.map((role) => (
                  <div key={role.id} className="admin-role-card">
                    <div className="admin-role-card-header">
                      <div>
                        <span className="admin-role-card-name">{role.display_name}</span>
                        {role.is_builtin && <span className="admin-role-card-builtin">{isZh ? "内置" : "Built-in"}</span>}
                        <span className="admin-role-card-count">{isZh ? `${role.user_count} 个用户` : `${role.user_count} users`}</span>
                      </div>
                      {canManageUsers && (
                        <div className="admin-role-card-actions">
                          <button className="admin-action-btn" onClick={() => openRoleEdit(role)} title={isZh ? "编辑" : "Edit"}><span className="material-symbols-outlined" style={{ fontSize: 15 }}>edit</span></button>
                          {!role.is_builtin && (
                            <button className="admin-action-btn admin-action-btn--danger" onClick={() => handleDeleteRole(role)} title={isZh ? "删除" : "Delete"}><span className="material-symbols-outlined" style={{ fontSize: 15 }}>delete</span></button>
                          )}
                        </div>
                      )}
                    </div>
                    {role.description && <div className="admin-role-card-desc">{role.description}</div>}
                    <div className="admin-role-card-perms">
                      {permGroups.map((grp) => {
                        const hasAny = grp.permissions.some((p) => (role.permissions || []).includes(p.code));
                        return (
                          <div key={grp.name} className={`admin-role-perm-group ${!hasAny ? "admin-role-perm-group--empty" : ""}`}>
                            <span className="admin-role-perm-group-name">{isZh ? grp.name : grp.name_en}</span>
                            <div className="admin-role-perm-tags">
                              {hasAny
                                ? grp.permissions.filter((p) => (role.permissions || []).includes(p.code)).map((p) => (
                                  <span key={p.code} className="admin-role-perm-tag">{isZh ? p.label : p.label_en}</span>
                                ))
                                : <span className="admin-role-perm-none">—</span>}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {/* ═══ Create User Modal ═══ */}
        {createOpen && (
          <div className="admin-modal-overlay" onClick={() => setCreateOpen(false)}>
            <form className="admin-modal" onClick={(e) => e.stopPropagation()} onSubmit={handleCreate}>
              <div className="admin-modal-header">
                <span className="admin-modal-title">{isZh ? "创建用户" : "Create User"}</span>
                <button type="button" className="admin-modal-close" onClick={() => setCreateOpen(false)}><span className="material-symbols-outlined">close</span></button>
              </div>
              <div className="admin-modal-body">
                <label className="admin-modal-label">{isZh ? "用户名" : "Username"} *</label>
                <input name="username" className="admin-modal-input" required autoFocus />
                <label className="admin-modal-label">{isZh ? "邮箱" : "Email"}</label>
                <input name="email" type="email" className="admin-modal-input" placeholder="user@example.com" />
                <label className="admin-modal-label">{isZh ? "密码" : "Password"} *</label>
                <input name="password" type="password" className="admin-modal-input" placeholder={isZh ? "至少 6 位" : "Min 6 chars"} required />
                <label className="admin-modal-check-label">
                  <input name="is_superuser" type="checkbox" /><span>{isZh ? "设为超级管理员" : "Grant superuser role"}</span>
                </label>
              </div>
              <div className="admin-modal-footer">
                <button type="button" className="admin-modal-cancel" onClick={() => setCreateOpen(false)}>{t("common.cancel")}</button>
                <button type="submit" className="admin-btn admin-btn--primary" disabled={creating}>{creating ? (isZh ? "创建中..." : "Creating...") : t("common.save")}</button>
              </div>
            </form>
          </div>
        )}

        {/* ═══ Reset Password Modal ═══ */}
        {resetOpen && resetUser && (
          <div className="admin-modal-overlay" onClick={() => { setResetOpen(false); setResetUser(null); }}>
            <form className="admin-modal" onClick={(e) => e.stopPropagation()} onSubmit={handleReset}>
              <div className="admin-modal-header">
                <span className="admin-modal-title">{isZh ? `重置密码 — ${resetUser.username}` : `Reset — ${resetUser.username}`}</span>
                <button type="button" className="admin-modal-close" onClick={() => { setResetOpen(false); setResetUser(null); }}><span className="material-symbols-outlined">close</span></button>
              </div>
              <div className="admin-modal-body">
                <label className="admin-modal-label">{isZh ? "新密码" : "New Password"} *</label>
                <input name="new_password" type="password" className="admin-modal-input" placeholder={isZh ? "至少 6 位" : "Min 6 chars"} required autoFocus />
              </div>
              <div className="admin-modal-footer">
                <button type="button" className="admin-modal-cancel" onClick={() => { setResetOpen(false); setResetUser(null); }}>{t("common.cancel")}</button>
                <button type="submit" className="admin-btn admin-btn--primary" disabled={resetting}>{resetting ? (isZh ? "重置中..." : "Resetting...") : (isZh ? "重置密码" : "Reset")}</button>
              </div>
            </form>
          </div>
        )}

        {/* ═══ Role Create/Edit Modal ═══ */}
        {roleModalOpen && editingRole && (
          <div className="admin-modal-overlay" onClick={() => { setRoleModalOpen(false); setEditingRole(null); }}>
            <div className="admin-modal admin-modal--wide" onClick={(e) => e.stopPropagation()}>
              <div className="admin-modal-header">
                <span className="admin-modal-title">
                  {editingRole._isNew ? (isZh ? "创建角色" : "Create Role") : (isZh ? `编辑角色 — ${editingRole.display_name}` : `Edit Role — ${editingRole.display_name}`)}
                </span>
                <button type="button" className="admin-modal-close" onClick={() => { setRoleModalOpen(false); setEditingRole(null); }}><span className="material-symbols-outlined">close</span></button>
              </div>
              <div className="admin-modal-body">
                <label className="admin-modal-label">{isZh ? "显示名称" : "Display Name"} *</label>
                <input
                  className="admin-modal-input"
                  value={editingRole.display_name}
                  onChange={(e) => setEditingRole((r) => ({ ...r, display_name: e.target.value }))}
                  placeholder={isZh ? "例如: 开发环境运维" : "e.g. Dev Operator"}
                  autoFocus
                />
                {editingRole._isNew && (
                  <>
                    <label className="admin-modal-label">{isZh ? "角色标识" : "Role Key"} (optional)</label>
                    <input
                      className="admin-modal-input"
                      value={editingRole.name}
                      onChange={(e) => setEditingRole((r) => ({ ...r, name: e.target.value }))}
                      placeholder={isZh ? "例如: dev_operator（留空自动生成）" : "e.g. dev_operator"}
                    />
                  </>
                )}
                <label className="admin-modal-label">{isZh ? "描述" : "Description"}</label>
                <textarea
                  className="admin-modal-textarea"
                  value={editingRole.description || ""}
                  onChange={(e) => setEditingRole((r) => ({ ...r, description: e.target.value }))}
                  rows={2}
                />

                {/* Permission checkboxes grouped */}
                <label className="admin-modal-label" style={{ marginTop: 14 }}>{isZh ? "权限" : "Permissions"}</label>
                <div className="admin-perm-editor">
                  {permGroups.map((grp) => (
                    <div key={grp.name} className="admin-perm-edit-group">
                      <div className="admin-perm-edit-group-name">{isZh ? grp.name : grp.name_en}</div>
                      <div className="admin-perm-checkboxes">
                        {grp.permissions.map((p) => {
                          const checked = (editingRole._perms || []).includes(p.code);
                          return (
                            <label key={p.code} className="admin-perm-checkbox-label">
                              <input type="checkbox" checked={checked} onChange={() => togglePermInRole(p.code)} />
                              <span>{isZh ? p.label : p.label_en}</span>
                            </label>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <div className="admin-modal-footer">
                <button type="button" className="admin-modal-cancel" onClick={() => { setRoleModalOpen(false); setEditingRole(null); }}>{t("common.cancel")}</button>
                <button type="button" className="admin-btn admin-btn--primary" onClick={handleSaveRole}>{t("common.save")}</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
