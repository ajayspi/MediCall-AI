import { Badge } from "@/components/badge";
import { Card } from "@/components/card";
import { StatCard } from "@/components/stat-card";
import { platformClinics } from "@/components/mock";

const STATUS_TONE: Record<string, "green" | "amber" | "neutral"> = {
  Active: "green",
  Trial: "amber",
  Paused: "neutral",
};

const clinicsKpis = [
  { label: "Total Clinics", value: "8", trend: "+2 this quarter", trendUp: true },
  { label: "On Trial", value: "1", trend: "Green Valley Hospital", trendUp: false },
  { label: "Avg Calls/Clinic", value: "156/day", trend: "MTD basis", trendUp: true },
  { label: "Churn Risk", value: "1", trend: "Sunrise Polyclinic paused", trendUp: false },
];

export default function ClinicsPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">Clinics</h1>
        <p className="text-slate-400 mt-1">Onboarded clinics on the MediCall platform.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {clinicsKpis.map((k) => (
          <StatCard key={k.label} {...k} />
        ))}
      </div>

      <Card
        title="Clinic Directory"
        subtitle="Plan tier, status and seats"
        action={
          <button className="text-sm font-semibold text-primary-400 hover:text-primary-300 transition-colors">
            + Add Clinic
          </button>
        }
      >
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