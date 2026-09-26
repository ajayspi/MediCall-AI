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
  pvDashboard as mockPvDashboard,
  pvPsur as mockPvPsur,
  pvAudit as mockPvAudit,
  pvCases as mockPvCases,
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

// The clinic every hook scopes to. Exported so a page that must pass filters
// (usePvCases) can forward the same id the hook would have defaulted to,
// instead of duplicating the env lookup.
export function clinicId(): string {
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

// ---- PVOIC hooks (phase-2.5, spec-micc-pv-phase25.md) ----------------------
// The read-only PV / Medical Information console, off the approved 2E surface:
// /api/pv/dashboard, /api/pv/dashboard/psur, /api/pv/audit, /api/pv/cases.
// Same house policy as every other hook — "true" is always fixtures, "false" is
// always the API, "auto" (the default) tries the API and falls back to the
// fixtures on error, so local dev renders a full page instead of an empty one.
//
// THE INDIA CLOCK IS NOT RE-DERIVED HERE. days_remaining, hours_remaining and
// days_overdue are the server's own numbers (app/services/pv_dashboard.py,
// keyed off the Phase-1 compute_reporting_deadline), and the snapshot is
// re-read every 60s rather than counted down in the browser: a UI timer can
// disagree with the legal clock, so there is deliberately no setInterval
// anywhere in this console — a client countdown is never the record.

// ---- backend contract types (app/api/pv.py + services/pv_dashboard.py) ----

export type ApiPvOverdueEntry = {
  case_id: string;
  status: string;
  is_serious: boolean;
  notification_deadline: string;
  days_overdue: number;
};

export type ApiPvUpcomingEntry = {
  case_id: string;
  status: string;
  is_serious: boolean;
  notification_deadline: string;
  days_remaining: number;
  hours_remaining: number;
};

export type ApiPvPsurEntry = {
  product_id: string;
  product_name: string;
  anchor: string | null;
  anchor_field: string;
  age_days: number | null;
  due_now: boolean;
  next_window: string;
  next_due_date: string | null;
  days_remaining: number | null;
};

export type ApiPvPsur = {
  schedule: string;
  anchor_field: string;
  products: number;
  due_now: number;
  entries: ApiPvPsurEntry[];
};

export type ApiPvAuditEvent = {
  id: string;
  event_type: string;
  severity: string;
  status: string;
  detected_at: string;
  description: string;
};

export type ApiPvAudit = {
  window_days: number;
  count: number;
  by_event_type: Record<string, number>;
  events: ApiPvAuditEvent[];
};

export type ApiPvCase = {
  id: string;
  case_type: string;
  product_id: string | null;
  event_text: string;
  seriousness_flags: string[];
  patient_initials: string | null;
  patient_age: string | null;
  patient_sex: string | null;
  status: string;
  received_at: string;
  notification_deadline: string;
  days_remaining: number;
  overdue: boolean;
  e2b_minimum_met: boolean;
};

export type ApiPvCases = { cases: ApiPvCase[]; count: number };

export type ApiPvDashboard = {
  generated_at: string;
  cases: {
    by_type: { ae: number; pqc: number; mi: number; total: number };
    by_status: {
      open: number;
      overdue: number;
      notified: number;
      submitted: number;
      closed: number;
      unknown: number;
      total: number;
    };
  };
  clocks: {
    horizon_hours: number;
    overdue_count: number;
    overdue: ApiPvOverdueEntry[];
    upcoming_count: number;
    upcoming: ApiPvUpcomingEntry[];
  };
  pqc: {
    total: number;
    by_investigation_status: Record<string, number>;
    by_disposition: Record<string, number>;
  };
  mi: { total: number; by_status: Record<string, number> };
  psur: ApiPvPsur;
  audit: ApiPvAudit;
};

// ---- display shapes (mirror the mock.ts fixtures) --------------------------

export type PvBucket = { label: string; count: number };

export type PvOverdueRow = {
  caseId: string;
  status: string;
  isSerious: boolean;
  deadline: string;
  daysOverdue: number;
};

export type PvUpcomingRow = {
  caseId: string;
  status: string;
  isSerious: boolean;
  deadline: string;
  daysRemaining: number;
  hoursRemaining: number;
};

export type PvPsurRow = {
  productId: string;
  productName: string;
  anchor: string | null;
  ageDays: number | null;
  dueNow: boolean;
  nextWindow: string;
  nextDueDate: string | null;
  daysRemaining: number | null;
};

export type PvAuditRow = {
  id: string;
  eventType: string;
  severity: string;
  status: string;
  detectedAt: string;
  description: string;
};

/** One AE row as the 2E GET /cases returns it (product_id, never a name). */
export type PvCaseView = {
  id: string;
  caseType: string;
  product: string;
  patient: string;
  eventText: string;
  isSerious: boolean;
  criteria: string[];
  status: string;
  deadline: string;
  daysRemaining: number;
  overdue: boolean;
  receivedAt: string;
  e2bMinimumMet: boolean;
};

export type PvDashboardView = {
  generatedAt: string;
  kpis: Kpi[];
  horizonHours: number;
  overdue: PvOverdueRow[];
  upcoming: PvUpcomingRow[];
  pqcStages: PvBucket[];
  pqcDispositions: PvBucket[];
  psur: {
    products: number;
    dueNow: number;
    schedule: string;
    nextWindow: string;
    nextDueDate: string | null;
  };
  audit: { windowDays: number; count: number; digest: PvBucket[] };
};

export type PvPsurView = {
  schedule: string;
  anchorField: string;
  products: number;
  dueNow: number;
  entries: PvPsurRow[];
};

export type PvAuditView = {
  windowDays: number;
  count: number;
  digest: PvBucket[];
  events: PvAuditRow[];
};

// ---- mapping helpers --------------------------------------------------------

/** {status_or_stage: count} -> a stable, display-ready bucket list. */
function pvBuckets(counts: Record<string, number> | undefined): PvBucket[] {
  return Object.entries(counts ?? {}).map(([label, count]) => ({ label, count }));
}

/** "under_investigation" -> "Under investigation" (the state-machine stages). */
export function pvLabel(value: string): string {
  const words = value.replace(/_/g, " ").trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : value;
}

/** A case as the queue shows it: the dictionary id, never an invented name. */
function pvProductLabel(productId: string | null): string {
  return productId ? productId.slice(0, 8).toUpperCase() : "—";
}

function pvPatientLabel(c: ApiPvCase): string {
  const parts = [
    c.patient_initials ?? "",
    c.patient_age ? `${c.patient_age} y` : "",
    c.patient_sex ?? "",
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "—";
}

export function toPvCaseView(c: ApiPvCase): PvCaseView {
  const criteria = c.seriousness_flags ?? [];
  return {
    id: c.id.slice(0, 8).toUpperCase(),
    caseType: c.case_type || "AE",
    product: pvProductLabel(c.product_id),
    patient: pvPatientLabel(c),
    eventText: c.event_text || "—",
    isSerious: criteria.length > 0,
    criteria,
    status: c.status,
    deadline: c.notification_deadline,
    daysRemaining: c.days_remaining ?? 0,
    overdue: Boolean(c.overdue) || (c.days_remaining ?? 0) < 0,
    receivedAt: c.received_at,
    e2bMinimumMet: Boolean(c.e2b_minimum_met),
  };
}

function toPvPsurRow(e: ApiPvPsurEntry): PvPsurRow {
  return {
    productId: e.product_id,
    productName: e.product_name || "—",
    anchor: e.anchor,
    ageDays: e.age_days,
    dueNow: Boolean(e.due_now),
    nextWindow: e.next_window,
    nextDueDate: e.next_due_date,
    daysRemaining: e.days_remaining,
  };
}

function toPvAuditRow(e: ApiPvAuditEvent): PvAuditRow {
  return {
    id: e.id,
    eventType: e.event_type,
    severity: e.severity || "low",
    status: e.status || "—",
    detectedAt: e.detected_at,
    description: e.description || "—",
  };
}

/** The soonest window still ahead, for the overview's one-line PSUR summary. */
function nextPsurWindow(entries: ApiPvPsurEntry[]): { label: string; due: string | null } {
  const ahead = entries
    .filter((e) => e.next_due_date)
    .sort((a, b) => (a.next_due_date ?? "").localeCompare(b.next_due_date ?? ""));
  const first = ahead[0];
  return first ? { label: first.next_window, due: first.next_due_date ?? null } : { label: "—", due: null };
}

function pvCaseKpis(rows: PvCaseView[]): Kpi[] {
  const serious = rows.filter((r) => r.isSerious).length;
  const overdue = rows.filter((r) => r.overdue).length;
  return [
    {
      label: "Cases Shown",
      value: String(rows.length),
      trend: "read-only queue",
      trendUp: true,
    },
    {
      label: "Serious",
      value: String(serious),
      trend: "ICH E2A flags",
      trendUp: serious === 0,
    },
    {
      label: "Overdue",
      value: String(overdue),
      trend: "past the India clock",
      trendUp: overdue === 0,
    },
  ];
}

/** The same filter the server applies, for the fixtures in offline dev. */
function filterPvCases(rows: PvCaseView[], status: string, seriousOnly: boolean): PvCaseView[] {
  return rows.filter(
    (r) => (!status || r.status === status) && (!seriousOnly || r.isSerious),
  );
}

// ---- hooks ------------------------------------------------------------------

export function usePvDashboard(cid: string = clinicId()) {
  const q = useQuery({
    queryKey: ["pv-dashboard", cid],
    queryFn: () =>
      authFetch<ApiPvDashboard>(`/api/pv/dashboard?clinic_id=${encodeURIComponent(cid)}`),
    enabled: USE_MOCK !== "true",
    // The clock caption must stay true: the server re-measures the India
    // deadline on every read, so a 60s re-read is what keeps the countdowns
    // honest. There is no in-page timer.
    refetchInterval: 60_000,
  });
  const useFallback =
    USE_MOCK === "true" ||
    (USE_MOCK !== "false" && (q.isError || !q.data));
  if (useFallback) return mockPvDashboard;
  const d = q.data as ApiPvDashboard;
  const byType = d.cases?.by_type ?? { ae: 0, pqc: 0, mi: 0, total: 0 };
  const byStatus = d.cases?.by_status ?? {
    open: 0, overdue: 0, notified: 0, submitted: 0, closed: 0, unknown: 0, total: 0,
  };
  const kpis: Kpi[] = [
    {
      label: "Total Cases",
      value: String(byType.total),
      trend: "AE · PQC · MI recorded",
      trendUp: byType.total > 0,
    },
    {
      label: "AE Cases",
      value: String(byType.ae),
      trend: "adverse event reports",
      trendUp: byType.ae > 0,
    },
    {
      label: "PQC Complaints",
      value: String(byType.pqc),
      trend: "quality complaints",
      trendUp: byType.pqc > 0,
    },
    {
      label: "MI Inquiries",
      value: String(byType.mi),
      trend: "medical information",
      trendUp: byType.mi > 0,
    },
    {
      label: "Overdue Cases",
      value: String(byStatus.overdue),
      trend: "past the India clock",
      trendUp: byStatus.overdue === 0,
    },
  ];
  const psur = d.psur ?? { schedule: "", anchor_field: "created_at", products: 0, due_now: 0, entries: [] };
  const next = nextPsurWindow(psur.entries ?? []);
  return {
    generatedAt: d.generated_at,
    kpis,
    horizonHours: d.clocks?.horizon_hours ?? 48,
    overdue: (d.clocks?.overdue ?? []).map((e) => ({
      caseId: e.case_id.slice(0, 8).toUpperCase(),
      status: e.status,
      isSerious: e.is_serious,
      deadline: e.notification_deadline,
      daysOverdue: e.days_overdue,
    })),
    upcoming: (d.clocks?.upcoming ?? []).map((e) => ({
      caseId: e.case_id.slice(0, 8).toUpperCase(),
      status: e.status,
      isSerious: e.is_serious,
      deadline: e.notification_deadline,
      daysRemaining: e.days_remaining,
      hoursRemaining: e.hours_remaining,
    })),
    pqcStages: pvBuckets(d.pqc?.by_investigation_status),
    pqcDispositions: pvBuckets(d.pqc?.by_disposition),
    psur: {
      products: psur.products,
      dueNow: psur.due_now,
      schedule: psur.schedule,
      nextWindow: next.label,
      nextDueDate: next.due,
    },
    audit: {
      windowDays: d.audit?.window_days ?? 7,
      count: d.audit?.count ?? 0,
      digest: pvBuckets(d.audit?.by_event_type),
    },
  };
}

export function usePvPsur(cid: string = clinicId()) {
  const q = useQuery({
    queryKey: ["pv-psur", cid],
    queryFn: () =>
      authFetch<ApiPvPsur>(`/api/pv/dashboard/psur?clinic_id=${encodeURIComponent(cid)}`),
    enabled: USE_MOCK !== "true",
  });
  const useFallback =
    USE_MOCK === "true" ||
    (USE_MOCK !== "false" && (q.isError || !q.data));
  if (useFallback) return mockPvPsur;
  const p = q.data as ApiPvPsur;
  return {
    schedule: p.schedule,
    anchorField: p.anchor_field,
    products: p.products,
    dueNow: p.due_now,
    entries: (p.entries ?? []).map(toPvPsurRow),
  };
}

export function usePvAudit(cid: string = clinicId(), days = 30) {
  const q = useQuery({
    queryKey: ["pv-audit", cid, days],
    queryFn: () =>
      authFetch<ApiPvAudit>(`/api/pv/audit?clinic_id=${encodeURIComponent(cid)}&days=${days}`),
    enabled: USE_MOCK !== "true",
  });
  const useFallback =
    USE_MOCK === "true" ||
    (USE_MOCK !== "false" && (q.isError || !q.data));
  if (useFallback) return mockPvAudit;
  const a = q.data as ApiPvAudit;
  return {
    windowDays: a.window_days,
    count: a.count,
    digest: pvBuckets(a.by_event_type),
    events: (a.events ?? []).map(toPvAuditRow),
  };
}

export function usePvCases(
  cid: string = clinicId(),
  status = "",
  seriousOnly = false,
) {
  const query = [
    `clinic_id=${encodeURIComponent(cid)}`,
    status ? `status=${encodeURIComponent(status)}` : "",
    seriousOnly ? "serious_only=true" : "",
  ].filter(Boolean).join("&");
  const q = useQuery({
    queryKey: ["pv-cases", cid, status, seriousOnly],
    queryFn: () => authFetch<ApiPvCases>(`/api/pv/cases?${query}`),
    enabled: USE_MOCK !== "true",
    placeholderData: () => ({ cases: [], count: 0 }),
  });
  const rows = (q.data?.cases ?? []).map(toPvCaseView);
  // An EMPTY result is an answer here, not a failure: a filter that matches
  // nothing must render an empty queue, never the unfiltered fixtures. Only a
  // transport error (or USE_MOCK=true) reaches for them — and then the same
  // filter is applied locally, so the chips stay honest offline too.
  const useFallback = USE_MOCK === "true" || (USE_MOCK !== "false" && q.isError);
  const shown = useFallback ? filterPvCases(mockPvCases, status, seriousOnly) : rows;
  return { rows: shown, kpis: pvCaseKpis(shown) };
}