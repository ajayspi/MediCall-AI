"use client";

// src/lib/auth.tsx — client auth context + route guard (spec-auth.md Q3).
// Token lives in localStorage (stateless HMAC JWT from /api/auth/*). The
// RequireAuth guard only enforces when NEXT_PUBLIC_USE_MOCK === "false"
// (production); in "true"/"auto" (offline dev) the demo login lets pages
// render without a backend.

import { createContext, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AuthSession,
  clearToken,
  fetchMe,
  getToken,
  loginOtpVerify,
  loginPassword,
  setToken,
  type AuthUser,
} from "@/lib/api";

const USE_MOCK = (process.env.NEXT_PUBLIC_USE_MOCK ?? "auto").toLowerCase();

const DEMO_USER: AuthUser = {
  id: "demo-user",
  name: "Demo Operator",
  phone: "+919900000000",
  email: null,
  role: "owner",
  memberships: [],
};

type AuthContextValue = {
  user: AuthUser | null;
  token: string | null;
  loading: boolean;
  /** Adopt a real session returned by /api/auth/login or /otp/verify. */
  adoptSession: (session: AuthSession) => void;
  /** Password login (throws on 401). */
  login: (username: string, password: string) => Promise<void>;
  /** OTP login — needs a prior requestOtp(phone). */
  loginWithOtp: (phone: string, code: string) => Promise<void>;
  logout: () => void;
  /** Offline/demo login — issues a local demo token when USE_MOCK != false. */
  demoLogin: () => boolean;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setTokenState] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Hydrate from localStorage after mount. Deferred to a macrotask so every
  // state flip is async (the react-hooks/set-state-in-effect rule — and SSR
  // hydration stability — forbid synchronous setState in the effect body).
  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      const stored = getToken();
      if (cancelled) return;
      if (!stored) {
        setLoading(false);
        return;
      }
      setTokenState(stored);
      setLoading(false);
      fetchMe(stored)
        .then((me) => {
          if (!cancelled) setUser(me);
        })
        .catch(() => {
          // expired/invalid token — stay logged out
          if (!cancelled) clearToken();
        });
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, []);

  function adoptSession(session: AuthSession) {
    setToken(session.access_token);
    setUser(session.user);
    setTokenState(session.access_token);
  }

  async function login(username: string, password: string) {
    adoptSession(await loginPassword(username, password));
  }

  async function loginWithOtp(phone: string, code: string) {
    adoptSession(await loginOtpVerify(phone, code));
  }

  function logout() {
    clearToken();
    setTokenState(null);
    setUser(null);
  }

  function demoLogin(): boolean {
    if (USE_MOCK === "false") return false;
    setToken("demo-token");
    setTokenState("demo-token");
    setUser(DEMO_USER);
    return true;
  }

  return (
    <AuthContext.Provider
      value={{ user, token, loading, adoptSession, login, loginWithOtp, logout, demoLogin }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}

export function RequireAuth({
  mode = USE_MOCK,
  children,
}: {
  /** "false" = enforce (production); "true"/"auto" = allow offline demo. */
  mode?: string;
  children: React.ReactNode;
}) {
  const { token, loading } = useAuth();
  const router = useRouter();
  const hardGuard = mode === "false";

  useEffect(() => {
    if (hardGuard && !loading && !token) router.replace("/login");
  }, [hardGuard, loading, token, router]);

  if (hardGuard && !loading && !token) return null;
  return <>{children}</>;
}