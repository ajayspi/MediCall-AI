import { Badge } from "@/components/badge";
import { Card } from "@/components/card";
import { StatCard } from "@/components/stat-card";
import { clinicBills, plans } from "@/components/mock";

const STATUS_TONE: Record<string, "green" | "amber" | "blue"> = {
  Paid: "green",
  Due: "amber",
  Trial: "blue",
};

const billingKpis = [
  { label: "MRR", value: "₹92,000", trend: "+18% quarter over quarter", trendUp: true },
  { label: "Invoices Due", value: "2", trend: "₹13,800 collectable", trendUp: false },
  { label: "Plan Attach Rate", value: "88%", trend: "self-serve signup", trendUp: true },
];

export default function BillingPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">Billing</h1>
        <p className="text-slate-400 mt-1">Plans and clinic bills in rupees.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {billingKpis.map((k) => (
          <StatCard key={k.label} {...k} />
        ))}
        {plans.map((p) => (
          <div key={p.name} className="card p-6">
            <p className="text-sm font-medium text-slate-400">{p.name}</p>
            <p className="text-2xl font-black text-white mt-1">{p.price}</p>
            <p className="text-sm text-slate-500">{p.details}</p>
          </div>
        ))}
      </div>

      <Card title="Clinic Bills" subtitle="Current billing cycle">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left text-sm text-slate-500 border-b border-white/10">
                <th className="pb-3 font-medium">Clinic</th>
                <th className="pb-3 font-medium">Plan</th>
                <th className="pb-3 font-medium">Amount</th>
                <th className="pb-3 font-medium">Cycle</th>
                <th className="pb-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {clinicBills.map((b) => (
                <tr key={b.clinic} className="hover:bg-white/[0.02]">
                  <td className="py-4 text-sm font-medium text-white">{b.clinic}</td>
                  <td className="py-4 text-sm">{b.plan}</td>
                  <td className="py-4 text-sm font-medium">{b.amount}</td>
                  <td className="py-4 text-sm text-slate-400">{b.cycle}</td>
                  <td className="py-4">
                    <Badge tone={STATUS_TONE[b.status] ?? "neutral"}>{b.status}</Badge>
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