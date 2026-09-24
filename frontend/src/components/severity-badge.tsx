import { Badge, type BadgeTone } from "./badge";

// Triage severity levels (G3 TriageSeverity): green/amber/red/critical.
export const SEVERITY_META: Record<string, { label: string; tone: BadgeTone }> = {
  green: { label: "Green", tone: "green" },
  amber: { label: "Amber", tone: "amber" },
  red: { label: "Red", tone: "red" },
  critical: { label: "Critical", tone: "critical" },
};

export function SeverityBadge({ severity }: { severity: string }) {
  const meta = SEVERITY_META[severity] ?? { label: severity, tone: "neutral" as BadgeTone };
  return <Badge tone={meta.tone}>{meta.label}</Badge>;
}