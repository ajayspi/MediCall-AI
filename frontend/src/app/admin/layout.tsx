"use client";

import { Sidebar } from "@/components/sidebar";
import { Header } from "@/components/header";
import { ADMIN_NAV } from "@/components/nav";
import { RequireAuth } from "@/lib/auth";

const ADMIN_USER = { name: "Platform Admin", org: "MediCall AI Operations", initials: "PA" };

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth mode={process.env.NEXT_PUBLIC_USE_MOCK ?? "auto"}>
      <div className="min-h-screen bg-background">
        <Sidebar brand="MediCall Admin" brandHref="/admin" nav={ADMIN_NAV} user={ADMIN_USER} />
        <main className="lg:ml-64 min-h-screen">
          <Header label="Platform Console" user={ADMIN_USER} />
          <div className="p-6 lg:p-8">{children}</div>
        </main>
      </div>
    </RequireAuth>
  );
}