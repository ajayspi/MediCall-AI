"use client";

import { Badge } from "@/components/badge";
import { Card } from "@/components/card";
import { StatCard } from "@/components/stat-card";
import { LanguageBadge } from "@/components/language-badge";
import { CallStateBadge } from "@/components/call-state-badge";
import { useAdminLiveCalls } from "@/lib/api";

const PROVIDERS = ["Exotel", "Knowlarity", "Twilio India"];

export default function LiveMonitorPage() {
  const { kpis, calls } = useAdminLiveCalls();
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">Live Monitor</h1>
        <p className="text-slate-400 mt-1">Every active voice room across all clinics.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {kpis.map((k) => (
          <StatCard key={k.label} {...k} />
        ))}
      </div>

      <Card title="Active Rooms" subtitle="Cross-clinic live calls">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left text-sm text-slate-500 border-b border-white/10">
                <th className="pb-3 font-medium">Call</th>
                <th className="pb-3 font-medium">Clinic</th>
                <th className="pb-3 font-medium">Language</th>
                <th className="pb-3 font-medium">State</th>
                <th className="pb-3 font-medium">Duration</th>
                <th className="pb-3 font-medium">Provider</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {calls.map((c, i) => (
                <tr key={c.id} className="hover:bg-white/[0.02]">
                  <td className="py-4 font-mono text-sm text-slate-400">{c.id}</td>
                  <td className="py-4 text-sm text-white">{c.clinicName}</td>
                  <td className="py-4">
                    <LanguageBadge lang={c.language} />
                  </td>
                  <td className="py-4">
                    <CallStateBadge state={c.state} />
                  </td>
                  <td className="py-4 text-sm text-slate-400">{c.duration}</td>
                  <td className="py-4 text-sm text-slate-400">{PROVIDERS[i % PROVIDERS.length]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}