import { Card } from "@/components/card";
import { StatCard } from "@/components/stat-card";
import { LanguageBadge } from "@/components/language-badge";
import { SeverityBadge } from "@/components/severity-badge";
import { CallStateBadge } from "@/components/call-state-badge";
import { liveCallKpis, todayCalls, type MockCall } from "@/components/mock";

function LivePulseIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
    </svg>
  );
}

export default function LiveCallsPage() {
  const active = todayCalls.filter((c) => !["COMPLETE", "DROPPED", "PAYMENT_EXPIRED"].includes(c.state));

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">Live Calls</h1>
        <p className="text-slate-400 mt-1">Conversations in progress, spoken by the AI voice agent.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {liveCallKpis.map((k) => (
          <StatCard key={k.label} {...k} icon={<LivePulseIcon />} />
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
        {(active.length ? active : todayCalls.slice(0, 3)).map((c: MockCall) => (
          <div key={c.id} className="card p-6">
            <div className="flex items-center justify-between mb-4">
              <span className="font-mono text-sm text-slate-400">{c.id}</span>
              <span className="flex items-center gap-1.5 text-xs text-green-400 font-medium">
                <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" /> LIVE
              </span>
            </div>
            <p className="text-lg font-bold text-white mb-1">{c.caller}</p>
            <p className="text-sm text-slate-400 mb-4 truncate">{c.complaint}</p>
            <div className="flex flex-wrap gap-2">
              <LanguageBadge lang={c.language} />
              <CallStateBadge state={c.state} />
              <SeverityBadge severity={c.severity} />
            </div>
            <div className="mt-4 pt-4 border-t border-white/5 text-sm text-slate-400">
              Started <span className="text-slate-300 font-medium">{c.startedAt}</span> · {c.duration}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}