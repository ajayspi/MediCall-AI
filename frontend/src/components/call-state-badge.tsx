import { Badge, type BadgeTone } from "./badge";

// The 9 call states from the G3 state machine (models/call.py CallState).
export const CALL_STATE_META: Record<string, { label: string; tone: BadgeTone }> = {
  GREETING: { label: "Greeting", tone: "blue" },
  TRIAGE: { label: "Triage", tone: "amber" },
  APPOINTMENT: { label: "Appointment", tone: "primary" },
  PRESCRIPTION: { label: "Prescription", tone: "primary" },
  COMPLETE: { label: "Complete", tone: "green" },
  ESCALATED: { label: "Escalated", tone: "red" },
  DROPPED: { label: "Dropped", tone: "neutral" },
  PAYMENT_SENT: { label: "Payment Sent", tone: "amber" },
  PAYMENT_EXPIRED: { label: "Payment Expired", tone: "red" },
};

export function CallStateBadge({ state }: { state: string }) {
  const meta = CALL_STATE_META[state] ?? { label: state, tone: "neutral" as BadgeTone };
  return <Badge tone={meta.tone}>{meta.label}</Badge>;
}