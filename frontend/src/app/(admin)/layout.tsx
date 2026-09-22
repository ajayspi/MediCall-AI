"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const ADMIN_TABS = [
  { href: "/admin", label: "Overview", icon: "M4 6h16M4 12h16M4 18h7" },
  { href: "/admin/live-monitor", label: "Live Monitor", icon: "M17.657 18.657A8 8 0 016.343 7.343S7 9 9 10c0-2 .5-5 2.986-7C14 5 16.09 5.777 17.656 7.303A7.975 7.975 0 0112 21c-2.5 0-4.847-.675-7-1.984z" },
  { href: "/admin/restaurants", label: "Restaurants", icon: "M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5a1 1 0 01-1 1h-1M12 12a5 5 0 10-10 0 5 5 0 0010 0z" },
  { href: "/admin/users", label: "Users", icon: "M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0v6v4a2 2 0 100 4h16a2 2 0 000-4v-4v-6z" },
  { href: "/admin/revenue", label: "Revenue", icon: "M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.105 0 2-.895 2-2 0-.5-.17-.96-.485-1.374a4.001 4.001 0 00-.91-1.892 4 4 0 00-1.553-.72m1.98 12.158c.316.3.6.583.882.85.223.265.477.486.749.67a10.319 10.319 0 003.176 1.47c.669.176 1.342.194 2.007.06a4.26 4.26 0 001.826-2.55 4.431 4.431 0 00-.474-2.31c-.136-.304-.256-.605-.357-.895M12 3v2.25M12 16.5V21" },
  { href: "/admin/billing", label: "Billing", icon: "M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" },
  { href: "/admin/infrastructure", label: "Infrastructure", icon: "M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z" },
  { href: "/admin/audit", label: "Audit Log", icon: "M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-5.618 3.032m5.618 7.968A11.955 11.955 0 0112 19.056a11.955 11.955 0 01-5.618-3.032m0-10.064a11.955 11.955 0 015.618 3.032M12 12a5 5 0 01-4.477 4.91" },
  { href: "/admin/analytics", label: "Analytics", icon: "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 002-2V5a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 002 2h2a2 2 0 002-2V5a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h2a2 2 0 012 2v6a2 2 0 01-2 2h-2a2 2 0 01-2 2zm0 0V9a2 2 0 012-2h2a2 2 0 002-2V5a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h2a2 2 0 01-2 2h2a2 2 0 01-2 2v6a2 2 0 01-2 2H8a2 2 0 01-2-2z" },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen bg-[#0f172a]">
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 bg-black/50 lg:hidden" onClick={() => setSidebarOpen(false)} />
      )}

      <aside className={`fixed lg:static inset-y-0 left-0 z-50 w-64 bg-slate-900/90 backdrop-blur border-r border-white/10 transform transition-transform duration-300 lg:translate-x-0 ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="flex flex-col h-full">
          <div className="flex items-center justify-between h-16 px-6 border-b border-white/10">
            <Link href="/admin" className="flex items-center gap-2">
              <svg width="32" height="32" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                <defs>
                  <linearGradient id="logoGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" style={{ stopColor: "#7c3aed", stopOpacity: 1 }} />
                    <stop offset="100%" style={{ stopColor: "#14b8a6", stopOpacity: 1 }} />
                  </linearGradient>
                </defs>
                <rect x="40" y="25" width="20" height="30" rx="10" fill="url(#logoGradient)" />
                <line x1="50" y1="55" x2="50" y2="75" stroke="url(#logoGradient)" strokeWidth="3" strokeLinecap="round" />
                <line x1="35" y1="75" x2="65" y2="75" stroke="url(#logoGradient)" strokeWidth="3" strokeLinecap="round" />
                <path d="M 20 40 Q 15 50 20 60" stroke="#7c3aed" strokeWidth="2.5" fill="none" opacity="0.7" />
                <path d="M 10 35 Q 3 50 10 65" stroke="#7c3aed" strokeWidth="2" fill="none" opacity="0.5" />
                <path d="M 80 40 Q 85 50 80 60" stroke="#14b8a6" strokeWidth="2.5" fill="none" opacity="0.7" />
                <path d="M 90 35 Q 97 50 90 65" stroke="#14b8a6" strokeWidth="2" fill="none" opacity="0.5" />
              </svg>
              <span className="text-xl font-bold text-white">TalkByte Admin</span>
            </Link>
            <button className="lg:hidden p-2" onClick={() => setSidebarOpen(false)}>
              <svg className="w-6 h-6 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
            {ADMIN_TABS.map((tab) => (
              <Link
                key={tab.href}
                href={tab.href}
                className={`flex items-center gap-3 px-4 py-3 rounded-2xl transition-all ${
                  pathname === tab.href
                    ? 'bg-gradient-to-r from-purple-500/20 to-pink-500/20 text-white ring-1 ring-purple-500/30'
                    : 'text-slate-400 hover:text-white hover:bg-white/5'
                }`}
              >
                <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={tab.icon} />
                </svg>
                <span className="font-medium">{tab.label}</span>
              </Link>
            ))}
          </nav>

          <div className="p-4 border-t border-white/10">
            <div className="flex items-center gap-3 px-4 py-3 rounded-2xl bg-purple-500/10 border border-purple-500/20">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center text-white text-sm font-bold">
                OA
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-white truncate">Operator Admin</p>
                <p className="text-xs text-slate-500 truncate">Platform Operations</p>
              </div>
            </div>
          </div>
        </div>
      </aside>

      <button className="lg:hidden fixed bottom-6 right-6 z-50 p-3 rounded-full bg-gradient-to-r from-purple-500 to-pink-600 text-white shadow-xl shadow-purple-500/20" onClick={() => setSidebarOpen(true)}>
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h7" />
        </svg>
      </button>

      <main className="lg:ml-64 min-h-screen">
        <div className="p-6 lg:p-8">
          {children}
        </div>
      </main>
    </div>
  );
}