import { Badge } from "@/components/badge";
import { Card } from "@/components/card";
import { StatCard } from "@/components/stat-card";
import { appointmentKpis, appointments } from "@/components/mock";

const STATUS_TONE: Record<string, "green" | "amber" | "blue" | "neutral"> = {
  Confirmed: "green",
  Pending: "amber",
  Completed: "blue",
  "No-show": "neutral",
};

export default function AppointmentsPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">Appointments</h1>
        <p className="text-slate-400 mt-1">Booked by the AI agent during calls, shown for today.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {appointmentKpis.map((k) => (
          <StatCard key={k.label} {...k} />
        ))}
      </div>

      <Card title="Today's Schedule" subtitle="09:30 – 17:00">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left text-sm text-slate-500 border-b border-white/10">
                <th className="pb-3 font-medium">Time</th>
                <th className="pb-3 font-medium">Patient</th>
                <th className="pb-3 font-medium">Doctor</th>
                <th className="pb-3 font-medium">Reason</th>
                <th className="pb-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {appointments.map((a) => (
                <tr key={a.time + a.patient} className="hover:bg-white/[0.02]">
                  <td className="py-4 font-mono text-sm text-slate-400">{a.time}</td>
                  <td className="py-4 text-sm font-medium text-white">{a.patient}</td>
                  <td className="py-4 text-sm">{a.doctor}</td>
                  <td className="py-4 text-sm text-slate-300">{a.reason}</td>
                  <td className="py-4">
                    <Badge tone={STATUS_TONE[a.status] ?? "neutral"}>{a.status}</Badge>
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