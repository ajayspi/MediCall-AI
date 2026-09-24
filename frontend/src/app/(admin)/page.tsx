import { Badge } from "@/components/badge";
import { Card } from "@/components/card";
import { StatCard } from "@/components/stat-card";
import { adminKpis, platformClinics } from "@/components/mock";

const STATUS_TONE: Record<string, "green" | "amber" | "neutral"> = {
  Active: "green",
  Trial: "amber",
  Paused: "neutral",
};

export default function AdminOverviewPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">Platform Overview</h1>
        <p className="text-slate-400 mt-1">All clinics, one view — powered by the voice pipeline.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {adminKpis.map((k) => (
          <StatCard key={k.label} {...k} />
        ))}
      </div>

      <Card title="Clinics" subtitle="Plan, status and call volume (month to date)">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left text-sm text-slate-500 border-b border-white/10">
                <th className="pb-3 font-medium">Clinic</th>
                <th className="pb-3 font-medium">City</th>
                <th className="pb-3 font-medium">Plan</th>
                <th className="pb-3 font-medium">Status</th>
                <th className="pb-3 font-medium">Calls MTD</th>
                <th className="pb-3 font-medium">Seats</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {platformClinics.map((c) => (
                <tr key={c.name} className="hover:bg-white/[0.02]">
                  <td className="py-4 text-sm font-medium text-white">{c.name}</td>
                  <td className="py-4 text-sm text-slate-400">{c.city}</td>
                  <td className="py-4 text-sm">{c.plan}</td>
                  <td className="py-4">
                    <Badge tone={STATUS_TONE[c.status] ?? "neutral"}>{c.status}</Badge>
                  </td>
                  <td className="py-4 text-sm text-slate-300">{c.callsMtd.toLocaleString()}</td>
                  <td className="py-4 text-sm text-slate-400">{c.seats}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}