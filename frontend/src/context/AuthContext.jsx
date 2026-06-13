import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import api from "../services/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ips, setIps] = useState(null);       // IP info from login response
  const [loading, setLoading] = useState(true);

  // ── Restore session from stored token ──
  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      setLoading(false);
      return;
    }
    // Restore saved IP info if available
    const savedIps = localStorage.getItem("pharos_ips");
    if (savedIps) {
      try { setIps(JSON.parse(savedIps)); } catch { /* ignore */ }
    }
    api
      .get("/auth/me/")
      .then(({ data }) => setUser(data))
      .catch(() => {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        localStorage.removeItem("pharos_ips");
      })
      .finally(() => setLoading(false));
  }, []);

  // ── Login ──
  const login = useCallback(async (username, password) => {
    const { data } = await api.post("/auth/login/", { username, password });
    localStorage.setItem("access_token", data.access);
    localStorage.setItem("refresh_token", data.refresh);
    if (data.ips) {
      setIps(data.ips);
      localStorage.setItem("pharos_ips", JSON.stringify(data.ips));
    }
    setUser(data.user);
    return data.user;
  }, []);

  // ── Logout ──
  const logout = useCallback(async () => {
    try {
      const refresh = localStorage.getItem("refresh_token");
      await api.post("/auth/logout/", { refresh });
    } finally {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      localStorage.removeItem("pharos_ips");
      setUser(null);
      setIps(null);
    }
  }, []);

  const value = useMemo(
    () => ({ user, ips, loading, login, logout, isAuthenticated: !!user }),
    [user, ips, loading, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
