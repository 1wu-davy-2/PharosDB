import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "../services/api";
import AppLayout from "../components/AppLayout";
import "./SettingsPage.css";

/* ── 分类元数据 ─────────────────────────────────────── */
const CATEGORY_LABELS = {
  collection: "采集参数",
  alerting: "告警参数",
  retention: "数据保留",
  notification: "推送配置",
  general: "通用",
};

const CATEGORY_ICONS = {
  collection: "database",
  alerting: "notifications",
  retention: "archive",
  notification: "send",
  general: "settings",
};

const SYSTEM_CATEGORIES = ["collection", "alerting", "retention", "general"];
const NOTIFICATION_CATEGORIES = ["notification"];

/* ── 敏感字段：显示/隐藏切换 ── */
function SecretInput({ value, onChange, disabled }) {
  const [show, setShow] = useState(false);
  return (
    <div className="settings-secret-wrap">
      <input
        className="settings-input"
        type={show ? "text" : "password"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      />
      <button
        type="button"
        className="settings-secret-eye"
        onClick={() => setShow((v) => !v)}
        tabIndex={-1}
      >
        <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
          {show ? "visibility_off" : "visibility"}
        </span>
      </button>
    </div>
  );
}

/* ── 单行配置控件 ── */
function ConfigRow({ cfg, dirty, onChange }) {
  const displayVal = dirty[cfg.key] !== undefined ? dirty[cfg.key] : cfg.value;
  const isBool = cfg.value_type === "bool";
  const isSecret = cfg.is_secret;

  return (
    <div className="settings-row">
      <div className="settings-row-label">
        <span className="settings-row-name">{cfg.display_name || cfg.key}</span>
        <span className="settings-row-key">{cfg.key}</span>
      </div>

      <div className="settings-row-control">
        {isBool ? (
          <label className="settings-toggle">
            <input
              type="checkbox"
              checked={
                displayVal === true ||
                displayVal === "true" ||
                displayVal === true
              }
              onChange={(e) => onChange(cfg.key, e.target.checked)}
              disabled={!cfg.editable}
            />
            <span className="settings-toggle-slider" />
          </label>
        ) : isSecret ? (
          <SecretInput
            value={displayVal}
            onChange={(v) => onChange(cfg.key, v)}
            disabled={!cfg.editable}
          />
        ) : (
          <input
            className="settings-input"
            type={
              cfg.value_type === "int" || cfg.value_type === "float"
                ? "number"
                : "text"
            }
            step={cfg.value_type === "float" ? "0.1" : "1"}
            min={cfg.value_type === "int" ? 1 : cfg.value_type === "float" ? 0.1 : undefined}
            value={displayVal}
            onChange={(e) => onChange(cfg.key, e.target.value)}
            disabled={!cfg.editable}
          />
        )}
      </div>

      <div className="settings-row-desc">{cfg.description}</div>
    </div>
  );
}

/* ── 分类卡片 ── */
function CategoryGroup({ category, items, dirty, onChange }) {
  return (
    <div className="settings-group">
      <div className="settings-group-header">
        <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
          {CATEGORY_ICONS[category] || "settings"}
        </span>
        <span>{CATEGORY_LABELS[category] || category}</span>
      </div>
      <div className="settings-group-body">
        {items.map((cfg) => (
          <ConfigRow key={cfg.key} cfg={cfg} dirty={dirty} onChange={onChange} />
        ))}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   SettingsPage
   ═══════════════════════════════════════════════════════ */

const TABS = [
  { key: "system", icon: "tune", i18n: "system" },
  { key: "notification", icon: "send", i18n: "notification" },
];

export default function SettingsPage() {
  const { t } = useTranslation();
  const [configs, setConfigs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dirty, setDirty] = useState({});
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);
  const [activeTab, setActiveTab] = useState("system");

  // ── Load configs ──
  useEffect(() => {
    api
      .get("/config/")
      .then(({ data }) => setConfigs(data.configs || []))
      .catch(() =>
        setMessage({ type: "error", text: t("settings.load_failed") })
      )
      .finally(() => setLoading(false));
  }, [t]);

  // ── Group by category ──
  const grouped = {};
  for (const c of configs) {
    const cat = c.category || "general";
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(c);
  }

  const handleChange = (key, newValue) => {
    setDirty((d) => ({ ...d, [key]: newValue }));
  };

  // ── Save ──
  const handleSave = async () => {
    const changes = Object.entries(dirty).map(([key, value]) => ({
      key,
      value,
    }));
    if (changes.length === 0) {
      setMessage({ type: "info", text: t("settings.no_changes") });
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      const { data } = await api.put("/config/", { configs: changes });
      if (data.errors?.length) {
        setMessage({
          type: "error",
          text: data.errors.map((e) => `${e.key}: ${e.error}`).join("; "),
        });
      } else {
        setMessage({ type: "success", text: t("settings.save_success") });
        setDirty({});
        setConfigs((prev) =>
          prev.map((c) => {
            const updated = data.updated.find((u) => u.key === c.key);
            return updated ? { ...c, value: updated.value } : c;
          })
        );
      }
    } catch (e) {
      setMessage({
        type: "error",
        text:
          e.response?.data?.detail ||
          e.response?.data?.error ||
          t("settings.save_failed"),
      });
    } finally {
      setSaving(false);
    }
  };

  // ── Filter categories by active tab ──
  const visibleCategories =
    activeTab === "notification"
      ? NOTIFICATION_CATEGORIES
      : SYSTEM_CATEGORIES;

  const empty =
    visibleCategories.filter((cat) => grouped[cat]?.length).length === 0;

  return (
    <AppLayout title={t("nav.settings")}>
      <div className="settings-page">
        {loading ? (
          <div className="loading-wrap" style={{ padding: 40 }}>
            <div className="mini-spinner" /> {t("common.loading")}
          </div>
        ) : (
          <>
            {/* ── Tab bar ── */}
            <div className="settings-tab-bar">
              {TABS.map((tab) => (
                <button
                  key={tab.key}
                  className={`settings-tab ${activeTab === tab.key ? "settings-tab--active" : ""}`}
                  onClick={() => setActiveTab(tab.key)}
                >
                  <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
                    {tab.icon}
                  </span>
                  <span>{t(`settings.tab_${tab.i18n}`)}</span>
                </button>
              ))}
            </div>

            {/* ── Top bar ── */}
            <div className="settings-topbar">
              <div className="settings-topbar-info">
                <span style={{ fontSize: 13, color: "var(--color-text-muted)" }}>
                  {t("settings.hint")}
                </span>
              </div>
              <button
                className="settings-save-btn"
                onClick={handleSave}
                disabled={saving || Object.keys(dirty).length === 0}
              >
                <span className="material-symbols-outlined" style={{ fontSize: 16 }}>
                  {saving ? "progress_activity" : "save"}
                </span>
                {saving ? t("common.saving") : t("settings.save")}
              </button>
            </div>

            {message && (
              <div className={`settings-msg settings-msg--${message.type}`}>
                {message.text}
              </div>
            )}

            {empty && !loading ? (
              <div className="empty-state" style={{ padding: 32 }}>
                <span className="material-symbols-outlined empty-state-icon">tune</span>
                <div className="empty-state-title">{t("settings.empty_tab")}</div>
              </div>
            ) : (
              visibleCategories.map((cat) => {
                const items = grouped[cat];
                if (!items?.length) return null;
                return (
                  <CategoryGroup
                    key={cat}
                    category={cat}
                    items={items}
                    dirty={dirty}
                    onChange={handleChange}
                  />
                );
              })
            )}
          </>
        )}
      </div>
    </AppLayout>
  );
}
