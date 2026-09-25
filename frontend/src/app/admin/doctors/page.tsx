import { Badge } from "@/components/badge";
import { Card } from "@/components/card";
import { StatCard } from "@/components/stat-card";
import { doctorList } from "@/components/mock";

const STATUS_TONE: Record<string, "green" | "amber"> = {
  Active: "green",
  "On leave": "amber",
};

const doctorsKpis = [
  { label: "Doctors Onboarded", value: "42", trend: "across 8 clinics", trendUp: true },
  { label: "On Leave Today", value: "3", trend: "calls reroute to peers", trendUp: true },
  { label: "Avg Consult Voice-scheduled", value: "11/day", trend: "per doctor", trendUp: true },
];

export default function DoctorsPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">Doctors</h1>
        <p className="text-slate-400 mt-1">Clinicians reachable through the voice pipeline.</p>
        <p className="text-xs text-slate-600 mt-2">no backend entity yet — rendered from static fixtures until the doctor registry ships (G6-Q11).</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {doctorsKpis.map((k) => (
          <StatCard key={k.label} {...k} />
        ))}
      </div>

      <Card
        title="Doctor Directory"
        action={
          <button className="text-sm font-semibold text-primary-400 hover:text-primary-300 transition-colors">
            + Add Doctor
          </button>
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left text-sm text-slate-500 border-b border-white/10">
                <th className="pb-3 font-medium">Doctor</th>
                <th className="pb-3 font-medium">Specialty</th>
                <th className="pb-3 font-medium">Clinic</th>
                <th className="pb-3 font-medium">Languages</th>
                <th className="pb-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {doctorList.map((d) => (
                <tr key={d.name} className="hover:bg-white/[0.02]">
                  <td className="py-4 text-sm font-medium text-white">{d.name}</td>
                  <td className="py-4 text-sm text-slate-300">{d.specialty}</td>
                  <td className="py-4 text-sm text-slate-400">{d.clinic}</td>
                  <td className="py-4 text-sm text-slate-400">{d.languages}</td>
                  <td className="py-4">
                    <Badge tone={STATUS_TONE[d.status] ?? "neutral"}>{d.status}</Badge>
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