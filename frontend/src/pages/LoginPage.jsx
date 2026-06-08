import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import "./LoginPage.css";

export default function LoginPage() {
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

  // ── 计算光束角度：灯塔核心 → 目标元素中心 ──
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

  // ── 光束锁定到输入框 ──
  const snapBeamTo = useCallback((target) => {
    const beam = beamRef.current;
    if (!beam) return;
    isFocused.current = true;
    beam.classList.add("beam--pointed");
    beam.style.transform = `rotate(${calculateAngle(target)}deg)`;
  }, [calculateAngle]);

  // ── 恢复旋转 ──
  const releaseBeam = useCallback(() => {
    const beam = beamRef.current;
    if (!beam) return;
    isFocused.current = false;
    setTimeout(() => {
      if (!isFocused.current && beamRef.current) {
        beam.classList.remove("beam--pointed");
        beam.style.transform = "";
        // 强制 CSS 动画重启
        beam.style.animation = "none";
        void beam.offsetHeight; // force reflow
        beam.style.animation = "";
      }
    }, 120);
  }, []);

  // ── 窗口 resize 时重新计算 ──
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
        "登录失败，请检查用户名和密码。";
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-immersive">
      {/* ═══ 星空背景 ═══ */}
      <div className="login-stars" />

      {/* ═══ 灯塔 + 品牌 ═══ */}
      <div className="login-lighthouse-area">
        {/* 灯塔 SVG + 发光核心（共用一个容器，光束以此为原点） */}
        <div className="lighthouse-body">
          {/* 多层旋转光束 — 所有层从同一个原点发射 */}
          <div className="beam-stage" ref={beamRef}>
            <div className="beam-layer beam-layer--main" />
            <div className="beam-layer beam-layer--left" />
            <div className="beam-layer beam-layer--right" />
            <div className="beam-layer beam-layer--wide" />
            <div className="beam-layer beam-layer--glow" />
          </div>

          {/* 灯塔 SVG */}
          <div className="login-lighthouse-svg">
            <svg fill="none" height="180" width="120" viewBox="0 0 120 180">
              <path d="M20 180L40 60H80L100 180H20Z" fill="#1e3a8a" stroke="#0d9488" strokeWidth="2" />
              <path d="M28 140L36 100H84L92 140H28Z" fill="#0f172a" stroke="#0d9488" strokeWidth="2" />
              <rect fill="#0f172a" height="10" stroke="#0d9488" strokeWidth="2" width="60" x="30" y="50" />
              <rect fill="transparent" height="30" stroke="#0d9488" strokeWidth="2" width="30" x="45" y="20" />
              <path d="M40 20L60 0L80 20H40Z" fill="#1e3a8a" stroke="#0d9488" strokeWidth="2" />
            </svg>
          </div>

          {/* 发光核心 — 光束原点 */}
          <div className="lantern-core" ref={lanternCoreRef} />
        </div>

        {/* 品牌文字 */}
        <div className="login-brand-text">
          <h1>PharosDB</h1>
          <p>数据库可观测性平台</p>
        </div>
      </div>

      {/* ═══ 玻璃拟态登录卡片 ═══ */}
      <div className="login-glass-wrap">
        <div className="login-glass-card">
          <div className="login-glass-header">
            <h2>欢迎回来</h2>
            <p>登录您的账号继续使用</p>
          </div>

          {error && (
            <div className="login-glass-alert">
              <span className="material-symbols-outlined">error</span>
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="login-glass-form">
            {/* 用户名 */}
            <div className="login-glass-field">
              <label htmlFor="username">用户名 / USERNAME</label>
              <div className="input-dark-wrap">
                <span className="material-symbols-outlined input-dark-icon">person</span>
                <input
                  id="username"
                  ref={usernameRef}
                  type="text"
                  placeholder="Enter your username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  onFocus={() => snapBeamTo(usernameRef.current)}
                  onBlur={releaseBeam}
                  disabled={submitting}
                  required
                />
              </div>
            </div>

            {/* 密码 */}
            <div className="login-glass-field">
              <label htmlFor="password">密码 / PASSWORD</label>
              <div className="input-dark-wrap">
                <span className="material-symbols-outlined input-dark-icon">lock</span>
                <input
                  id="password"
                  ref={passwordRef}
                  type={showPwd ? "text" : "password"}
                  placeholder="Enter your password"
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

            {/* 记住我 + 忘记密码 */}
            <div className="login-glass-options">
              <label className="login-glass-remember">
                <input type="checkbox" />
                <span>记住我</span>
              </label>
              <a href="#" onClick={(e) => e.preventDefault()} className="login-glass-forgot">
                忘记密码?
              </a>
            </div>

            {/* 登录按钮 */}
            <button type="submit" className="login-glass-submit" disabled={submitting}>
              {submitting ? (
                <>
                  登录中…
                  <span className="material-symbols-outlined login-spinner">progress_activity</span>
                </>
              ) : (
                "登 录"
              )}
            </button>
          </form>
        </div>

        {/* Footer */}
        <div className="login-glass-footer">
          © 2026 PharosDB · v0.1.0
        </div>
      </div>
    </div>
  );
}
