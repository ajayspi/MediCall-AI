import { Card } from "@/components/card";
import { StatCard } from "@/components/stat-card";
import { analyticsKpis, hourlyCalls, languageMix, severityMix } from "@/components/mock";

export default function AnalyticsPage() {
  const maxHourly = Math.max(...hourlyCalls);
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">Analytics</h1>
        <p className="text-slate-400 mt-1">Volume, language and severity trends — mock until the routes phase.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {analyticsKpis.map((k) => (
          <StatCard key={k.label} {...k} />
        ))}
      </div>

      <Card title="Call Volume by Hour" subtitle="Today (deterministic mock series)">
        <div className="h-56 flex items-end justify-between gap-1 px-2">
          {hourlyCalls.map((v, i) => (
            <div key={i} className="flex-1 flex flex-col items-center gap-1">
              <div
                className={`w-full rounded-t ${i >= 9 && i <= 13 || i >= 17 && i <= 20 ? "bg-gradient-to-t from-primary-600 to-primary-400" : "bg-slate-700/50"}`}
                style={{ height: `${Math.max(4, (v / maxHourly) * 170)}px` }}
              />
              <span className="text-[10px] text-slate-500">{i % 3 === 0 ? `${i}:00` : ""}</span>
            </div>
          ))}
        </div>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Language Mix" subtitle="hi / en / ta / te / bn">
          <div className="space-y-4">
            {languageMix.map((l) => (
              <div key={l.lang}>
                <div className="flex items-center justify-between text-sm mb-1.5">
                  <span className="text-slate-300">{l.label}</span>
                  <span className="text-slate-500">{l.pct}%</span>
                </div>
                <div className="h-2.5 rounded-full bg-white/5 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-primary-500 to-primary-400"
                    style={{ width: `${l.pct}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Severity Mix" subtitle="Triage outcomes">
          <div className="space-y-4">
            {severityMix.map((s) => (
              <div key={s.severity}>
                <div className="flex items-center justify-between text-sm mb-1.5">
                  <span className="text-slate-300">{s.label}</span>
                  <span className="text-slate-500">{s.pct}%</span>
                </div>
                <div className="h-2.5 rounded-full bg-white/5 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${
                      s.severity === "green"
                        ? "bg-green-500"
                        : s.severity === "amber"
                          ? "bg-yellow-500"
                          : "bg-red-500"
                    }`}
                    style={{ width: `${s.pct}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}