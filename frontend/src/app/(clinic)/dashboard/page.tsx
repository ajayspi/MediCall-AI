"use client";

import Link from "next/link";
import { Card } from "@/components/card";
import { StatCard } from "@/components/stat-card";
import { LanguageBadge } from "@/components/language-badge";
import { SeverityBadge } from "@/components/severity-badge";
import { CallStateBadge } from "@/components/call-state-badge";
import { useTodayCalls } from "@/lib/api";

export default function ClinicOverviewPage() {
  const { calls: todayCalls, kpis: clinicKpis } = useTodayCalls();
  return (
    <div className="space-y-8">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white">Dashboard</h1>
          <p className="text-slate-400 mt-1">City Care Clinic — what&apos;s happening today.</p>
        </div>
        <Link href="/live-calls" className="btn-primary inline-block !px-6 !py-3 text-sm">
          Open Live Calls
        </Link>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {clinicKpis.map((k) => (
          <StatCard key={k.label} {...k} />
        ))}
      </div>

      <Card
        title="Today's Calls"
        subtitle="Latest activity across all states"
        action={
          <Link href="/live-calls" className="text-sm font-medium text-primary-400 hover:underline">
            View all →
          </Link>
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left text-sm text-slate-500 border-b border-white/10">
                <th className="pb-3 font-medium">Call</th>
                <th className="pb-3 font-medium">Caller</th>
                <th className="pb-3 font-medium">Language</th>
                <th className="pb-3 font-medium">State</th>
                <th className="pb-3 font-medium">Severity</th>
                <th className="pb-3 font-medium">Duration</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {todayCalls.map((c) => (
                <tr key={c.id} className="hover:bg-white/[0.02]">
                  <td className="py-4 font-mono text-sm text-slate-400">{c.id}</td>
                  <td className="py-4 text-sm">{c.caller}</td>
                  <td className="py-4">
                    <LanguageBadge lang={c.language} />
                  </td>
                  <td className="py-4">
                    <CallStateBadge state={c.state} />
                  </td>
                  <td className="py-4">
                    <SeverityBadge severity={c.severity} />
                  </td>
                  <td className="py-4 text-sm text-slate-400">{c.duration}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Triage Mix" subtitle="Severity distribution of today's calls">
        <div className="grid grid-cols-4 gap-4">
          {[
            { sev: "green", label: "Green", pct: 64 },
            { sev: "amber", label: "Amber", pct: 28 },
            { sev: "red", label: "Red", pct: 6 },
            { sev: "critical", label: "Critical", pct: 2 },
          ].map((s) => (
            <div key={s.sev} className="rounded-2xl bg-white/[0.03] p-4 border border-white/5">
              <SeverityBadge severity={s.sev} />
              <p className="text-2xl font-black text-white mt-3">{s.pct}%</p>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}