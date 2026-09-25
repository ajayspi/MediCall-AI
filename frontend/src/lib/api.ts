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
import {
  clinicKpis,
  todayCalls,
  liveCallKpis as mockLiveCallKpis,
  triageQueue as mockTriageQueue,
  appointmentKpis as mockAppointmentKpis,
  appointments as mockAppointments,
  prescriptionKpis as mockPrescriptionKpis,
  prescriptions as mockPrescriptions,
  patientKpis as mockPatientKpis,
  patients as mockPatients,
  analyticsKpis as mockAnalyticsKpis,
  hourlyCalls as mockHourlyCalls,
  languageMix as mockLanguageMix,
  severityMix as mockSeverityMix,
  adminKpis as mockAdminKpis,
  platformClinics as mockPlatformClinics,
  platformPatients as mockPlatformPatients,
  revenueKpis as mockRevenueKpis,
  gateways as mockGateways,
  invoices as mockInvoices,
} from "@/components/mock";

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

// ─── G6-Q11 wiring: generic authed GET + platform helpers ──────────────────
// Hook fallback policy is identical to useTodayCalls: NEXT_PUBLIC_USE_MOCK
// "true" -> always fixtures, "false" -> always fetch, "auto" (default) ->
// try the API and fall back to the mock fixtures on error/empty.

async function authFetch<T>(path: string): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = { Accept: "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}${path}`, { headers });
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`);
  return (await res.json()) as T;
}

function clinicId(): string {
  return process.env.NEXT_PUBLIC_CLINIC_ID ?? "";
}

export function formatINR(amount: number): string {
  // Indian number grouping (lakh/crore): 124500 -> ₹1,24,500.
  const n = Math.round((amount || 0) * 100) / 100;
  const neg = n < 0;
  const abs = Math.abs(n);
  const intPart = Math.floor(abs).toString();
  const dec = Math.round((abs - Math.floor(abs)) * 100);
  const last3 = intPart.slice(-3);
  const rest = intPart.slice(0, -3);
  const grouped = rest
    ? `${rest.replace(/\B(?=(\d{2})+(?!\d))/g, ",")},${last3}`
    : last3;
  const suffix = dec > 0 ? `.${dec.toString().padStart(2, "0")}` : "";
  return `${neg ? "-" : ""}₹${grouped}${suffix}`;
}

export function formatRelativeDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const today = new Date();
  const startOfToday = new Date(
    today.getFullYear(),
    today.getMonth(),
    today.getDate(),
  );
  const startOfDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const days = Math.round(
    (startOfToday.getTime() - startOfDay.getTime()) / 86_400_000,
  );
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  const months = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];
  return `${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()}`;
}

// ---- backend contract types (app/api/appointments, prescriptions, admin) ---

export type ApiAppointment = {
  id: string;
  clinic_id: string;
  patient_name: string | null;
  patient_phone: string | null;
  patient_language: string;
  caller_id: string | null;
  scheduled_at: string | null;
  status: string;
  reason: string | null;
  doctor_id: string | null;
  duration_minutes: number;
  location: string | null;
};

export type ApiPrescription = {
  id: string;
  clinic_id: string;
  patient_name: string | null;
  patient_phone: string | null;
  patient_language: string;
  caller_id: string | null;
  medication: string;
  dosage: string | null;
  frequency: string | null;
  instructions: string | null;
  doctor_id: string | null;
  status: string;
  pharmacy_name: string | null;
};

export type ApiAdminOverview = {
  clinics_total: number;
  clinics_active: number;
  calls_today: number;
  live_calls: number;
  revenue_today_inr: number;
};

export type ApiAdminClinic = {
  id: string;
  name: string;
  city: string | null;
  state: string | null;
  plan: string | null;
  is_active: boolean;
  calls_mtd: number;
  calls_today: number;
  live_calls: number;
};

export type ApiAdminPatient = {
  caller_number: string;
  clinic_id: string | null;
  clinic_name: string | null;
  language: string | null;
  first_call_at: string | null;
  last_call_at: string | null;
  call_count: number;
  last_state: string | null;
};

export type ApiAdminRevenue = {
  captured_inr: number;
  pending_inr: number;
  failed_inr: number;
  refunded_inr: number;
  count: number;
  by_gateway: Record<string, { captured_inr: number; count: number }>;
  by_clinic: {
    clinic_id: string;
    clinic_name: string | null;
    captured_inr: number;
    count: number;
  }[];
};

export type ApiAdminCall = {
  id: string;
  clinic_id: string;
  clinic_name: string | null;
  caller_number: string | null;
  language: string | null;
  state: string;
  severity: string | null;
  started_at: string | null;
  duration_seconds: number;
};

// ---- display shapes (mirror the mock fixtures so page JSX barely changes) --

export type AppointmentView = {
  time: string;
  patient: string;
  doctor: string;
  reason: string;
  status: string;
};

export type PrescriptionView = {
  patient: string;
  medicine: string;
  dosage: string;
  frequency: string;
  doctor: string;
  status: string;
};

export type RecentCallerView = {
  name: string;
  phone: string;
  language: string;
  lastVisit: string;
  calls: number;
};

export type AdminClinicView = {
  name: string;
  city: string;
  plan: string;
  status: string;
  callsMtd: number;
  seats: string | number;
};

export type AdminPatientView = {
  name: string;
  phone: string;
  clinic: string;
  language: string;
  lastActivity: string;
};

export type AdminLiveCallView = {
  id: string;
  clinicName: string;
  language: string;
  state: string;
  duration: string;
};

export type GatewayView = {
  name: string;
  status: string;
  txns: number;
  share: string;
};

export type InvoiceView = {
  id: string;
  clinic: string;
  amount: string;
  gateway: string;
  status: string;
};

// ---- mapping helpers --------------------------------------------------------

const APPOINTMENT_DISPLAY: Record<string, string> = {
  pending: "Pending",
  confirmed: "Confirmed",
  completed: "Completed",
  cancelled: "Cancelled",
  no_show: "No-show",
};

const PRESCRIPTION_DISPLAY: Record<string, string> = {
  pending: "Pending",
  approved: "Active",
  sent_pharmacy: "Sent Pharmacy",
  dispensed: "Dispensed",
};

function doctorLabel(doctorId: string | null): string {
  return doctorId ? `Doc ${doctorId.slice(0, 8).toUpperCase()}` : "Unassigned";
}

export function toAppointmentView(a: ApiAppointment): AppointmentView {
  return {
    time: formatStartTime(a.scheduled_at),
    patient: a.patient_name ?? "Unknown caller",
    doctor: doctorLabel(a.doctor_id),
    reason: a.reason ?? "—",
    status: APPOINTMENT_DISPLAY[a.status] ?? a.status,
  };
}

export function toPrescriptionView(p: ApiPrescription): PrescriptionView {
  return {
    patient: p.patient_name ?? "Unknown caller",
    medicine: p.medication,
    dosage: p.dosage ?? "—",
    frequency: p.frequency ?? "—",
    doctor: doctorLabel(p.doctor_id),
    status: PRESCRIPTION_DISPLAY[p.status] ?? p.status,
  };
}

export function toRecentCallers(calls: ApiCall[]): RecentCallerView[] {
  const byNumber = new Map<string, { last: ApiCall; count: number }>();
  for (const c of calls) {
    const key = c.caller_number ?? "unknown";
    const cur = byNumber.get(key);
    if (!cur) {
      byNumber.set(key, { last: c, count: 1 });
    } else {
      cur.count += 1;
      if ((c.started_at ?? "") > (cur.last.started_at ?? "")) cur.last = c;
    }
  }
  return [...byNumber.entries()]
    .sort((a, b) =>
      (b[1].last.started_at ?? "").localeCompare(a[1].last.started_at ?? ""),
    )
    .map(([number, { last, count }]) => ({
      name: number,
      phone: number,
      language: last.caller_language || "en",
      lastVisit: formatRelativeDate(last.started_at),
      calls: count,
    }));
}

export function toAdminClinicView(c: ApiAdminClinic): AdminClinicView {
  return {
    name: c.name,
    city: c.city ?? "—",
    plan: c.plan ?? "—",
    status: c.is_active ? "Active" : "Paused",
    callsMtd: c.calls_mtd,
    seats: "—",
  };
}

export function toAdminPatientView(p: ApiAdminPatient): AdminPatientView {
  return {
    name: p.caller_number,
    phone: p.caller_number,
    clinic: p.clinic_name ?? "—",
    language: p.language ?? "en",
    lastActivity: formatRelativeDate(p.last_call_at),
  };
}

export function toAdminLiveCallView(c: ApiAdminCall): AdminLiveCallView {
  return {
    id: c.id.slice(0, 8).toUpperCase(),
    clinicName: c.clinic_name ?? "—",
    language: c.language || "en",
    state: c.state,
    duration: formatDuration(c.duration_seconds),
  };
}

function formatWaiting(iso: string | null): string {
  if (!iso) return "--:--";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "--:--";
  const mins = Math.max(0, Math.floor((Date.now() - d.getTime()) / 60_000));
  return `${pad(Math.floor(mins / 60))}:${pad(mins % 60)}`;
}

// ---- clinic-domain hooks ----------------------------------------------------

export function useTriageQueue() {
  const cid = clinicId();
  const q = useQuery({
    queryKey: ["triage-queue", cid],
    queryFn: () => fetchCalls(cid),
    enabled: USE_MOCK !== "true",
    placeholderData: () => [],
  });
  const live = (q.data ?? [])
    .filter((c) => !TERMINAL_STATES.includes(c.state))
    .map((c) => ({
      id: c.id.slice(0, 8).toUpperCase(),
      caller: c.caller_number ?? "unknown",
      language: c.caller_language || "en",
      complaint: c.diagnosed_conditions?.[0] ?? "",
      severity: c.triage_severity ?? "green",
      waiting: formatWaiting(c.started_at),
    }));
  const useFallback =
    USE_MOCK === "true" ||
    (USE_MOCK !== "false" && (q.isError || live.length === 0));
  return useFallback ? mockTriageQueue : live;
}

export function useAppointments() {
  const cid = clinicId();
  const q = useQuery({
    queryKey: ["appointments", cid],
    queryFn: () =>
      authFetch<ApiAppointment[]>(
        `/api/appointments?clinic_id=${encodeURIComponent(cid)}`,
      ),
    enabled: USE_MOCK !== "true",
    placeholderData: () => [],
  });
  const rows = (q.data ?? []).map(toAppointmentView);
  const useFallback =
    USE_MOCK === "true" ||
    (USE_MOCK !== "false" && (q.isError || rows.length === 0));
  if (useFallback) return { rows: mockAppointments, kpis: mockAppointmentKpis };
  const count = (status: string) => rows.filter((r) => r.status === status).length;
  const kpis: Kpi[] = [
    {
      label: "Today's Appointments",
      value: String(rows.length),
      trend: "live schedule",
      trendUp: true,
    },
    {
      label: "Pending Confirmation",
      value: String(count("Pending")),
      trend: "SMS pending",
      trendUp: true,
    },
    {
      label: "Completed",
      value: String(count("Completed")),
      trend: "on track",
      trendUp: true,
    },
    {
      label: "No-shows",
      value: String(count("No-show")),
      trend: "reminder sent",
      trendUp: false,
    },
  ];
  return { rows, kpis };
}

export function usePrescriptions() {
  const cid = clinicId();
  const q = useQuery({
    queryKey: ["prescriptions", cid],
    queryFn: () =>
      authFetch<ApiPrescription[]>(
        `/api/prescriptions?clinic_id=${encodeURIComponent(cid)}`,
      ),
    enabled: USE_MOCK !== "true",
    placeholderData: () => [],
  });
  const rows = (q.data ?? []).map(toPrescriptionView);
  const useFallback =
    USE_MOCK === "true" ||
    (USE_MOCK !== "false" && (q.isError || rows.length === 0));
  if (useFallback) {
    return { rows: mockPrescriptions, kpis: mockPrescriptionKpis };
  }
  const count = (status: string) => rows.filter((r) => r.status === status).length;
  const kpis: Kpi[] = [
    {
      label: "Issued Today",
      value: String(rows.length),
      trend: "via voice agent",
      trendUp: true,
    },
    {
      label: "Pending Approval",
      value: String(count("Pending")),
      trend: "doctor review",
      trendUp: false,
    },
    {
      label: "Dispensed",
      value: String(count("Dispensed")),
      trend: "pharmacy done",
      trendUp: true,
    },
  ];
  return { rows, kpis };
}

export function useRecentCallers() {
  const cid = clinicId();
  const q = useQuery({
    queryKey: ["recent-callers", cid],
    queryFn: () => fetchCalls(cid),
    enabled: USE_MOCK !== "true",
    placeholderData: () => [],
  });
  const rows = toRecentCallers(q.data ?? []);
  const useFallback =
    USE_MOCK === "true" ||
    (USE_MOCK !== "false" && (q.isError || rows.length === 0));
  if (useFallback) return { rows: mockPatients, kpis: mockPatientKpis };
  const repeat = rows.length
    ? Math.round((rows.filter((r) => r.calls > 1).length / rows.length) * 100)
    : 0;
  const langs = new Set(rows.map((r) => r.language)).size;
  const kpis: Kpi[] = [
    {
      label: "Total Patients",
      value: rows.length.toLocaleString(),
      trend: "unique callers",
      trendUp: true,
    },
    {
      label: "Repeat Callers",
      value: `${repeat}%`,
      trend: "called more than once",
      trendUp: true,
    },
    {
      label: "Languages Served",
      value: String(langs),
      trend: "hi · en · ta · te · bn",
      trendUp: true,
    },
  ];
  return { rows, kpis };
}

// ---- analytics (all 8 /api/analytics endpoints; page uses 4 + calls) -------

const ANALYTICS_PATHS: Record<string, string> = {
  volume: "/api/analytics/volume",
  resolution: "/api/analytics/resolution",
  triage: "/api/analytics/triage",
  language: "/api/analytics/language",
  "no-show": "/api/analytics/no-show",
  revenue: "/api/analytics/revenue",
  delivery: "/api/analytics/delivery",
  benchmarks: "/api/analytics/benchmarks",
};

function analyticsPath(slug: keyof typeof ANALYTICS_PATHS, cid: string): string {
  const path = ANALYTICS_PATHS[slug];
  return slug === "benchmarks" ? path : `${path}?clinic_id=${encodeURIComponent(cid)}`;
}

type VolumePayload = {
  calls: {
    total: number;
    by_state: Record<string, number>;
    avg_duration_seconds: number | null;
  };
};
type ResolutionPayload = { resolution_rate: number | null; counts: Record<string, number> };
type LanguagePayload = { language_dist: Record<string, number> };
type TriagePayload = { triage_mix: Record<string, number> };

const LANG_LABELS: Record<string, string> = {
  hi: "हिन्दी",
  en: "English",
  ta: "தமிழ்",
  te: "తెలుగు",
  bn: "বাংলা",
};

export function useAnalyticsKpis() {
  const cid = clinicId();
  const volumeQ = useQuery({
    queryKey: ["analytics-volume", cid],
    queryFn: () => authFetch<VolumePayload>(analyticsPath("volume", cid)),
    enabled: USE_MOCK !== "true",
    placeholderData: () => ({
      calls: { total: 0, by_state: {}, avg_duration_seconds: null },
    }),
  });
  const resolutionQ = useQuery({
    queryKey: ["analytics-resolution", cid],
    queryFn: () => authFetch<ResolutionPayload>(analyticsPath("resolution", cid)),
    enabled: USE_MOCK !== "true",
    placeholderData: () => ({ resolution_rate: null, counts: {} }),
  });
  const languageQ = useQuery({
    queryKey: ["analytics-language", cid],
    queryFn: () => authFetch<LanguagePayload>(analyticsPath("language", cid)),
    enabled: USE_MOCK !== "true",
    placeholderData: () => ({ language_dist: {} }),
  });
  const triageQ = useQuery({
    queryKey: ["analytics-triage", cid],
    queryFn: () => authFetch<TriagePayload>(analyticsPath("triage", cid)),
    enabled: USE_MOCK !== "true",
    placeholderData: () => ({ triage_mix: {} }),
  });
  const callsQ = useQuery({
    queryKey: ["analytics-hourly", cid],
    queryFn: () => fetchCalls(cid),
    enabled: USE_MOCK !== "true",
    placeholderData: () => [],
  });

  const liveBroken =
    volumeQ.isError ||
    resolutionQ.isError ||
    languageQ.isError ||
    triageQ.isError ||
    callsQ.isError;
  const useFallback = USE_MOCK === "true" || (USE_MOCK !== "false" && liveBroken);
  if (useFallback) {
    return {
      kpis: mockAnalyticsKpis,
      hourlyCalls: mockHourlyCalls,
      languageMix: mockLanguageMix,
      severityMix: mockSeverityMix,
    };
  }

  const volume = volumeQ.data?.calls;
  const total = volume?.total ?? 0;
  const escalated = volume?.by_state?.ESCALATED ?? 0;
  const resolutionRate = resolutionQ.data?.resolution_rate ?? 0;

  const hourly = new Array<number>(24).fill(0);
  for (const c of callsQ.data ?? []) {
    if (!c.started_at) continue;
    const d = new Date(c.started_at);
    if (!Number.isNaN(d.getTime())) hourly[d.getHours()] += 1;
  }

  const langTotal = Object.values(languageQ.data?.language_dist ?? {}).reduce(
    (s, n) => s + n,
    0,
  );
  const languageMix = (
    Object.entries(languageQ.data?.language_dist ?? {}) as [string, number][]
  )
    .filter(([lang]) => LANG_LABELS[lang] !== undefined)
    .map(([lang, n]) => ({
      lang,
      label: LANG_LABELS[lang],
      pct: langTotal > 0 ? Math.round((n / langTotal) * 100) : 0,
    }))
    .sort((a, b) => b.pct - a.pct);

  const sevTotal = Object.values(triageQ.data?.triage_mix ?? {}).reduce(
    (s, n) => s + n,
    0,
  );
  const severityMix = (
    Object.entries(triageQ.data?.triage_mix ?? {}) as [string, number][]
  )
    .filter(([sev]) => sev !== "untriaged")
    .map(([sev, n]) => ({
      severity: sev,
      label: sev.charAt(0).toUpperCase() + sev.slice(1),
      pct: sevTotal > 0 ? Math.round((n / sevTotal) * 100) : 0,
    }));

  const kpis: Kpi[] = [
    {
      label: "Calls Today",
      value: String(total),
      trend: "live volume",
      trendUp: total > 0,
    },
    {
      label: "Avg Duration",
      value: formatDuration(volume?.avg_duration_seconds ?? 0),
      trend: "live avg",
      trendUp: true,
    },
    {
      label: "Resolution Rate",
      value: `${Math.round(resolutionRate * 100)}%`,
      trend: "COMPLETE / terminal",
      trendUp: true,
    },
    {
      label: "Escalation Rate",
      value: `${total > 0 ? Math.round((escalated / total) * 100) : 0}%`,
      trend: "vs target 5%",
      trendUp: escalated < total * 0.05,
    },
  ];

  return { kpis, hourlyCalls: hourly, languageMix, severityMix };
}

// ---- platform-admin hooks (all 5 /api/admin endpoints, platform-scoped) ----

export function useAdminOverview() {
  const overviewQ = useQuery({
    queryKey: ["admin-overview"],
    queryFn: () => authFetch<ApiAdminOverview>("/api/admin"),
    enabled: USE_MOCK !== "true",
  });
  const clinicsQ = useQuery({
    queryKey: ["admin-clinics"],
    queryFn: () => authFetch<ApiAdminClinic[]>("/api/admin/clinics"),
    enabled: USE_MOCK !== "true",
    placeholderData: () => [],
  });
  const useFallback =
    USE_MOCK === "true" ||
    (USE_MOCK !== "false" &&
      (overviewQ.isError || clinicsQ.isError || !overviewQ.data));
  if (useFallback) {
    return { kpis: mockAdminKpis, clinics: mockPlatformClinics };
  }
  const ov = overviewQ.data ?? {
    clinics_total: 0,
    clinics_active: 0,
    calls_today: 0,
    live_calls: 0,
    revenue_today_inr: 0,
  };
  const kpis: Kpi[] = [
    {
      label: "Active Clinics",
      value: String(ov.clinics_active),
      trend: "platform-wide",
      trendUp: true,
    },
    {
      label: "Calls Today",
      value: ov.calls_today.toLocaleString(),
      trend: "across all clinics",
      trendUp: true,
    },
    {
      label: "Live Calls",
      value: String(ov.live_calls),
      trend: "non-terminal",
      trendUp: true,
    },
    {
      label: "Revenue Today",
      value: formatINR(ov.revenue_today_inr),
      trend: "captured",
      trendUp: true,
    },
  ];
  return { kpis, clinics: (clinicsQ.data ?? []).map(toAdminClinicView) };
}

export function useAdminClinics() {
  const q = useQuery({
    queryKey: ["admin-clinics"],
    queryFn: () => authFetch<ApiAdminClinic[]>("/api/admin/clinics"),
    enabled: USE_MOCK !== "true",
    placeholderData: () => [],
  });
  const rows = (q.data ?? []).map(toAdminClinicView);
  const useFallback =
    USE_MOCK === "true" ||
    (USE_MOCK !== "false" && (q.isError || rows.length === 0));
  return useFallback ? mockPlatformClinics : rows;
}

export function useAdminPatients() {
  const q = useQuery({
    queryKey: ["admin-patients"],
    queryFn: () => authFetch<ApiAdminPatient[]>("/api/admin/patients"),
    enabled: USE_MOCK !== "true",
    placeholderData: () => [],
  });
  const rows = (q.data ?? []).map(toAdminPatientView);
  const useFallback =
    USE_MOCK === "true" ||
    (USE_MOCK !== "false" && (q.isError || rows.length === 0));
  return useFallback ? mockPlatformPatients : rows;
}

export function useAdminRevenue() {
  const q = useQuery({
    queryKey: ["admin-revenue"],
    queryFn: () => authFetch<ApiAdminRevenue>("/api/admin/revenue"),
    enabled: USE_MOCK !== "true",
  });
  const useFallback =
    USE_MOCK === "true" || (USE_MOCK !== "false" && (q.isError || !q.data));
  if (useFallback) {
    return { kpis: mockRevenueKpis, gateways: mockGateways, invoices: mockInvoices };
  }
  const rev = q.data ?? {
    captured_inr: 0,
    pending_inr: 0,
    failed_inr: 0,
    refunded_inr: 0,
    count: 0,
    by_gateway: {},
    by_clinic: [],
  };
  const kpis: Kpi[] = [
    {
      label: "Captured",
      value: formatINR(rev.captured_inr),
      trend: `${rev.count} payments`,
      trendUp: true,
    },
    {
      label: "Pending",
      value: formatINR(rev.pending_inr),
      trend: "awaiting capture",
      trendUp: false,
    },
    {
      label: "Failed",
      value: formatINR(rev.failed_inr),
      trend: "gateway declines",
      trendUp: false,
    },
    {
      label: "Refunded",
      value: formatINR(rev.refunded_inr),
      trend: "reversed",
      trendUp: false,
    },
  ];
  const entries = Object.entries(rev.by_gateway ?? {}).sort(
    (a, b) => b[1].captured_inr - a[1].captured_inr,
  );
  const gwTotal = entries.reduce((s, [, v]) => s + v.captured_inr, 0);
  const gateways = entries.map(([name, v]) => ({
    name,
    status: v.count > 0 ? "healthy" : "idle",
    txns: v.count,
    share: gwTotal > 0 ? `${Math.round((v.captured_inr / gwTotal) * 100)}%` : "0%",
  }));
  const invoices = (rev.by_clinic ?? []).map((c) => ({
    id: `CL-${c.clinic_id.slice(0, 8).toUpperCase()}`,
    clinic: c.clinic_name ?? "—",
    amount: formatINR(c.captured_inr),
    gateway: "—",
    status: "Paid",
  }));
  return { kpis, gateways, invoices };
}

export function useAdminLiveCalls() {
  const overviewQ = useQuery({
    queryKey: ["admin-overview"],
    queryFn: () => authFetch<ApiAdminOverview>("/api/admin"),
    enabled: USE_MOCK !== "true",
  });
  const callsQ = useQuery({
    queryKey: ["admin-calls"],
    queryFn: () => authFetch<ApiAdminCall[]>("/api/admin/calls?limit=200"),
    enabled: USE_MOCK !== "true",
    placeholderData: () => [],
  });
  const useFallback =
    USE_MOCK === "true" ||
    (USE_MOCK !== "false" &&
      (overviewQ.isError || callsQ.isError || !overviewQ.data));
  if (useFallback) {
    return {
      kpis: mockLiveCallKpis,
      calls: todayCalls.map((c) => ({
        id: c.id,
        clinicName: "City Care Clinic",
        language: c.language,
        state: c.state,
        duration: c.duration,
      })),
    };
  }
  const ov = overviewQ.data ?? {
    clinics_total: 0,
    clinics_active: 0,
    calls_today: 0,
    live_calls: 0,
    revenue_today_inr: 0,
  };
  const all = callsQ.data ?? [];
  const live = all.filter((c) => !TERMINAL_STATES.includes(c.state));
  const escCount = live.filter((c) => c.state === "ESCALATED").length;
  const avgDuration = live.length
    ? Math.round(live.reduce((s, c) => s + (c.duration_seconds || 0), 0) / live.length)
    : 0;
  const kpis: Kpi[] = [
    {
      label: "Active Calls",
      value: String(ov.live_calls),
      trend: "non-terminal",
      trendUp: true,
    },
    {
      label: "On Hold",
      value: "0",
      trend: "queueing not tracked",
      trendUp: false,
    },
    {
      label: "Escalated",
      value: String(escCount),
      trend: "in feed",
      trendUp: escCount === 0,
    },
    {
      label: "Avg Duration",
      value: formatDuration(avgDuration),
      trend: "active calls",
      trendUp: true,
    },
  ];
  return { kpis, calls: all.map(toAdminLiveCallView) };
}