"use client";

// src/app/pv/cases/page.tsx — the PVOIC case queue, off GET /api/pv/cases
// (phase-2.5, spec-micc-pv-phase25.md). Read-only: a PVOIC looks at the
// queue, they do not change it. Case intake stays API/voice-only and the E2B
// export is service-token guarded, so there is no write action to hang here.
//
// The two filters are SERVER parameters (status=, serious_only=), not a
// client-side narrowing, so the count the officer sees is the count that
// exists. The hook only reaches for the fixtures on a transport error or
// USE_MOCK=true, and then applies the same filter locally — an empty result
// is an answer, never a reason to show unfiltered rows.
import { useState } from "react";
import type { ReactNode } from "react";
import { Badge, type BadgeTone } from "@/components/badge";
import { Card } from "@/components/card";
import { StatCard } from "@/components/stat-card";
import { clinicId, formatRelativeDate, pvLabel, usePvCases } from "@/lib/api";

/** The queue's own state machine (app/models/pharmacovigilance.py). */
const STATUSES = ["", "new", "open", "notified", "submitted", "closed"] as const;

const STATUS_TONE: Record<string, BadgeTone> = {
  new: "blue",
  open: "amber",
  notified: "primary",
  submitted: "green",
  closed: "neutral",
};

const CASE_TONE: Record<string, BadgeTone> = {
  AE: "red",
  PQC: "amber",
  MI: "blue",
};

function Chip({ active, children, onClick }: { active: boolean; children: ReactNode; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
        active
          ? "bg-primary-500/20 text-primary-300 border-primary-500/40"
          : "bg-white/5 text-slate-400 border-white/10 hover:bg-white/10"
      }`}
    >
      {children}
    </button>
  );
}

/** The deadline cell: the day count is the server's, not a browser countdown. */
function DeadlineCell({ deadline, daysRemaining, overdue }: { deadline: string; daysRemaining: number; overdue: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-slate-300">{formatRelativeDate(deadline)}</span>
      {overdue ? (
        <Badge tone="red">{Math.abs(daysRemaining)} d over</Badge>
      ) : daysRemaining === 0 ? (
        <Badge tone="amber">Due today</Badge>
      ) : (
        <span className="text-xs text-slate-500">{daysRemaining} d left</span>
      )}
    </div>
  );
}

export default function PvCasesPage() {
  const [status, setStatus] = useState<string>("");
  const [seriousOnly, setSeriousOnly] = useState(false);
  const { rows, kpis } = usePvCases(clinicId(), status, seriousOnly);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">Case Queue</h1>
        <p className="text-slate-400 mt-1">
          Adverse events, product quality complaints and medical information
          inquiries — live from /api/pv/cases.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
        {kpis.map((k) => (
          <StatCard key={k.label} {...k} />
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs uppercase tracking-wide text-slate-500">Status</span>
          {STATUSES.map((s) => (
            <Chip key={s || "all"} active={status === s} onClick={() => setStatus(s)}>
              {s ? pvLabel(s) : "All"}
            </Chip>
          ))}
        </div>
        <div className="h-5 w-px bg-white/10 hidden sm:block" />
        <Chip active={seriousOnly} onClick={() => setSeriousOnly((v) => !v)}>
          Serious only
        </Chip>
        <span className="text-xs text-slate-500">
          {rows.length} case{rows.length === 1 ? "" : "s"} shown
        </span>
      </div>

      <Card title="Cases" subtitle="Ordered by the reporting deadline, most urgent first">
        {rows.length === 0 ? (
          <p className="text-sm text-slate-400">
            No case matches this filter. The queue is genuinely empty — widen the
            status chip or turn off serious only.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-sm text-slate-500 border-b border-white/10">
                  <th className="pb-3 font-medium">Case</th>
                  <th className="pb-3 font-medium">Product / Patient</th>
                  <th className="pb-3 font-medium">Event (verbatim)</th>
                  <th className="pb-3 font-medium">Seriousness</th>
                  <th className="pb-3 font-medium">Received</th>
                  <th className="pb-3 font-medium">Notification Deadline</th>
                  <th className="pb-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {rows.map((c) => (
                  <tr key={c.id} className="hover:bg-white/[0.02] align-top">
                    <td className="py-4">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-white">{c.id}</span>
                        <Badge tone={CASE_TONE[c.caseType] ?? "neutral"}>{c.caseType}</Badge>
                      </div>
                      {!c.e2bMinimumMet && (
                        <p className="text-[10px] text-slate-500 mt-1">E2B minimum not met</p>
                      )}
                    </td>
                    <td className="py-4">
                      {/* The 2E serializer exposes the product dictionary id, not a
                          name — so the queue shows the id rather than invent one. */}
                      <div className="text-sm text-slate-300">{c.product}</div>
                      <div className="text-xs text-slate-500 mt-1">{c.patient}</div>
                    </td>
                    <td className="py-4 max-w-md">
                      <p className="text-sm text-slate-300">{c.eventText}</p>
                    </td>
                    <td className="py-4">
                      {c.isSerious ? (
                        <div>
                          <Badge tone="critical">Serious</Badge>
                          <p className="text-xs text-slate-500 mt-1">
                            {c.criteria.map(pvLabel).join(", ")}
                          </p>
                        </div>
                      ) : (
                        <span className="text-sm text-slate-500">Non-serious</span>
                      )}
                    </td>
                    <td className="py-4 text-sm text-slate-400">
                      {formatRelativeDate(c.receivedAt)}
                    </td>
                    <td className="py-4">
                      <DeadlineCell
                        deadline={c.deadline}
                        daysRemaining={c.daysRemaining}
                        overdue={c.overdue}
                      />
                    </td>
                    <td className="py-4">
                      <Badge tone={STATUS_TONE[c.status] ?? "neutral"}>
                        {pvLabel(c.status)}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
