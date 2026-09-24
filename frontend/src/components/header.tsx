"use client";

import Link from "next/link";
import type { SidebarUser } from "./sidebar";

export function Header({
  label,
  settingsHref,
  user,
}: {
  label: string;
  settingsHref?: string;
  user: SidebarUser;
}) {
  return (
    <header className="sticky top-0 z-30 flex items-center justify-between h-16 px-6 lg:px-8 border-b border-white/10 bg-background/80 backdrop-blur-md">
      <div>
        <p className="text-sm font-semibold text-slate-300">{label}</p>
      </div>

      <div className="flex items-center gap-3">
        {/* Settings lives in the header for the clinic shell (D1) */}
        {settingsHref && (
          <Link
            href={settingsHref}
            className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-white/5"
            aria-label="Settings"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
              />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </Link>
        )}

        {/* User chip */}
        <div className="flex items-center gap-3 px-3 py-2 rounded-2xl bg-white/5">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary-500 to-primary-700 flex items-center justify-center text-white text-sm font-bold">
            {user.initials}
          </div>
          <div className="hidden sm:block min-w-0">
            <p className="text-sm font-medium text-white truncate">{user.name}</p>
            <p className="text-xs text-slate-500 truncate">{user.org}</p>
          </div>
        </div>
      </div>
    </header>
  );
}