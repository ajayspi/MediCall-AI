import { Card } from "@/components/card";
import { StatCard } from "@/components/stat-card";
import { LanguageBadge } from "@/components/language-badge";
import { SeverityBadge } from "@/components/severity-badge";
import { triageQueue } from "@/components/mock";

const TriageKpis = [
  { label: "Waiting", value: "6", trend: "2 above comfort target", trendUp: false },
  { label: "Avg Wait", value: "3:12", trend: "down 18% this week", trendUp: true },
  { label: "Escalated Today", value: "2", trend: "both handled", trendUp: true },
  { label: "Longest Wait", value: "9:40", trend: "red — prioritize", trendUp: false },
];

export default function TriageQueuePage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">Triage Queue</h1>
        <p className="text-slate-400 mt-1">Callers awaiting clinician attention, ranked by severity.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {TriageKpis.map((k) => (
          <StatCard key={k.label} {...k} />
        ))}
      </div>

      <Card title="Queue" subtitle="Newest calls first">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left text-sm text-slate-500 border-b border-white/10">
                <th className="pb-3 font-medium">Call</th>
                <th className="pb-3 font-medium">Caller</th>
                <th className="pb-3 font-medium">Language</th>
                <th className="pb-3 font-medium">Complaint</th>
                <th className="pb-3 font-medium">Severity</th>
                <th className="pb-3 font-medium">Waiting</th>
                <th className="pb-3 font-medium">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {triageQueue.map((t) => (
                <tr key={t.id} className="hover:bg-white/[0.02]">
                  <td className="py-4 font-mono text-sm text-slate-400">{t.id}</td>
                  <td className="py-4 text-sm">{t.caller}</td>
                  <td className="py-4">
                    <LanguageBadge lang={t.language} />
                  </td>
                  <td className="py-4 text-sm text-slate-300 max-w-xs truncate">{t.complaint}</td>
                  <td className="py-4">
                    <SeverityBadge severity={t.severity} />
                  </td>
                  <td className="py-4 text-sm text-slate-400">{t.waiting}</td>
                  <td className="py-4">
                    <button className="text-xs font-semibold text-primary-400 hover:text-primary-300 transition-colors">
                      Assign →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}