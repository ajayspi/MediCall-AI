import type { ReactNode } from "react";

export const BADGE_TONES = {
  neutral: "bg-slate-500/20 text-slate-300",
  green: "bg-green-500/20 text-green-400",
  amber: "bg-yellow-500/20 text-yellow-400",
  red: "bg-red-500/20 text-red-400",
  critical: "bg-red-500/30 text-red-300 ring-1 ring-red-500/40",
  primary: "bg-primary-500/20 text-primary-300",
  blue: "bg-blue-500/20 text-blue-400",
} as const;

export type BadgeTone = keyof typeof BADGE_TONES;

export function Badge({ tone = "neutral", children }: { tone?: BadgeTone; children: ReactNode }) {
  return (
    <span className={`inline-flex px-2.5 py-1 rounded-full text-xs font-medium ${BADGE_TONES[tone]}`}>
      {children}
    </span>
  );
}