import { Badge } from "@/components/badge";
import { infrastructure } from "@/components/mock";

const STATUS_TONE: Record<string, "green" | "amber"> = {
  up: "green",
  degraded: "amber",
};

export default function InfrastructurePage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">Infrastructure</h1>
        <p className="text-slate-400 mt-1">
          Providers behind the call pipeline — Exotel/Knowlarity/Twilio fallback chain, LiveKit,
          Deepgram, ElevenLabs, OpenAI, PostgreSQL, Redis.
        </p>
        <p className="text-xs text-slate-600 mt-2">no backend entity yet — rendered from static fixtures until health checks are wired (G6-Q11).</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        {infrastructure.map((s) => (
          <div key={s.name} className="card p-6">
            <div className="flex items-center justify-between mb-4">
              <span className="font-bold text-white">{s.name}</span>
              <Badge tone={STATUS_TONE[s.status] ?? "neutral"}>{s.status}</Badge>
            </div>
            <p className="text-sm text-slate-500 mb-1">{s.role}</p>
            <p className="text-sm text-slate-300 mb-3">{s.note}</p>
            <p className="font-mono text-xs text-slate-500">latency {s.latency}</p>
          </div>
        ))}
      </div>
    </div>
  );
}