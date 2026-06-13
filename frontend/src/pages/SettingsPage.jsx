import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "../services/api";
import AppLayout from "../components/AppLayout";
import "./SettingsPage.css";

const CATEGORY_LABELS = {
  collection: "采集参数",
  alerting: "告警参数",
  retention: "数据保留",
  general: "通用",
};

const CATEGORY_ICONS = {
  collection: "database",
  alerting: "notifications",
  retention: "archive",
  general: "settings",
};

export default function SettingsPage() {
  const { t } = useTranslation();
  const [configs, setConfigs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dirty, setDirty] = useState({}); // key → new value
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null); // { type: "success"|"error", text }

  // ── Load configs ──
  useEffect(() => {
    api.get("/config/").then(({ data }) => {
      setConfigs(data.configs || []);
    }).catch(() => {
      setMessage({ type: "error", text: t("settings.load_failed") });
    }).finally(() => setLoading(false));
  }, [t]);

  // ── Group configs by category ──
  const grouped = {};
  for (const c of configs) {
    const cat = c.category || "general";
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(c);
  }

  // ── Handle value change ──
  const handleChange = (key, newValue) => {
    setDirty((d) => ({ ...d, [key]: newValue }));
  };

  // ── Save ──
  const handleSave = async () => {
    const changes = Object.entries(dirty).map(([key, value]) => ({ key, value }));
    if (changes.length === 0) {
      setMessage({ type: "info", text: t("settings.no_changes") });
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      const { data } = await api.put("/config/", { configs: changes });
      if (data.errors?.length) {
        setMessage({ type: "error", text: data.errors.map((e) => `${e.key}: ${e.error}`).join("; ") });
      } else {
        setMessage({ type: "success", text: t("settings.save_success") });
        setDirty({});
        // Refresh configs
        setConfigs((prev) =>
          prev.map((c) => {
            const updated = data.updated.find((u) => u.key === c.key);
            return updated
              ? { ...c, value: updated.value }
              : c;
          })
        );
      }
    } catch (e) {
      setMessage({
        type: "error",
        text: e.response?.data?.detail || e.response?.data?.error || t("settings.save_failed"),
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <AppLayout title={t("nav.settings")}>
      <div className="settings-page">
        {loading ? (
          <div className="loading-wrap" style={{ padding: 40 }}>
            <div className="mini-spinner" /> {t("common.loading")}
          </div>
        ) : (
          <>
            {/* Top bar */}
            <div className="settings-topbar">
              <div className="settings-topbar-info">
                <span className="material-symbols-outlined" style={{ fontSize: 20, color: "var(--color-accent)" }}>tune</span>
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

            {/* Config groups */}
            {Object.entries(grouped).map(([category, items]) => (
              <div key={category} className="settings-group">
                <div className="settings-group-header">
                  <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
                    {CATEGORY_ICONS[category] || "settings"}
                  </span>
                  <span>{CATEGORY_LABELS[category] || category}</span>
                </div>

                <div className="settings-group-body">
                  {items.map((cfg) => {
                    const displayVal = dirty[cfg.key] !== undefined ? dirty[cfg.key] : cfg.value;
                    const isInt = cfg.value_type === "int";
                    const isFloat = cfg.value_type === "float";
                    const isBool = cfg.value_type === "bool";

                    return (
                      <div key={cfg.key} className="settings-row">
                        <div className="settings-row-label">
                          <span className="settings-row-name">{cfg.display_name || cfg.key}</span>
                          <span className="settings-row-key">{cfg.key}</span>
                        </div>

                        <div className="settings-row-control">
                          {isBool ? (
                            <label className="settings-toggle">
                              <input
                                type="checkbox"
                                checked={displayVal === true || displayVal === "true" || displayVal === true}
                                onChange={(e) => handleChange(cfg.key, e.target.checked)}
                                disabled={!cfg.editable}
                              />
                              <span className="settings-toggle-slider" />
                            </label>
                          ) : (
                            <input
                              className="settings-input"
                              type={isInt || isFloat ? "number" : "text"}
                              step={isFloat ? "0.1" : "1"}
                              min={isInt ? 1 : isFloat ? 0.1 : undefined}
                              value={displayVal}
                              onChange={(e) => handleChange(cfg.key, e.target.value)}
                              disabled={!cfg.editable}
                            />
                          )}
                        </div>

                        <div className="settings-row-desc">{cfg.description}</div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </>
        )}
      </div>
    </AppLayout>
  );
}
