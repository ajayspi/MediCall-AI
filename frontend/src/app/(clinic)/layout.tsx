"use client";

import { Sidebar } from "@/components/sidebar";
import { Header } from "@/components/header";
import { CLINIC_NAV } from "@/components/nav";
import { RequireAuth } from "@/lib/auth";

const CLINIC_USER = { name: "Clinic Admin", org: "City Care Clinic", initials: "CA" };

export default function ClinicLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth mode={process.env.NEXT_PUBLIC_USE_MOCK ?? "auto"}>
      <div className="min-h-screen bg-background">
        <Sidebar brand="MediCall AI" brandHref="/dashboard" nav={CLINIC_NAV} user={CLINIC_USER} />
        <main className="lg:ml-64 min-h-screen">
          <Header label="Clinic Console" settingsHref="/settings" user={CLINIC_USER} />
          <div className="p-6 lg:p-8">{children}</div>
        </main>
      </div>
    </RequireAuth>
  );
}