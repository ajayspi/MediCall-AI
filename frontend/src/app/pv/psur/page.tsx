"use client";

// src/app/pv/psur/page.tsx — the PSUR schedule, off GET /api/pv/dashboard/psur
// (phase-2.5, spec-micc-pv-phase25.md). One card per product on the schedule,
// with the window the server put it in and the date that window falls due.
//
// The windows come from the Phase-1 helper psur_next_window
// (services/pv_dashboard.py): two half-yearly reports and then two annual
// ones, counted from the product's own anchor date. This page renders those
// numbers; it never recomputes a schedule, and it never counts down — a due
// date that the browser "refreshes" is not a compliance record.
import { Badge } from "@/components/badge";
import { Card } from "@/components/card";
import { StatCard } from "@/components/stat-card";
import { formatRelativeDate, usePvPsur } from "@/lib/api";

export default function PvPsurPage() {
  const { schedule, anchorField, products, dueNow, entries } = usePvPsur();

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">PSUR Schedule</h1>
        <p className="text-slate-400 mt-1">
          Periodic Safety Update Reports per product — live from
          /api/pv/dashboard/psur.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          label="Products"
          value={String(products)}
          trend={schedule}
          trendUp
        />
        <StatCard
          label="Windows Open Now"
          value={String(dueNow)}
          trend="reporting window is due"
          trendUp={dueNow === 0}
        />
        <StatCard
          label="Schedule"
          value={schedule.split(",")[0] ?? schedule}
          trend={schedule}
          trendUp
        />
        <StatCard
          label="Anchored On"
          value={anchorField.replace(/_/g, " ")}
          trend="per product, from the first record"
          trendUp
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {entries.map((e) => (
          <Card
            key={e.productId}
            title={e.productName}
            subtitle={`${e.productId} · anchored ${formatRelativeDate(e.anchor)}`}
            action={e.dueNow ? <Badge tone="amber">Window open</Badge> : <Badge tone="green">Not due</Badge>}
          >
            <div className="grid grid-cols-2 gap-4">
              <div className="rounded-2xl bg-white/[0.02] border border-white/10 px-4 py-3">
                <p className="text-xs text-slate-500">Reporting window</p>
                <p className="text-sm font-bold text-white mt-1">{e.nextWindow}</p>
              </div>
              <div className="rounded-2xl bg-white/[0.02] border border-white/10 px-4 py-3">
                <p className="text-xs text-slate-500">Due</p>
                <p className="text-sm font-bold text-white mt-1">
                  {e.nextDueDate ? formatRelativeDate(e.nextDueDate) : "No window scheduled"}
                </p>
              </div>
            </div>
            <div className="mt-4 flex items-center justify-between text-sm">
              <span className="text-slate-400">
                {e.ageDays === null ? "Age unknown" : `${e.ageDays} days since the anchor`}
              </span>
              {e.daysRemaining === null ? (
                <span className="text-xs text-slate-500">—</span>
              ) : e.dueNow ? (
                <span className="text-xs text-slate-400">{e.daysRemaining} d into the window</span>
              ) : (
                <span className="text-xs text-severity-green">{e.daysRemaining} d to go</span>
              )}
            </div>
          </Card>
        ))}
      </div>

      {entries.length === 0 && (
        <Card title="No products on the schedule" subtitle="Nothing to report yet">
          <p className="text-sm text-slate-400">
            No product has an anchor date yet, so no PSUR window has been computed.
          </p>
        </Card>
      )}
    </div>
  );
}
