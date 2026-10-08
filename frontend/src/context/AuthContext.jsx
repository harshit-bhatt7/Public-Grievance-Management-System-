import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { ApiError, getCurrentUser, login as apiLogin, logout as apiLogout, refreshSession, registerCitizen } from "../services/api";

/**
 * Global authentication state.
 *
 * Token storage strategy (documented in docs/architecture.md):
 * - The refresh token lives only in an HttpOnly, SameSite=Lax cookie set
 *   by the backend — it is never readable by frontend JavaScript.
 * - The access token is kept only in React state (memory). It is lost on
 *   full page reload by design, so on mount we silently call /api/auth/refresh
 *   (which relies on the cookie) to obtain a fresh one and restore the session.
 */
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [accessToken, setAccessToken] = useState(null);
  const [initializing, setInitializing] = useState(true);

  useEffect(() => {
    let cancelled = false;

    refreshSession()
      .then((data) => {
        if (cancelled) return;
        setAccessToken(data.access_token);
        setUser(data.user);
      })
      .catch(() => {
        // No valid session cookie yet — that's expected for a first visit.
      })
      .finally(() => {
        if (!cancelled) setInitializing(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const register = useCallback(async (payload) => {
    return registerCitizen(payload);
  }, []);

  const login = useCallback(async (credentials) => {
    const data = await apiLogin(credentials);
    setAccessToken(data.access_token);
    setUser(data.user);
    return data.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } finally {
      setAccessToken(null);
      setUser(null);
    }
  }, []);

  const refreshProfile = useCallback(async () => {
    if (!accessToken) return null;
    const freshUser = await getCurrentUser(accessToken);
    setUser(freshUser);
    return freshUser;
  }, [accessToken]);

  const value = useMemo(
    () => ({
      user,
      accessToken,
      isAuthenticated: Boolean(accessToken && user),
      initializing,
      register,
      login,
      logout,
      refreshProfile,
    }),
    [user, accessToken, initializing, register, login, logout, refreshProfile]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}

export { ApiError };
