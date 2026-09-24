import { LanguageBadge } from "@/components/language-badge";
import { Card } from "@/components/card";
import { StatCard } from "@/components/stat-card";
import { platformPatients } from "@/components/mock";

const patientsKpis = [
  { label: "Patients (cross-clinic)", value: "18,420", trend: "+412 this week", trendUp: true },
  { label: "Active This Week", value: "2,310", trend: "unique callers", trendUp: true },
  { label: "Languages Served", value: "5", trend: "hi · en · ta · te · bn", trendUp: true },
];

export default function PlatformPatientsPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">Patients</h1>
        <p className="text-slate-400 mt-1">De-duplicated across every clinic on the platform.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {patientsKpis.map((k) => (
          <StatCard key={k.label} {...k} />
        ))}
      </div>

      <Card title="Recent Activity" subtitle="Last engagement per patient">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left text-sm text-slate-500 border-b border-white/10">
                <th className="pb-3 font-medium">Patient</th>
                <th className="pb-3 font-medium">Phone</th>
                <th className="pb-3 font-medium">Clinic</th>
                <th className="pb-3 font-medium">Language</th>
                <th className="pb-3 font-medium">Last Activity</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {platformPatients.map((p) => (
                <tr key={p.phone} className="hover:bg-white/[0.02]">
                  <td className="py-4 text-sm font-medium text-white">{p.name}</td>
                  <td className="py-4 font-mono text-sm text-slate-400">{p.phone}</td>
                  <td className="py-4 text-sm text-slate-400">{p.clinic}</td>
                  <td className="py-4">
                    <LanguageBadge lang={p.language} />
                  </td>
                  <td className="py-4 text-sm text-slate-400">{p.lastActivity}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}