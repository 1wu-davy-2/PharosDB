import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "../services/api";
import AppLayout from "../components/AppLayout";
import { usePerm } from "../context/AuthContext";
import "./AdvisorPage.css";

/* ── 严重度映射 ── */
const SEV = {
  critical: { color: "#ef4444", bg: "rgba(239,68,68,.12)", labelKey: "severity_critical" },
  error: { color: "#f87171", bg: "rgba(248,113,113,.10)", labelKey: "severity_error" },
  warning: { color: "#fbbf24", bg: "rgba(251,191,36,.10)", labelKey: "severity_warning" },
  info: { color: "#60a5fa", bg: "rgba(96,165,250,.10)", labelKey: "severity_info" },
};

const CAT_LABELS = { security: "安全", configuration: "配置", performance: "性能" };
const CAT_LABELS_EN = { security: "Security", configuration: "Config", performance: "Perf" };

/* ═══════════════════════════════════════════════════════════════
   AdvisorPage
   ═══════════════════════════════════════════════════════════════ */

export default function AdvisorPage() {
  const { t, i18n } = useTranslation();
  const isZh = i18n.language === "zh";

  const canRun = usePerm("advisor:run");
  const canToggle = usePerm("advisor:toggle");
  const canTargeting = usePerm("advisor:targeting");
  const canGroups = usePerm("advisor:groups");

  const [checks, setChecks] = useState([]);
  const [findings, setFindings] = useState([]);
  const [summary, setSummary] = useState(null);
  const [groups, setGroups] = useState([]);
  const [scheduler, setScheduler] = useState(null);
  const [instances, setInstances] = useState([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState(null);

  // filters
  const [filterFamily, setFilterFamily] = useState("");
  const [filterCategory, setFilterCategory] = useState("");
  const [filterSeverity, setFilterSeverity] = useState("");
  const [tab, setTab] = useState("findings"); // findings | checks | groups

  // modals
  const [groupModal, setGroupModal] = useState(false);
  const [editingGroup, setEditingGroup] = useState(null);
  const [targetModal, setTargetModal] = useState(false);
  const [targetingCheck, setTargetingCheck] = useState(null);
  const [runMenuOpen, setRunMenuOpen] = useState(false);
  const runMenuRef = useRef(null);

  const catLabel = (c) => (isZh ? (CAT_LABELS[c] || c) : (CAT_LABELS_EN[c] || c));

  // ── Load all data ──
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [cr, fr, sr, gr, schR] = await Promise.all([
        api.get("/advisor/checks/"),
        api.get("/advisor/findings/?limit=100"),
        api.get("/advisor/summary/"),
        api.get("/advisor/groups/"),
        api.get("/advisor/scheduler/status/"),
      ]);
      setChecks(cr.data.checks || []);
      setFindings(fr.data.findings || []);
      setSummary(sr.data);
      setGroups(gr.data.groups || []);
      setScheduler(schR.data);
    } catch {
      setMsg({ type: "error", text: t("common.error") });
    } finally {
      setLoading(false);
    }
  }, [t]);

  // ── Load instances (for group modal) ──
  const loadInstances = useCallback(async () => {
    try {
      const { data } = await api.get("/collector/instances/");
      setInstances(data.results || data || []);
    } catch {}
  }, []);

  useEffect(() => { load(); }, [load]);

  // Close run menu on outside click
  useEffect(() => {
    const handler = (e) => {
      if (runMenuRef.current && !runMenuRef.current.contains(e.target)) {
        setRunMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // ── Run checks ──
  const handleRun = async (action, groupId) => {
    setRunning(true);
    setMsg(null);
    setRunMenuOpen(false);
    try {
      const body = groupId ? { action: "group", group_id: groupId } : { action: "all" };
      const { data } = await api.post("/advisor/run/", body);
      setMsg({ type: "success", text: t("advisor.run_complete", { count: data.findings }) });
      await load();
    } catch (e) {
      setMsg({ type: "error", text: e.response?.data?.error || t("advisor.run_failed") });
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

  // ── Groups CRUD ──
  const handleCreateGroup = () => {
    setEditingGroup(null);
    setGroupModal(true);
    loadInstances();
  };

  const handleEditGroup = (group) => {
    setEditingGroup(group);
    setGroupModal(true);
    loadInstances();
  };

  const handleSaveGroup = async (e) => {
    e.preventDefault();
    const form = e.target;
    const name = form.group_name.value.trim();
    const description = form.group_desc.value.trim();
    const checkedIds = [...form.querySelectorAll("input[name='group_instances']:checked")]
      .map((el) => parseInt(el.value, 10));

    if (!name) return;

    try {
      if (editingGroup) {
        await api.put(`/advisor/groups/${editingGroup.id}/`, {
          name, description, instance_ids: checkedIds,
        });
      } else {
        await api.post("/advisor/groups/", {
          name, description, instance_ids: checkedIds,
        });
      }
      setGroupModal(false);
      setEditingGroup(null);
      load();
    } catch (e) {
      setMsg({ type: "error", text: e.response?.data?.error || "保存失败" });
    }
  };

  const handleDeleteGroup = async (id) => {
    if (!window.confirm(t("advisor.group_delete_confirm"))) return;
    try {
      await api.delete(`/advisor/groups/${id}/`);
      load();
    } catch {}
  };

  // ── Check targeting ──
  const openTargeting = (check) => {
    setTargetingCheck({ ...check, _groupIds: (check.target_groups || []).map((g) => g.id) });
    setTargetModal(true);
  };

  const handleSaveTargeting = async () => {
    if (!targetingCheck) return;
    try {
      await api.put(`/advisor/checks/${targetingCheck.id}/targeting/`, {
        group_ids: targetingCheck._groupIds,
      });
      setTargetModal(false);
      setTargetingCheck(null);
      load();
    } catch (e) {
      setMsg({ type: "error", text: e.response?.data?.error || "保存失败" });
    }
  };

  const toggleGroupInTargeting = (groupId) => {
    setTargetingCheck((prev) => {
      const ids = prev._groupIds || [];
      return { ...prev, _groupIds: ids.includes(groupId) ? ids.filter((i) => i !== groupId) : [...ids, groupId] };
    });
  };

  // ── Scheduler toggle ──
  const handleSchedulerToggle = async () => {
    const next = !scheduler?.running;
    try {
      await api.post("/advisor/scheduler/toggle/", { enabled: next });
      setScheduler((s) => ({ ...s, running: next }));
    } catch {}
  };

  // ── Filters ──
  const families = [...new Set(checks.map((c) => c.family))];
  const categories = [...new Set(checks.map((c) => c.category))];

  let filtered = tab === "checks" ? checks : tab === "groups" ? groups : findings;
  if (tab !== "groups") {
    if (filterFamily) filtered = filtered.filter((c) => c.family === filterFamily);
    if (filterCategory) filtered = filtered.filter((c) => c.category === filterCategory);
    if (filterSeverity) filtered = filtered.filter((c) => c.severity === filterSeverity);
  }

  return (
    <AppLayout title={t("nav.advisor")}>
      <div className="advisor-page">
        {/* ── Scheduler status bar ── */}
        <div className="advisor-scheduler-bar">
          <div className="advisor-scheduler-left">
            <span className={`advisor-scheduler-dot ${scheduler?.running ? "advisor-scheduler-dot--on" : "advisor-scheduler-dot--off"}`} />
            <span className="advisor-scheduler-label">
              {scheduler?.running ? t("advisor.scheduler_running") : t("advisor.scheduler_paused")}
            </span>
            {scheduler?.running && (
              <span className="advisor-scheduler-count">
                {scheduler.active_checks} checks active
              </span>
            )}
          </div>
          {canRun && (
            <button className="advisor-scheduler-btn" onClick={handleSchedulerToggle}>
              <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
                {scheduler?.running ? "pause" : "play_arrow"}
              </span>
              {scheduler?.running ? t("advisor.scheduler_pause") : t("advisor.scheduler_start")}
            </button>
          )}
        </div>

        {/* ── Summary Bar ── */}
        {summary && (
          <div className="advisor-summary">
            <div className="advisor-summary-card advisor-summary-total">
              <span className="advisor-summary-num">{summary.total}</span>
              <span className="advisor-summary-label">{t("advisor.active_findings")}</span>
            </div>
            <div className="advisor-summary-card advisor-summary-critical">
              <span className="advisor-summary-num">{(summary.by_severity?.critical || 0) + (summary.by_severity?.error || 0)}</span>
              <span className="advisor-summary-label">{t("advisor.summary_critical")}</span>
            </div>
            <div className="advisor-summary-card advisor-summary-warning">
              <span className="advisor-summary-num">{summary.by_severity?.warning || 0}</span>
              <span className="advisor-summary-label">{t("advisor.summary_warning")}</span>
            </div>
            <div className="advisor-summary-card advisor-summary-info">
              <span className="advisor-summary-num">{summary.by_severity?.info || 0}</span>
              <span className="advisor-summary-label">{t("advisor.summary_info")}</span>
            </div>
          </div>
        )}

        {/* ── Actions Bar ── */}
        <div className="advisor-bar">
          <div className="advisor-tabs">
            <button className={`advisor-tab ${tab === "findings" ? "advisor-tab--active" : ""}`} onClick={() => setTab("findings")}>
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>error</span>
              {t("advisor.tab_findings")} ({findings.length})
            </button>
            <button className={`advisor-tab ${tab === "checks" ? "advisor-tab--active" : ""}`} onClick={() => setTab("checks")}>
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>rule</span>
              {t("advisor.tab_checks")} ({checks.length})
            </button>
            <button className={`advisor-tab ${tab === "groups" ? "advisor-tab--active" : ""}`} onClick={() => setTab("groups")}>
              <span className="material-symbols-outlined" style={{ fontSize: 16 }}>group_work</span>
              {t("advisor.tab_groups")} ({groups.length})
            </button>
          </div>

          {tab !== "groups" && (
            <div className="advisor-filters">
              <select className="advisor-sel" value={filterFamily} onChange={(e) => setFilterFamily(e.target.value)}>
                <option value="">{t("advisor.filter_all_db")}</option>
                {families.map((f) => <option key={f} value={f}>{f}</option>)}
              </select>
              <select className="advisor-sel" value={filterCategory} onChange={(e) => setFilterCategory(e.target.value)}>
                <option value="">{t("advisor.filter_all_cat")}</option>
                {categories.map((c) => <option key={c} value={c}>{catLabel(c)}</option>)}
              </select>
              <select className="advisor-sel" value={filterSeverity} onChange={(e) => setFilterSeverity(e.target.value)}>
                <option value="">{t("advisor.filter_all_sev")}</option>
                {Object.entries(SEV).map(([k, v]) => <option key={k} value={k}>{t(v.labelKey)}</option>)}
              </select>
            </div>
          )}

          {/* Run button with dropdown */}
          {canRun && (
            <div className="advisor-run-wrap" ref={runMenuRef}>
              <button className="advisor-run-btn" onClick={() => handleRun("all")} disabled={running}>
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                  {running ? "progress_activity" : "play_arrow"}
                </span>
                {running ? t("advisor.running") : t("advisor.run_all")}
              </button>
              {groups.length > 0 && (
                <>
                  <button className="advisor-run-caret" onClick={() => setRunMenuOpen(!runMenuOpen)} disabled={running}>
                    <span className="material-symbols-outlined" style={{ fontSize: 16 }}>expand_more</span>
                  </button>
                  {runMenuOpen && (
                    <div className="advisor-run-menu">
                      <div className="advisor-run-menu-item" onClick={() => handleRun("all")}>
                        {t("advisor.run_all_instances")}
                      </div>
                      {groups.map((g) => (
                        <div key={g.id} className="advisor-run-menu-item" onClick={() => handleRun("group", g.id)}>
                          {t("advisor.run_group", { name: g.name })}
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </div>

        {msg && (
          <div className={`advisor-msg advisor-msg--${msg.type}`}>{msg.text}</div>
        )}

        {/* ── Content ── */}
        {loading ? (
          <div className="loading-wrap"><div className="mini-spinner" /> {t("common.loading")}</div>
        ) : (
          <>
            {/* ═══ FINDINGS TAB ═══ */}
            {tab === "findings" && (
              filtered.length === 0 ? (
                <div className="empty-state" style={{ padding: 40 }}>
                  <span className="material-symbols-outlined empty-state-icon">verified</span>
                  <div className="empty-state-title">{t("advisor.no_findings")}</div>
                  <div className="empty-state-desc">{t("advisor.no_findings_desc")}</div>
                </div>
              ) : (
                <div className="advisor-findings-list">
                  {filtered.map((f) => {
                    const sev = SEV[f.severity] || SEV.info;
                    return (
                      <div key={f.id} className="advisor-finding-card" style={{ borderLeftColor: sev.color }}>
                        <div className="advisor-finding-left">
                          <span className="advisor-finding-sev" style={{ background: sev.color }}>{t(sev.labelKey)}</span>
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
                          <span className="advisor-finding-cat" title={f.category}>{catLabel(f.category)}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )
            )}

            {/* ═══ CHECKS TAB ═══ */}
            {tab === "checks" && (
              <div className="advisor-checks-grid">
                {filtered.map((c) => {
                  const sev = SEV[c.severity] || SEV.info;
                  const hasTargets = c.target_groups && c.target_groups.length > 0;
                  return (
                    <div key={c.id} className={`advisor-check-card ${!c.enabled ? "advisor-check-card--disabled" : ""}`}>
                      <div className="advisor-check-header">
                        <span className="advisor-check-name">{c.display_name}</span>
                        {canToggle ? (
                          <label className="advisor-check-toggle">
                            <input type="checkbox" checked={c.enabled} onChange={() => handleToggle(c.name, c.enabled)} />
                            <span className="advisor-check-toggle-slider" />
                          </label>
                        ) : (
                          <span className="advisor-check-tag" style={{ color: c.enabled ? "#34d399" : "#9ca3af" }}>
                            {c.enabled ? "已启用" : "已禁用"}
                          </span>
                        )}
                      </div>
                      <div className="advisor-check-summary">{c.summary}</div>
                      <div className="advisor-check-meta">
                        <span className="advisor-check-tag" style={{ background: sev.bg, color: sev.color }}>{t(sev.labelKey)}</span>
                        <span className="advisor-check-tag">{c.family}</span>
                        <span className="advisor-check-tag">{catLabel(c.category)}</span>
                        <span className="advisor-check-tag">{c.mode === "exists" ? "存在即报" : `阈值 > ${c.threshold}`}</span>
                        {c.active_findings > 0 && (
                          <span className="advisor-check-tag" style={{ background: "rgba(239,68,68,.15)", color: "#f87171" }}>
                            {c.active_findings} 项发现
                          </span>
                        )}
                      </div>
                      {/* Targeting info */}
                      <div className="advisor-check-target-row">
                        {hasTargets ? (
                          <span className="advisor-check-target-info">
                            <span className="material-symbols-outlined" style={{ fontSize: 13 }}>groups</span>
                            {t("advisor.target_limited", { groups: c.target_groups.map((g) => g.name).join(", ") })}
                          </span>
                        ) : (
                          <span className="advisor-check-target-info advisor-check-target-all">
                            <span className="material-symbols-outlined" style={{ fontSize: 13 }}>public</span>
                            {t("advisor.target_all")}
                          </span>
                        )}
                        {canTargeting && (
                          <button className="advisor-check-target-btn" onClick={() => openTargeting(c)}>
                            {t("advisor.configure_target")}
                          </button>
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

            {/* ═══ GROUPS TAB ═══ */}
            {tab === "groups" && (
              <>
                {canGroups && (
                  <div style={{ marginBottom: 12 }}>
                    <button className="advisor-run-btn" onClick={handleCreateGroup} style={{ background: "var(--color-accent)" }}>
                      <span className="material-symbols-outlined" style={{ fontSize: 16 }}>add</span>
                      {t("advisor.group_create")}
                    </button>
                  </div>
                )}

                {groups.length === 0 ? (
                  <div className="empty-state" style={{ padding: 40 }}>
                    <span className="material-symbols-outlined empty-state-icon">group_work</span>
                    <div className="empty-state-title">{t("advisor.group_empty")}</div>
                    <div className="empty-state-desc">{t("advisor.group_empty_desc")}</div>
                  </div>
                ) : (
                  <div className="advisor-groups-grid">
                    {groups.map((g) => (
                      <div key={g.id} className="advisor-group-card">
                        <div className="advisor-group-header">
                          <div className="advisor-group-name">{g.name}</div>
                          {canGroups && (
                            <div className="advisor-group-actions">
                              <button className="advisor-group-action-btn" onClick={() => handleEditGroup(g)} title={t("common.edit")}>
                                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>edit</span>
                              </button>
                              <button className="advisor-group-action-btn advisor-group-action-btn--danger" onClick={() => handleDeleteGroup(g.id)} title={t("common.delete")}>
                                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>delete</span>
                              </button>
                            </div>
                          )}
                        </div>
                        {g.description && <div className="advisor-group-desc">{g.description}</div>}
                        <div className="advisor-group-stats">
                          <span className="advisor-group-stat">
                            <span className="material-symbols-outlined" style={{ fontSize: 14 }}>storage</span>
                            {t("advisor.group_instance_count", { count: g.instance_count })}
                          </span>
                          <span className="advisor-group-stat">
                            <span className="material-symbols-outlined" style={{ fontSize: 14 }}>rule</span>
                            {t("advisor.group_check_count", { count: g.check_count })}
                          </span>
                        </div>
                        {/* Instances list */}
                        {g.instances && g.instances.length > 0 && (
                          <div className="advisor-group-instances">
                            {g.instances.map((inst) => (
                              <span key={inst.id} className="advisor-group-inst-tag" title={`${inst.environment} / ${inst.cluster || "—"} / ${inst.cluster_role}`}>
                                <span className={`advisor-inst-dot advisor-inst-dot--${inst.connection_status}`} />
                                {inst.name}
                                <span className="advisor-inst-type">{inst.db_type}</span>
                              </span>
                            ))}
                          </div>
                        )}
                        {(!g.instances || g.instances.length === 0) && (
                          <div className="advisor-group-no-inst">{t("advisor.group_no_instances")}</div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </>
        )}

        {/* ═══ Group Create/Edit Modal ═══ */}
        {groupModal && (
          <div className="advisor-modal-overlay" onClick={() => { setGroupModal(false); setEditingGroup(null); }}>
            <form className="advisor-modal" onClick={(e) => e.stopPropagation()} onSubmit={handleSaveGroup}>
              <div className="advisor-modal-header">
                <span className="advisor-modal-title">{editingGroup ? t("advisor.group_edit") : t("advisor.group_create")}</span>
                <button type="button" className="advisor-modal-close" onClick={() => { setGroupModal(false); setEditingGroup(null); }}>
                  <span className="material-symbols-outlined">close</span>
                </button>
              </div>
              <div className="advisor-modal-body">
                <label className="advisor-modal-label">{t("advisor.group_name")}</label>
                <input
                  name="group_name"
                  className="advisor-modal-input"
                  placeholder={t("advisor.group_name_placeholder")}
                  defaultValue={editingGroup?.name || ""}
                  required
                  autoFocus
                />
                <label className="advisor-modal-label">{t("advisor.group_description")}</label>
                <textarea
                  name="group_desc"
                  className="advisor-modal-textarea"
                  placeholder={t("advisor.group_desc_placeholder")}
                  defaultValue={editingGroup?.description || ""}
                  rows={3}
                />
                <label className="advisor-modal-label">{t("advisor.group_instances")}</label>
                <div className="advisor-instance-checklist">
                  {instances.length === 0 && <div className="advisor-group-no-inst">加载实例中...</div>}
                  {instances.map((inst) => {
                    const checked = editingGroup
                      ? editingGroup.instances?.some((i) => i.id === inst.id)
                      : false;
                    return (
                      <label key={inst.id} className="advisor-instance-checklist-item">
                        <input
                          type="checkbox"
                          name="group_instances"
                          value={inst.id}
                          defaultChecked={checked}
                        />
                        <span className="advisor-inst-checklist-name">
                          <span className={`advisor-inst-dot advisor-inst-dot--${inst.connection_status}`} />
                          {inst.name}
                        </span>
                        <span className="advisor-inst-checklist-meta">{inst.db_type} / {inst.environment}</span>
                      </label>
                    );
                  })}
                </div>
              </div>
              <div className="advisor-modal-footer">
                <button type="button" className="advisor-modal-cancel" onClick={() => { setGroupModal(false); setEditingGroup(null); }}>
                  {t("common.cancel")}
                </button>
                <button type="submit" className="advisor-run-btn" style={{ background: "var(--color-accent)" }}>
                  {t("common.save")}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* ═══ Targeting Modal ═══ */}
        {targetModal && targetingCheck && (
          <div className="advisor-modal-overlay" onClick={() => { setTargetModal(false); setTargetingCheck(null); }}>
            <div className="advisor-modal" onClick={(e) => e.stopPropagation()}>
              <div className="advisor-modal-header">
                <span className="advisor-modal-title">{t("advisor.configure_target")} — {targetingCheck.display_name}</span>
                <button type="button" className="advisor-modal-close" onClick={() => { setTargetModal(false); setTargetingCheck(null); }}>
                  <span className="material-symbols-outlined">close</span>
                </button>
              </div>
              <div className="advisor-modal-body">
                <p className="advisor-target-hint">{t("advisor.target_hint")}</p>
                <div className="advisor-target-group-list">
                  {groups.length === 0 && (
                    <div className="advisor-group-no-inst">{t("advisor.group_empty")} — {t("advisor.group_empty_desc")}</div>
                  )}
                  {groups.map((g) => {
                    const isSelected = (targetingCheck._groupIds || []).includes(g.id);
                    return (
                      <label key={g.id} className={`advisor-target-group-item ${isSelected ? "advisor-target-group-item--selected" : ""}`}>
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleGroupInTargeting(g.id)}
                        />
                        <div className="advisor-target-group-info">
                          <span className="advisor-target-group-name">{g.name}</span>
                          <span className="advisor-target-group-meta">
                            {t("advisor.group_instance_count", { count: g.instance_count })}
                          </span>
                        </div>
                      </label>
                    );
                  })}
                </div>
              </div>
              <div className="advisor-modal-footer">
                <button type="button" className="advisor-modal-cancel" onClick={() => { setTargetModal(false); setTargetingCheck(null); }}>
                  {t("common.cancel")}
                </button>
                <button type="button" className="advisor-run-btn" style={{ background: "var(--color-accent)" }} onClick={handleSaveTargeting}>
                  {t("advisor.target_save")}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
