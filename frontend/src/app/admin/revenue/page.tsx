import { Badge } from "@/components/badge";
import { Card } from "@/components/card";
import { StatCard } from "@/components/stat-card";
import { gateways, invoices, revenueKpis } from "@/components/mock";

const GATEWAY_TONE: Record<string, "green" | "amber"> = {
  healthy: "green",
  degraded: "amber",
};

const INVOICE_TONE: Record<string, "green" | "amber"> = {
  Paid: "green",
  Pending: "amber",
};

export default function RevenuePage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">Revenue</h1>
        <p className="text-slate-400 mt-1">Payments via Razorpay · PhonePe · Cashfree.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {revenueKpis.map((k) => (
          <StatCard key={k.label} {...k} />
        ))}
      </div>

      <Card title="Payment Gateways" subtitle="Live collection status">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {gateways.map((g) => (
            <div key={g.name} className="rounded-2xl bg-white/[0.03] border border-white/5 p-5">
              <div className="flex items-center justify-between mb-3">
                <span className="font-bold text-white">{g.name}</span>
                <Badge tone={GATEWAY_TONE[g.status] ?? "neutral"}>{g.status}</Badge>
              </div>
              <p className="text-2xl font-black text-white">{g.txns}</p>
              <p className="text-sm text-slate-500">txns today · {g.share} share</p>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Invoices" subtitle="Clinic billing, newest first">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left text-sm text-slate-500 border-b border-white/10">
                <th className="pb-3 font-medium">Invoice</th>
                <th className="pb-3 font-medium">Clinic</th>
                <th className="pb-3 font-medium">Amount</th>
                <th className="pb-3 font-medium">Gateway</th>
                <th className="pb-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {invoices.map((inv) => (
                <tr key={inv.id} className="hover:bg-white/[0.02]">
                  <td className="py-4 font-mono text-sm text-slate-400">{inv.id}</td>
                  <td className="py-4 text-sm text-white">{inv.clinic}</td>
                  <td className="py-4 text-sm font-medium">{inv.amount}</td>
                  <td className="py-4 text-sm text-slate-400">{inv.gateway}</td>
                  <td className="py-4">
                    <Badge tone={INVOICE_TONE[inv.status] ?? "neutral"}>{inv.status}</Badge>
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