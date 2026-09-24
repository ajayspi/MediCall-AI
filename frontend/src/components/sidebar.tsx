"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { NavItem } from "./nav";

export function MediCallLogo({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      {/* Medical cross */}
      <rect x="42" y="14" width="16" height="42" rx="6" fill="#14b8a6" />
      <rect x="29" y="29" width="42" height="16" rx="6" fill="#2dd4bf" />
      {/* Voice waves */}
      <path d="M 22 34 Q 13 50 22 66" stroke="#14b8a6" strokeWidth="4" fill="none" strokeLinecap="round" opacity="0.8" />
      <path d="M 78 34 Q 87 50 78 66" stroke="#14b8a6" strokeWidth="4" fill="none" strokeLinecap="round" opacity="0.8" />
    </svg>
  );
}

export type SidebarUser = { name: string; org: string; initials: string };

export function Sidebar({
  brand,
  brandHref,
  nav,
  user,
}: {
  brand: string;
  brandHref: string;
  nav: NavItem[];
  user: SidebarUser;
}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <>
      {/* Mobile overlay */}
      {open && (
        <div className="fixed inset-0 z-40 bg-black/50 lg:hidden" onClick={() => setOpen(false)} />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed lg:static inset-y-0 left-0 z-50 w-64 bg-slate-900/90 backdrop-blur border-r border-white/10 transform transition-transform duration-300 lg:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="flex items-center justify-between h-16 px-6 border-b border-white/10">
            <Link href={brandHref} className="flex items-center gap-2">
              <MediCallLogo />
              <span className="text-xl font-bold text-white">{brand}</span>
            </Link>
            <button className="lg:hidden p-2" onClick={() => setOpen(false)} aria-label="Close menu">
              <svg className="w-6 h-6 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
            {nav.map((tab) => (
              <Link
                key={tab.href}
                href={tab.href}
                className={`flex items-center gap-3 px-4 py-3 rounded-2xl transition-all ${
                  pathname === tab.href
                    ? "bg-gradient-to-r from-primary-500/20 to-primary-700/20 text-white ring-1 ring-primary-500/30"
                    : "text-slate-400 hover:text-white hover:bg-white/5"
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
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary-500 to-primary-700 flex items-center justify-center text-white text-sm font-bold">
                {user.initials}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-white truncate">{user.name}</p>
                <p className="text-xs text-slate-500 truncate">{user.org}</p>
              </div>
            </div>
          </div>
        </div>
      </aside>

      {/* Mobile menu button */}
      <button
        className="lg:hidden fixed bottom-6 right-6 z-50 p-3 rounded-full bg-gradient-to-r from-primary-500 to-primary-600 text-white shadow-xl shadow-primary-500/20"
        onClick={() => setOpen(true)}
        aria-label="Open menu"
      >
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h7" />
        </svg>
      </button>
    </>
  );
}