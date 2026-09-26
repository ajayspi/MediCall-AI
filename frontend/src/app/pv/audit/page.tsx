"use client";

// src/app/pv/audit/page.tsx — the PV audit trail, off GET /api/pv/audit
// (phase-2.5, spec-micc-pv-phase25.md). Append-only and read-only: the point
// of this view is that a PVOIC cannot edit what the system recorded, so there
// is deliberately no action column and no filter that changes the underlying
// events — only the window that is asked for.
//
// severity is the recorder's own verdict on the event, mapped onto the
// triage badge tones the rest of the product already uses. The description
// is the raw server string (it carries the field values that made the event
// significant) and is shown verbatim, not summarised.
import { Badge, type BadgeTone } from "@/components/badge";
import { Card } from "@/components/card";
import { StatCard } from "@/components/stat-card";
import { formatRelativeDate, pvLabel, usePvAudit } from "@/lib/api";

const SEVERITY_TONE: Record<string, BadgeTone> = {
  low: "green",
  medium: "amber",
  high: "critical",
};

function Bar({ buckets }: { buckets: { label: string; count: number }[] }) {
  const max = Math.max(1, ...buckets.map((b) => b.count));
  return (
    <div className="space-y-4">
      {buckets.map((b) => (
        <div key={b.label}>
          <div className="flex items-center justify-between text-sm mb-1.5">
            <span className="text-slate-300">{pvLabel(b.label)}</span>
            <span className="text-slate-500">{b.count}</span>
          </div>
          <div className="h-2.5 rounded-full bg-white/5 overflow-hidden">
            <div
              className="h-full rounded-full bg-green-500"
              style={{ width: `${(b.count / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function PvAuditPage() {
  const { windowDays, count, digest, events } = usePvAudit();

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">PV Audit Trail</h1>
        <p className="text-slate-400 mt-1">
          Every recorded pharmacovigilance event, append-only — live from
          /api/pv/audit.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
        <StatCard
          label="Events in Window"
          value={String(count)}
          trend={`last ${windowDays} days`}
          trendUp
        />
        <StatCard
          label="Event Types"
          value={String(digest.length)}
          trend="distinct recorder actions"
          trendUp
        />
        <StatCard
          label="High Severity"
          value={String(events.filter((e) => e.severity === "high").length)}
          trend="serious or batch-affecting"
          trendUp={events.every((e) => e.severity !== "high")}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card title="By Event Type" subtitle={`Counts across the last ${windowDays} days`}>
          {digest.length === 0 ? (
            <p className="text-sm text-slate-400">No events recorded in this window.</p>
          ) : (
            <Bar buckets={digest} />
          )}
        </Card>

        <div className="lg:col-span-2">
          <Card
            title="Recorded Events"
            subtitle={`${events.length} event${events.length === 1 ? "" : "s"} · read-only, nothing here can be edited`}
          >
            {events.length === 0 ? (
              <p className="text-sm text-slate-400">
                No event was recorded in the last {windowDays} days.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="text-left text-sm text-slate-500 border-b border-white/10">
                      <th className="pb-3 font-medium">Event</th>
                      <th className="pb-3 font-medium">Type</th>
                      <th className="pb-3 font-medium">Severity</th>
                      <th className="pb-3 font-medium">Detected</th>
                      <th className="pb-3 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    {events.map((e) => (
                      <tr key={e.id} className="hover:bg-white/[0.02] align-top">
                        <td className="py-4 max-w-md">
                          <span className="text-sm font-bold text-white">{e.id}</span>
                          <p className="text-xs text-slate-400 mt-1">{e.description}</p>
                        </td>
                        <td className="py-4 text-sm text-slate-300">{pvLabel(e.eventType)}</td>
                        <td className="py-4">
                          <Badge tone={SEVERITY_TONE[e.severity] ?? "neutral"}>
                            {pvLabel(e.severity)}
                          </Badge>
                        </td>
                        <td className="py-4 text-sm text-slate-400">
                          {formatRelativeDate(e.detectedAt)}
                        </td>
                        <td className="py-4">
                          <Badge tone="neutral">{pvLabel(e.status)}</Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
