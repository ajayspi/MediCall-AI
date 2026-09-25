"use client";

import { Badge } from "@/components/badge";
import { Card } from "@/components/card";
import { StatCard } from "@/components/stat-card";
import { usePrescriptions } from "@/lib/api";

const STATUS_TONE: Record<string, "green" | "amber" | "blue" | "neutral"> = {
  Active: "green",
  Renewal: "amber",
  Pending: "blue",
  Expired: "neutral",
  "Sent Pharmacy": "amber",
  Dispensed: "green",
};

export default function PrescriptionsPage() {
  const { rows, kpis } = usePrescriptions();
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">Prescriptions</h1>
        <p className="text-slate-400 mt-1">Issued by voice, refill requests queued for clinician review.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {kpis.map((k) => (
          <StatCard key={k.label} {...k} />
        ))}
      </div>

      <Card title="Recent Prescriptions" subtitle="Transcript-only phase — meds captured from the call">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left text-sm text-slate-500 border-b border-white/10">
                <th className="pb-3 font-medium">Patient</th>
                <th className="pb-3 font-medium">Medicine</th>
                <th className="pb-3 font-medium">Dosage</th>
                <th className="pb-3 font-medium">Frequency</th>
                <th className="pb-3 font-medium">Doctor</th>
                <th className="pb-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {rows.map((p) => (
                <tr key={p.patient + p.medicine} className="hover:bg-white/[0.02]">
                  <td className="py-4 text-sm font-medium text-white">{p.patient}</td>
                  <td className="py-4 text-sm font-mono text-slate-300">{p.medicine}</td>
                  <td className="py-4 text-sm text-slate-400">{p.dosage}</td>
                  <td className="py-4 text-sm text-slate-400">{p.frequency}</td>
                  <td className="py-4 text-sm">{p.doctor}</td>
                  <td className="py-4">
                    <Badge tone={STATUS_TONE[p.status] ?? "neutral"}>{p.status}</Badge>
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