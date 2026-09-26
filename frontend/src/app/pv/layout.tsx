"use client";

// src/app/pv/layout.tsx — the PVOIC shell (PV / Medical Information Call
// Centre), phase-2.5 per spec-micc-pv-phase25.md. The THIRD shell, alongside
// (clinic) and admin, with the same three parts: the identity guard, the
// sidebar and the header. PVOIC_NAV is a third array in components/nav.ts —
// the pinned clinic (7) and admin (9) arrays are untouched, and a `(pv)` route
// group would have resolved to bare /... paths that collide with them.
//
// The identity is hardcoded like the other two shells: a membership picker is
// a follow-up slice. Every page under here is READ-ONLY — case intake stays
// API/voice-only and the E2B export route is service-token guarded, so there is
// no write action to expose yet.
import { Sidebar } from "@/components/sidebar";
import { Header } from "@/components/header";
import { PVOIC_NAV } from "@/components/nav";
import { RequireAuth } from "@/lib/auth";

const PVOIC_USER = {
  name: "PVOIC Officer",
  org: "MediCall PV & Medical Information",
  initials: "PV",
};

export default function PvLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth mode={process.env.NEXT_PUBLIC_USE_MOCK ?? "auto"}>
      <div className="min-h-screen bg-background">
        <Sidebar brand="MediCall PVOIC" brandHref="/pv" nav={PVOIC_NAV} user={PVOIC_USER} />
        <main className="lg:ml-64 min-h-screen">
          <Header label="Pharmacovigilance & Medical Information" user={PVOIC_USER} />
          <div className="p-6 lg:p-8">{children}</div>
        </main>
      </div>
    </RequireAuth>
  );
}
