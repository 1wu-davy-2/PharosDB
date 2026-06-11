import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../context/AuthContext";
import i18n from "../i18n";
import "./LoginPage.css";

export default function LoginPage() {
  const { t } = useTranslation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const beamRef = useRef(null);
  const lanternCoreRef = useRef(null);
  const usernameRef = useRef(null);
  const passwordRef = useRef(null);
  const isFocused = useRef(false);

  const calculateAngle = useCallback((target) => {
    const core = lanternCoreRef.current;
    if (!core || !target) return 0;
    const cr = core.getBoundingClientRect();
    const tr = target.getBoundingClientRect();
    const cx = cr.left + cr.width / 2;
    const cy = cr.top + cr.height / 2;
    const tx = tr.left + tr.width / 2;
    const ty = tr.top + tr.height / 2;
    let deg = Math.atan2(ty - cy, tx - cx) * (180 / Math.PI) - 90;
    if (deg < 0) deg += 360;
    return deg;
  }, []);

  const snapBeamTo = useCallback((target) => {
    const beam = beamRef.current;
    if (!beam) return;
    isFocused.current = true;
    beam.classList.add("beam--pointed");
    beam.style.transform = `rotate(${calculateAngle(target)}deg)`;
  }, [calculateAngle]);

  const releaseBeam = useCallback(() => {
    const beam = beamRef.current;
    if (!beam) return;
    isFocused.current = false;
    setTimeout(() => {
      if (!isFocused.current && beamRef.current) {
        beam.classList.remove("beam--pointed");
        beam.style.transform = "";
        beam.style.animation = "none";
        void beam.offsetHeight;
        beam.style.animation = "";
      }
    }, 120);
  }, []);

  useEffect(() => {
    const onResize = () => {
      if (document.activeElement === usernameRef.current) {
        snapBeamTo(usernameRef.current);
      } else if (document.activeElement === passwordRef.current) {
        snapBeamTo(passwordRef.current);
      }
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [snapBeamTo]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(username, password);
      navigate("/", { replace: true });
    } catch (err) {
      const msg =
        err.response?.data?.non_field_errors?.[0] ||
        err.response?.data?.detail ||
        t("login.error_default");
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const toggleLang = () => {
    const next = i18n.language === "zh" ? "en" : "zh";
    i18n.changeLanguage(next);
    localStorage.setItem("pharos_lang", next);
  };

  return (
    <div className="login-immersive">
      {/* 语言切换按钮 */}
      <button className="login-lang-btn" onClick={toggleLang}>
        {i18n.language === "zh" ? "EN" : "中"}
      </button>

      <div className="login-stars" />

      <div className="login-lighthouse-area">
        <div className="lighthouse-body">
          <div className="beam-stage" ref={beamRef}>
            <div className="beam-layer beam-layer--main" />
            <div className="beam-layer beam-layer--left" />
            <div className="beam-layer beam-layer--right" />
            <div className="beam-layer beam-layer--wide" />
            <div className="beam-layer beam-layer--glow" />
          </div>

          <div className="login-lighthouse-svg">
            <svg fill="none" height="180" width="120" viewBox="0 0 120 180">
              <path d="M20 180L40 60H80L100 180H20Z" fill="#1e3a8a" stroke="#0d9488" strokeWidth="2" />
              <path d="M28 140L36 100H84L92 140H28Z" fill="#0f172a" stroke="#0d9488" strokeWidth="2" />
              <rect fill="#0f172a" height="10" stroke="#0d9488" strokeWidth="2" width="60" x="30" y="50" />
              <rect fill="transparent" height="30" stroke="#0d9488" strokeWidth="2" width="30" x="45" y="20" />
              <path d="M40 20L60 0L80 20H40Z" fill="#1e3a8a" stroke="#0d9488" strokeWidth="2" />
            </svg>
          </div>

          <div className="lantern-core" ref={lanternCoreRef} />
        </div>

        <div className="login-brand-text">
          <h1>PharosDB</h1>
          <p>{t("login.subtitle")}</p>
        </div>
      </div>

      <div className="login-glass-wrap">
        <div className="login-glass-card">
          <div className="login-glass-header">
            <h2>{t("login.welcome")}</h2>
            <p>{t("login.welcome_sub")}</p>
          </div>

          {error && (
            <div className="login-glass-alert">
              <span className="material-symbols-outlined">error</span>
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="login-glass-form">
            <div className="login-glass-field">
              <label htmlFor="username">{t("login.username_label")}</label>
              <div className="input-dark-wrap">
                <span className="material-symbols-outlined input-dark-icon">person</span>
                <input
                  id="username"
                  ref={usernameRef}
                  type="text"
                  placeholder={t("login.username_placeholder")}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  onFocus={() => snapBeamTo(usernameRef.current)}
                  onBlur={releaseBeam}
                  disabled={submitting}
                  required
                />
              </div>
            </div>

            <div className="login-glass-field">
              <label htmlFor="password">{t("login.password_label")}</label>
              <div className="input-dark-wrap">
                <span className="material-symbols-outlined input-dark-icon">lock</span>
                <input
                  id="password"
                  ref={passwordRef}
                  type={showPwd ? "text" : "password"}
                  placeholder={t("login.password_placeholder")}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onFocus={() => snapBeamTo(passwordRef.current)}
                  onBlur={releaseBeam}
                  disabled={submitting}
                  required
                />
                <button
                  type="button"
                  className="input-dark-eye"
                  onClick={() => setShowPwd(!showPwd)}
                  tabIndex={-1}
                >
                  <span className="material-symbols-outlined">
                    {showPwd ? "visibility_off" : "visibility"}
                  </span>
                </button>
              </div>
            </div>

            <div className="login-glass-options">
              <label className="login-glass-remember">
                <input type="checkbox" />
                <span>{t("login.remember")}</span>
              </label>
              <a href="#" onClick={(e) => e.preventDefault()} className="login-glass-forgot">
                {t("login.forgot")}
              </a>
            </div>

            <button type="submit" className="login-glass-submit" disabled={submitting}>
              {submitting ? (
                <>
                  {t("login.submitting")}
                  <span className="material-symbols-outlined login-spinner">progress_activity</span>
                </>
              ) : (
                t("login.submit")
              )}
            </button>
          </form>
        </div>

        <div className="login-glass-footer">
          © 2026 PharosDB · v0.1.0
        </div>
      </div>
    </div>
  );
}
