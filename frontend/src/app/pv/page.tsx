"use client";

// src/app/pv/page.tsx — the PVOIC overview, off GET /api/pv/dashboard
// (phase-2.5, spec-micc-pv-phase25.md). Five numbers, the India reporting
// clock, and the three things a PVOIC has to be able to answer in one look:
// what is past the CDSCO / ICH E2B notification deadline, what is about to
// land inside the next 48 hours, and what the PQC pipeline is doing.
//
// EVERY NUMBER HERE IS THE SERVER'S. daysOverdue, daysRemaining and
// hoursRemaining come straight from the snapshot (services/pv_dashboard.py,
// keyed off the Phase-1 compute_reporting_deadline) and the snapshot is
// re-read every 60s by the hook — this page never counts down in the browser,
// because a client-side timer can disagree with the legal clock.
import { Badge } from "@/components/badge";
import { Card } from "@/components/card";
import { StatCard } from "@/components/stat-card";
import { formatRelativeDate, pvLabel, usePvDashboard } from "@/lib/api";

/** A countdown in whole hours, because hours are the unit the server measures. */
function hoursAway(hours: number): string {
  if (hours < 24) return `${hours} h`;
  const whole = Math.floor(hours);
  const rest = Math.round((hours - whole) * 10) / 10;
  return `${whole} d ${rest} h`;
}

function BucketBars({ buckets, accent }: { buckets: { label: string; count: number }[]; accent: string }) {
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
              className={`h-full rounded-full ${accent}`}
              style={{ width: `${(b.count / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function PvOverviewPage() {
  const {
    generatedAt,
    kpis,
    horizonHours,
    overdue,
    upcoming,
    pqcStages,
    pqcDispositions,
    psur,
    audit,
  } = usePvDashboard();

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">Pharmacovigilance Overview</h1>
        <p className="text-slate-400 mt-1">
          AE, PQC and MI case load against the India reporting clock — live from
          /api/pv/dashboard.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-6">
        {kpis.map((k) => (
          <StatCard key={k.label} {...k} />
        ))}
      </div>

      {/* The India clock. Server-computed, re-read every 60s — see the header. */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card
          title="Past the Notification Deadline"
          subtitle={`${overdue.length} case${overdue.length === 1 ? "" : "s"} past the ICH E2B / CDSCO clock`}
        >
          {overdue.length === 0 ? (
            <p className="text-sm text-slate-400">Nothing overdue. Every case is inside its window.</p>
          ) : (
            <div className="space-y-3">
              {overdue.map((row) => (
                <div
                  key={row.caseId}
                  className="flex items-center justify-between gap-4 rounded-2xl bg-red-500/5 border border-red-500/20 px-4 py-3"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold text-white">{row.caseId}</span>
                      {row.isSerious && <Badge tone="critical">Serious</Badge>}
                    </div>
                    <p className="text-xs text-slate-400 mt-1">
                      {pvLabel(row.status)} · due {formatRelativeDate(row.deadline)}
                    </p>
                  </div>
                  <Badge tone="red">{row.daysOverdue} d overdue</Badge>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card
          title={`Due in the Next ${horizonHours} Hours`}
          subtitle="Notifications that must go out before the horizon closes"
        >
          {upcoming.length === 0 ? (
            <p className="text-sm text-slate-400">
              Nothing falls due in the next {horizonHours} hours.
            </p>
          ) : (
            <div className="space-y-3">
              {upcoming.map((row) => (
                <div
                  key={row.caseId}
                  className="flex items-center justify-between gap-4 rounded-2xl bg-white/[0.02] border border-white/10 px-4 py-3"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold text-white">{row.caseId}</span>
                      {row.isSerious && <Badge tone="amber">Serious</Badge>}
                    </div>
                    <p className="text-xs text-slate-400 mt-1">
                      {pvLabel(row.status)} · due {formatRelativeDate(row.deadline)}
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-sm font-bold text-primary-300">
                      {hoursAway(row.hoursRemaining)} left
                    </div>
                    <div className="text-xs text-slate-500 mt-1">
                      {row.daysRemaining === 0
                        ? "today"
                        : `day ${row.daysRemaining} of the window`}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="PQC Pipeline" subtitle="Investigation stage of every quality complaint">
          <BucketBars buckets={pqcStages} accent="bg-primary-500" />
        </Card>
        <Card title="PQC Dispositions" subtitle="Where the complaints ended up">
          <BucketBars buckets={pqcDispositions} accent="bg-primary-400" />
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card
          title="PSUR Schedule"
          subtitle={psur.schedule}
          action={
            psur.dueNow > 0 ? (
              <Badge tone="amber">{psur.dueNow} window{psur.dueNow === 1 ? "" : "s"} open</Badge>
            ) : (
              <Badge tone="green">All windows closed</Badge>
            )
          }
        >
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-3xl font-black text-white">{psur.products}</p>
              <p className="text-sm text-slate-400 mt-1">products on the schedule</p>
            </div>
            <div>
              <p
                className={`text-3xl font-black ${
                  psur.dueNow > 0 ? "text-severity-amber" : "text-white"
                }`}
              >
                {psur.dueNow}
              </p>
              <p className="text-sm text-slate-400 mt-1">windows open now</p>
            </div>
          </div>
          <div className="mt-6 rounded-2xl bg-white/[0.02] border border-white/10 px-4 py-3">
            <p className="text-xs text-slate-500">Next window</p>
            <p className="text-sm font-medium text-white mt-1">
              {psur.nextWindow}
              {psur.nextDueDate ? ` · ${formatRelativeDate(psur.nextDueDate)}` : ""}
            </p>
          </div>
        </Card>

        <Card
          title="PV Audit Digest"
          subtitle={`${audit.count} event${audit.count === 1 ? "" : "s"} in the last ${audit.windowDays} days`}
        >
          {audit.digest.length === 0 ? (
            <p className="text-sm text-slate-400">No audit events recorded in this window.</p>
          ) : (
            <BucketBars buckets={audit.digest} accent="bg-green-500" />
          )}
        </Card>
      </div>

      <p className="text-xs text-slate-500">
        Updated {formatRelativeDate(generatedAt)} · snapshot re-read every 60 seconds
      </p>
    </div>
  );
}
