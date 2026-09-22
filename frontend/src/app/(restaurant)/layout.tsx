"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/dashboard", label: "Overview", icon: "M4 6h16M4 12h16M4 18h7" },
  { href: "/live-calls", label: "Live Calls", icon: "M17.657 18.657A8 8 0 016.343 7.343S7 9 9 10c0-2 .5-5 2.986-7C14 5 16.09 5.777 17.656 7.303A7.975 7.975 0 0112 21c-2.5 0-4.847-.675-7-1.984z" },
  { href: "/orders", label: "Orders", icon: "M16 11V7a4 4 0 11-8 0v4m0 0l-3 3m4-4l3 3m-3.5-3.5L6.75 14.25M18 11l-3 3m4-4l3 3m-3.5-3.5l-3.25 3.25" },
  { href: "/menu", label: "Menu", icon: "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" },
  { href: "/analytics", label: "Analytics", icon: "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 002-2V5a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 002 2h2a2 2 0 002-2V5a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 002 2h2a2 2 0 012 2v6a2 2 0 01-2 2H8a2 2 0 01-2-2z" },
  { href: "/billing", label: "Billing", icon: "M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" },
  { href: "/settings", label: "Settings", icon: "M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z" },
];

export default function RestaurantLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen bg-[#0f172a]">
      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 bg-black/50 lg:hidden" onClick={() => setSidebarOpen(false)} />
      )}

      {/* Sidebar */}
      <aside className={`fixed lg:static inset-y-0 left-0 z-50 w-64 bg-slate-900/90 backdrop-blur border-r border-white/10 transform transition-transform duration-300 lg:translate-x-0 ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="flex items-center justify-between h-16 px-6 border-b border-white/10">
            <Link href="/dashboard" className="flex items-center gap-2">
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
              <span className="text-xl font-bold text-white">TalkByte</span>
            </Link>
            <button className="lg:hidden p-2" onClick={() => setSidebarOpen(false)}>
              <svg className="w-6 h-6 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
            {TABS.map((tab) => (
              <Link
                key={tab.href}
                href={tab.href}
                className={`flex items-center gap-3 px-4 py-3 rounded-2xl transition-all ${
                  pathname === tab.href
                    ? 'bg-gradient-to-r from-primary-500/20 to-purple-500/20 text-white ring-1 ring-primary-500/30'
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

          {/* User section */}
          <div className="p-4 border-t border-white/10">
            <div className="flex items-center gap-3 px-4 py-3 rounded-2xl bg-white/5">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary-500 to-purple-500 flex items-center justify-center text-white text-sm font-bold">
                RJ
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-white truncate">Restaurant Owner</p>
                <p className="text-xs text-slate-500 truncate">Mama's Pizzeria</p>
              </div>
            </div>
          </div>
        </div>
      </aside>

      {/* Mobile menu button */}
      <button className="lg:hidden fixed bottom-6 right-6 z-50 p-3 rounded-full bg-gradient-to-r from-primary-500 to-purple-600 text-white shadow-xl shadow-primary-500/20" onClick={() => setSidebarOpen(true)}>
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h7" />
        </svg>
      </button>

      {/* Main content */}
      <main className="lg:ml-64 min-h-screen">
        <div className="p-6 lg:p-8">
          {children}
        </div>
      </main>
    </div>
  );
}