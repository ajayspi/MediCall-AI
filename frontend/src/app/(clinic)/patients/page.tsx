"use client";

import { LanguageBadge } from "@/components/language-badge";
import { Card } from "@/components/card";
import { StatCard } from "@/components/stat-card";
import { useRecentCallers } from "@/lib/api";

export default function PatientsPage() {
  const { rows, kpis } = useRecentCallers();
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">Patients</h1>
        <p className="text-slate-400 mt-1">Everyone who called the clinic, regardless of outcome.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {kpis.map((k) => (
          <StatCard key={k.label} {...k} />
        ))}
      </div>

      <Card title="Patient Directory" subtitle="Sorted by most recent call">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left text-sm text-slate-500 border-b border-white/10">
                <th className="pb-3 font-medium">Patient</th>
                <th className="pb-3 font-medium">Phone</th>
                <th className="pb-3 font-medium">Language</th>
                <th className="pb-3 font-medium">Last Visit</th>
                <th className="pb-3 font-medium">Calls</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {rows.map((p) => (
                <tr key={p.phone} className="hover:bg-white/[0.02]">
                  <td className="py-4 text-sm font-medium text-white">{p.name}</td>
                  <td className="py-4 font-mono text-sm text-slate-400">{p.phone}</td>
                  <td className="py-4">
                    <LanguageBadge lang={p.language} />
                  </td>
                  <td className="py-4 text-sm text-slate-400">{p.lastVisit}</td>
                  <td className="py-4 text-sm text-slate-300">{p.calls}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}