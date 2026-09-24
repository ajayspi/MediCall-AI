// src/lib/api.ts — typed fetch client + react-query hooks (Docker/CI phase).
// Contracts: docs/uml/03-api-contracts.md + the backend serializers
// (backend/app/api/calls.py call_row). The 2 proof pages (live-calls,
// dashboard) render through useTodayCalls; the other 14 pages stay on
// components/mock until their domains get wired in a later stage.
//
// Fallback policy (NEXT_PUBLIC_USE_MOCK, default "auto"):
//   true  -> never fetch, always mock (offline dev)
//   false -> always fetch, no fallback (production)
//   auto  -> try the API, fall back to mock on error/empty (local dev)

import { useQuery } from "@tanstack/react-query";
import { clinicKpis, todayCalls } from "@/components/mock";

const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL ?? "";
const USE_MOCK = (process.env.NEXT_PUBLIC_USE_MOCK ?? "auto").toLowerCase();

const TERMINAL_STATES = ["COMPLETE", "DROPPED", "PAYMENT_EXPIRED"];

// ---- backend contract types (app/api/calls.py call_row) -------------------

export type ApiCall = {
  id: string;
  clinic_id: string;
  caller_number: string | null;
  caller_language: string;
  state: string;
  started_at: string | null;
  ended_at: string | null;
  duration_seconds: number;
  transcript: unknown[];
  stt_confidence: number | null;
  triage_severity: string | null;
  diagnosed_conditions: string[];
  prescription_issued: boolean | null;
  appointment_scheduled: boolean | null;
  appointment_id: string | null;
  escalated_to_human: boolean | null;
};

// Display shape — matches what the dashboard shells already render
// (components/mock.ts MockCall), so page JSX barely changes.
export type CallView = {
  id: string;
  caller: string;
  language: string;
  state: string;
  severity: string;
  duration: string;
  complaint: string;
  startedAt: string;
};

export type Kpi = { label: string; value: string; trend: string; trendUp: boolean };

// ---- mapping helpers --------------------------------------------------------

function pad(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds || 0));
  return `${pad(Math.floor(s / 60))}:${pad(s % 60)}`;
}

export function formatStartTime(iso: string | null): string {
  if (!iso) return "--:--";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "--:--";
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function toCallView(c: ApiCall): CallView {
  return {
    id: c.id.slice(0, 8).toUpperCase(),
    caller: c.caller_number ?? "unknown",
    language: c.caller_language || "en",
    state: c.state,
    severity: c.triage_severity ?? "green",
    duration: formatDuration(c.duration_seconds),
    complaint: c.diagnosed_conditions?.[0] ?? "",
    startedAt: formatStartTime(c.started_at),
  };
}

function buildKpis(base: Kpi[], calls: CallView[]): Kpi[] {
  const active = calls.filter((c) => !TERMINAL_STATES.includes(c.state)).length;
  return base.map((k) => {
    if (k.label === "Calls Today") return { ...k, value: String(calls.length) };
    if (k.label === "Active Calls") return { ...k, value: String(active) };
    return k;
  });
}

// ---- queries -----------------------------------------------------------------

async function fetchCalls(clinicId: string): Promise<ApiCall[]> {
  const token = getToken();
  const headers: Record<string, string> = { Accept: "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(
    `${API_BASE}/api/calls?clinic_id=${encodeURIComponent(clinicId)}`,
    { headers },
  );
  if (!res.ok) throw new Error(`GET /api/calls -> ${res.status}`);
  return (await res.json()) as ApiCall[];
}

export function useCalls(clinicId: string) {
  return useQuery({
    queryKey: ["calls", clinicId],
    queryFn: () => fetchCalls(clinicId),
    enabled: USE_MOCK !== "true",
    placeholderData: () => [],
  });
}

export function useTodayCalls(baseKpis: Kpi[] = clinicKpis) {
  const clinicId = process.env.NEXT_PUBLIC_CLINIC_ID ?? "";
  const q = useCalls(clinicId);
  const apiCalls = (q.data ?? []).map(toCallView);
  const useFallback =
    USE_MOCK === "true" ||
    (USE_MOCK !== "false" && (q.isError || apiCalls.length === 0));
  const calls = useFallback ? todayCalls : apiCalls;
  const kpis = useFallback ? baseKpis : buildKpis(baseKpis, calls);
  return { calls, kpis, isLive: !useFallback, isLoading: q.isPending };
}

// ---- auth surface (Phase-1, G6-Q1 — spec-auth.md) ---------------------------
// Tokens are stateless HMAC-SHA256 JWTs from POST /api/auth/*; localStorage
// holds the bearer token; demo mode (NEXT_PUBLIC_USE_MOCK=true/auto) issues a
// local demo token so offline dev still reaches the dashboard shells.

const TOKEN_KEY = "medicall_token";

export type AuthUser = {
  id: string;
  name: string;
  phone: string | null;
  email: string | null;
  role: string;
  memberships?: { clinic_id: string; role: string }[];
};

export type AuthSession = {
  access_token: string;
  token_type: string;
  user: AuthUser;
};

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return (await res.json()) as T;
}

export function loginPassword(username: string, password: string): Promise<AuthSession> {
  return apiPost<AuthSession>("/api/auth/login", { username, password });
}

export function loginOtpRequest(phone: string): Promise<{ status: string; expires_in: number }> {
  return apiPost<{ status: string; expires_in: number }>("/api/auth/otp/request", { phone });
}

export function loginOtpVerify(phone: string, code: string): Promise<AuthSession> {
  return apiPost<AuthSession>("/api/auth/otp/verify", { phone, code });
}

export function registerUser(input: {
  name: string;
  phone?: string;
  email?: string;
  password: string;
}): Promise<AuthUser> {
  return apiPost<AuthUser>("/api/auth/register", input);
}

export async function fetchMe(token: string): Promise<AuthUser> {
  const res = await fetch(`${API_BASE}/api/auth/me`, {
    headers: { Accept: "application/json", Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`GET /api/auth/me -> ${res.status}`);
  return (await res.json()) as AuthUser;
}