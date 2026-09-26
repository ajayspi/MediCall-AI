"use client";

// src/app/pv/cases/[id]/page.tsx - the ONE case behind a queue row, and the
// four ways a PVOIC takes it away. Phase-2.6, spec-micc-pv-phase26.md.
//
// THIS PAGE INVENTS NOTHING. Every field below is a key of `_case_row`
// (app/api/pv.py:318-352) reached through GET /api/pv/cases/{case_id} - the same
// serializer the print sheet and both e2b routes build from. That is the point:
// what the officer reads is what the regulator was handed. A field this page
// would like but the API does not carry is a backend change, not a UI guess, and
// the product dictionary id is shown as the id because the API exposes an id and
// not a name.
//
// The four actions are BUTTONS, never <a href>. The bearer token lives in
// localStorage, so a link arrives at the API with no Authorization header and
// 401s - which an officer reads as a broken button rather than as an
// authentication problem. So each action fetches through authDownload /
// authDownloadPost and hands the Blob to a real file save.
//
// A REFUSAL IS SHOWN, NEVER SWALLOWED. The 2C export gate answers 409 for an
// expedited case with no reviewer stamp, and that message is the single most
// useful thing this page can tell someone. A download that fails quietly leaves
// an officer believing an unstamped case is exportable - so the server's own
// `detail` is rendered verbatim, whatever the status.
import { useParams } from "next/navigation";
import { useState } from "react";
import type { ReactNode } from "react";
import Link from "next/link";
import { Badge, type BadgeTone } from "@/components/badge";
import { Card } from "@/components/card";
import {
  authDownload,
  authDownloadPost,
  clinicId,
  formatRelativeDate,
  pvLabel,
  usePvCase,
} from "@/lib/api";

const USE_MOCK = (process.env.NEXT_PUBLIC_USE_MOCK ?? "auto").toLowerCase();

const STATUS_TONE: Record<string, BadgeTone> = {
  new: "blue",
  open: "amber",
  notified: "primary",
  submitted: "green",
  closed: "neutral",
};

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2 border-b border-white/5 last:border-b-0">
      <span className="text-xs uppercase tracking-wide text-slate-500 shrink-0">{label}</span>
      <span className="text-sm text-slate-300 text-right">{children}</span>
    </div>
  );
}

/** A dash is the honest empty. Blank would read as "we forgot to load it". */
function orDash(value: string): string {
  return value && value.trim() ? value : "—";
}

export default function PvCaseDetailPage() {
  const params = useParams<{ id: string }>();
  const id = typeof params?.id === "string" ? params.id : "";
  const { case: row, isMock } = usePvCase(id);
  const [busy, setBusy] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);

  /**
   * One path for all four actions: ask, save, or show why not.
   *
   * The URL.createObjectURL blob is revoked right after the click is
   * dispatched - revoking it earlier can cancel the download in some browsers,
   * and never revoking it leaks the whole artifact for the life of the tab.
   */
  async function run(label: string, fetchIt: () => Promise<Blob>, filename: string) {
    setBusy(label);
    setRefusal(null);
    try {
      const blob = await fetchIt();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      // The server's own words, e.g. the 409 reviewer-stamp refusal. A thrown
      // download with no message is the failure mode this page exists to avoid.
      const detail =
        err && typeof err === "object" && "detail" in err
          ? String((err as { detail: unknown }).detail)
          : "The download could not be completed.";
      setRefusal(detail);
    } finally {
      setBusy(null);
    }
  }

  if (!row) {
    return (
      <div className="space-y-6">
        <Link href="/pv/cases" className="text-sm text-primary-300 hover:text-primary-200">
          ← Back to the case queue
        </Link>
        <Card title="Case not available" subtitle="Nothing to show for this id">
          <p className="text-sm text-slate-400">
            No case was returned for this id. It may have been entered under a
            different id, or the API is unreachable in this mode.
          </p>
        </Card>
      </div>
    );
  }

  const downloadXml = () =>
    run("E2B XML", () => authDownload(`/api/pv/cases/${id}/e2b.xml`), `e2b-${id}.xml`);

  // The batch export is the ONE JSON/CSV contract the API has
  // (POST /api/pv/export, PvExportRequest). Since 2.6 it accepts an optional
  // case_id that restricts the export to exactly this case (404 if missing);
  // the clinic filter and status are ignored when case_id is set.
  const downloadBatch = (format: "json" | "csv") =>
    run(format.toUpperCase(), () =>
      authDownloadPost("/api/pv/export", {
        clinic_id: row.clinicId || clinicId(),
        case_id: id,
        format,
      }),
    `pv-e2b-export.${format}`);

  const downloadPrint = () =>
    run(
      "Print view",
      () => authDownload(`/api/pv/cases/${id}/print`),
      `pv-case-${id}.html`,
    );

  const actions = [
    { label: "E2B XML", onClick: downloadXml, hint: "R3 XML for one case" },
    { label: "JSON", onClick: () => downloadBatch("json"), hint: "E2B bundle" },
    { label: "CSV", onClick: () => downloadBatch("csv"), hint: "Flat interchange" },
    { label: "Print view", onClick: downloadPrint, hint: "Printable case sheet" },
  ];

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link href="/pv/cases" className="text-sm text-primary-300 hover:text-primary-200">
            ← Back to the case queue
          </Link>
          <h1 className="text-3xl font-bold text-white mt-2">Case {row.id.slice(0, 8).toUpperCase()}</h1>
          <p className="text-slate-400 mt-1">
            {row.caseType} · received {formatRelativeDate(row.receivedAt)} ·{" "}
            {row.sourceChannel}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={STATUS_TONE[row.status] ?? "neutral"}>{pvLabel(row.status)}</Badge>
          {row.isSerious ? (
            <Badge tone="critical">Serious</Badge>
          ) : (
            <Badge tone="neutral">Non-serious</Badge>
          )}
          <Badge tone={row.e2bMinimumMet ? "green" : "amber"}>
            E2B minimum {row.e2bMinimumMet ? "met" : "not met"}
          </Badge>
        </div>
      </div>

      {/* The actions, and any refusal. A disabled action says WHY it is
          disabled: a greyed-out button with no reason reads as a broken build. */}
      <div className="card p-6">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-xs uppercase tracking-wide text-slate-500">Export</span>
          {actions.map((action) => (
            <button
              key={action.label}
              type="button"
              title={action.hint}
              disabled={busy !== null || isMock}
              onClick={action.onClick}
              className="px-3 py-1.5 rounded-full text-xs font-medium border border-primary-500/40 bg-primary-500/20 text-primary-300 transition-colors hover:bg-primary-500/30 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {busy === action.label ? `${action.label}…` : action.label}
            </button>
          ))}
        </div>
        {isMock && (
          <p className="text-xs text-slate-500 mt-3">
            Demo data — exports are disabled because there is no real case to
            export. Set NEXT_PUBLIC_USE_MOCK=false to download from the API.
          </p>
        )}
        {refusal && (
          <p className="text-sm text-red-300 mt-3" role="alert">
            {refusal}
          </p>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Patient & product" subtitle="Who the report is about">
          <Row label="Patient">{orDash(row.patient)}</Row>
          <Row label="Product">{orDash(row.product)}</Row>
          <Row label="Event onset">{formatRelativeDate(row.eventOnsetDate)}</Row>
          <Row label="Outcome">{orDash(row.outcome)}</Row>
          <Row label="Expectedness">{orDash(pvLabel(row.expectedness))}</Row>
        </Card>

        <Card title="Event (verbatim)" subtitle="As the caller reported it — no interpretation">
          <p className="text-sm text-slate-200">{orDash(row.eventText)}</p>
          <div className="mt-4">
            <span className="text-xs uppercase tracking-wide text-slate-500">Seriousness</span>
            <div className="flex flex-wrap gap-2 mt-2">
              {row.criteria.length ? (
                row.criteria.map((flag) => (
                  <Badge key={flag} tone="red">
                    {pvLabel(flag)}
                  </Badge>
                ))
              ) : (
                <span className="text-sm text-slate-500">No ICH E2A criterion reported</span>
              )}
            </div>
          </div>
        </Card>

        <Card title="WHO-UMC causality" subtitle="Captured, not derived — each assessment is a human's own words">
          <Row label="Reporter's own words">{orDash(row.causalityReporter)}</Row>
          <Row label="Reporter assessment">{orDash(pvLabel(row.reporterCausality))}</Row>
          <Row label="Reviewer assessment">
            {row.reviewerCausality ? (
              <Badge tone="primary">{pvLabel(row.reviewerCausality)}</Badge>
            ) : (
              <span className="text-amber-400">Not yet reviewed — the export gate will refuse this case</span>
            )}
          </Row>
          <Row label="Reviewed by">{orDash(row.reviewedBy)}</Row>
          <Row label="Reviewed at">{formatRelativeDate(row.reviewedAt)}</Row>
        </Card>

        <Card title="Coding" subtitle="A dictionary lookup, never an invented code">
          {row.coding.coded ? (
            <>
              <Row label="Event PT">{row.coding.event?.pt ?? "—"}</Row>
              <Row label="Event code">{row.coding.event?.code ?? "—"}</Row>
              <Row label="SOC">{row.coding.event?.soc ?? "—"}</Row>
              <Row label="HLT">{row.coding.event?.hlt ?? "—"}</Row>
              <Row label="Drug">{row.coding.drug?.name ?? "— not in the dictionary"}</Row>
              <Row label="Dictionary">{orDash(row.coding.dictionary)}</Row>
            </>
          ) : (
            <p className="text-sm text-slate-400">
              Not coded against the installed dictionary
              {row.coding.reason ? `: ${row.coding.reason}` : "."} A reported miss is
              stored as a miss — no code is ever invented for it.
            </p>
          )}
        </Card>

        <Card title="Notification clock" subtitle="The India 15/90-day deadline, as stored">
          <Row label="Deadline">{formatRelativeDate(row.deadline)}</Row>
          <Row label="Time left">
            {row.overdue ? (
              <Badge tone="red">{Math.abs(row.daysRemaining)} d overdue</Badge>
            ) : row.daysRemaining === 0 ? (
              <Badge tone="amber">Due today</Badge>
            ) : (
              <span>{row.daysRemaining} d left</span>
            )}
          </Row>
          <Row label="Notified at">{formatRelativeDate(row.notifiedAt)}</Row>
        </Card>

        <Card title="Capture & audit" subtitle="What the record says about itself">
          <Row label="Reporter type">{orDash(row.reporterType)}</Row>
          {row.reporter.map((entry) => (
            <Row key={entry.label} label={entry.label}>
              {orDash(entry.value)}
            </Row>
          ))}
          <Row label="Source channel">{orDash(row.sourceChannel)}</Row>
          <Row label="Recording consent">
            {row.recordingConsent ? (
              <Badge tone="green">Given</Badge>
            ) : (
              <Badge tone="neutral">Not given</Badge>
            )}
          </Row>
          <Row label="Received at">{formatRelativeDate(row.receivedAt)}</Row>
        </Card>
      </div>
    </div>
  );
}
