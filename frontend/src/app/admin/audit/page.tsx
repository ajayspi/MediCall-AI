import { Card } from "@/components/card";
import { auditLog } from "@/components/mock";

export default function AuditPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">Audit</h1>
        <p className="text-slate-400 mt-1">Every privileged action, recorded.</p>
        <p className="text-xs text-slate-600 mt-2">no backend entity yet — rendered from static fixtures until the audit trail surfaces (G6-Q11).</p>
      </div>

      <Card title="Audit Log" subtitle="Newest events first">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left text-sm text-slate-500 border-b border-white/10">
                <th className="pb-3 font-medium">Time</th>
                <th className="pb-3 font-medium">Actor</th>
                <th className="pb-3 font-medium">Action</th>
                <th className="pb-3 font-medium">Target</th>
                <th className="pb-3 font-medium">Source IP</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {auditLog.map((e, i) => (
                <tr key={e.time + e.action} className="hover:bg-white/[0.02]">
                  <td className="py-4 font-mono text-sm text-slate-400">{e.time}</td>
                  <td className="py-4 text-sm font-medium text-white">{e.actor}</td>
                  <td className="py-4 text-sm text-slate-300">{e.action}</td>
                  <td className="py-4 text-sm text-slate-400">{e.target}</td>
                  <td className="py-4 font-mono text-sm text-slate-500">{e.ip}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}