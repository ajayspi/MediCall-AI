// Single source of truth for dashboard navigation — tested by
// tests/test_dashboards.py: exactly 7 clinic tabs (D1, Settings lives in the
// header, not here) and exactly 9 admin views. Icon = SVG path data consumed
// by Sidebar. Do not inline nav arrays in layouts.
export type NavItem = { href: string; label: string; icon: string };

export const CLINIC_NAV: NavItem[] = [
  { href: "/dashboard", label: "Overview", icon: "M4 6h16M4 12h16M4 18h7" },
  { href: "/live-calls", label: "Live Calls", icon: "M17.657 18.657A8 8 0 016.343 7.343S7 9 9 10c0-2 .5-5 2.986-7C14 5 16.09 5.777 17.656 7.303A7.975 7.975 0 0112 21c-2.5 0-4.847-.675-7-1.984z" },
  { href: "/triage-queue", label: "Triage Queue", icon: "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" },
  { href: "/appointments", label: "Appointments", icon: "M8 7V3m8 4V3M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2zM3 11h18" },
  { href: "/prescriptions", label: "Prescriptions", icon: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" },
  { href: "/patients", label: "Patients", icon: "M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0v6v4a2 2 0 100 4h16a2 2 0 000-4v-4v-6z" },
  { href: "/analytics", label: "Analytics", icon: "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 002-2V5a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 002 2h2a2 2 0 012 2v6a2 2 0 01-2 2H8a2 2 0 01-2-2z" },
];

export const ADMIN_NAV: NavItem[] = [
  { href: "/admin", label: "Overview", icon: "M4 6h16M4 12h16M4 18h7" },
  { href: "/admin/live-monitor", label: "Live Monitor", icon: "M17.657 18.657A8 8 0 016.343 7.343S7 9 9 10c0-2 .5-5 2.986-7C14 5 16.09 5.777 17.656 7.303A7.975 7.975 0 0112 21c-2.5 0-4.847-.675-7-1.984z" },
  { href: "/admin/clinics", label: "Clinics", icon: "M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5a1 1 0 01-1 1h-1M12 12a5 5 0 10-10 0 5 5 0 0010 0z" },
  { href: "/admin/doctors", label: "Doctors", icon: "M17.657 18.657A8 8 0 016.343 7.343S7 9 9 10c0-2 .5-5 2.986-7C14 5 16.09 5.777 17.656 7.303A7.975 7.975 0 0112 21c-2.5 0-4.847-.675-7-1.984z" },
  { href: "/admin/patients", label: "Patients", icon: "M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0v6v4a2 2 0 100 4h16a2 2 0 000-4v-4v-6z" },
  { href: "/admin/revenue", label: "Revenue", icon: "M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.105 0 2-.895 2-2 0-.5-.17-.96-.485-1.374a4.001 4.001 0 00-.91-1.892 4 4 0 00-1.553-.72m1.98 12.158c.316.3.6.583.882.85.223.265.477.486.749.67a10.319 10.319 0 003.176 1.47c.669.176 1.342.194 2.007.06a4.26 4.26 0 001.826-2.55 4.431 4.431 0 00-.474-2.31c-.136-.304-.256-.605-.357-.895M12 3v2.25M12 16.5V21" },
  { href: "/admin/billing", label: "Billing", icon: "M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" },
  { href: "/admin/infrastructure", label: "Infrastructure", icon: "M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065zM15 12a3 3 0 11-6 0 3 3 0 016 0z" },
  { href: "/admin/audit", label: "Audit", icon: "M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-5.618 3.032m5.618 7.968A11.955 11.955 0 0112 19.056a11.955 11.955 0 01-5.618-3.032m0-10.064a11.955 11.955 0 015.618 3.032M12 12a5 5 0 01-4.477 4.91" },
];