import { Badge, type BadgeTone } from "./badge";

// The 5 supported call languages (G4: hi/en/ta/te/bn).
export const LANGUAGE_LABELS: Record<string, string> = {
  hi: "हिन्दी",
  en: "English",
  ta: "தமிழ்",
  te: "తెలుగు",
  bn: "বাংলা",
};

const LANGUAGE_TONE: Record<string, BadgeTone> = {
  hi: "primary",
  en: "blue",
  ta: "amber",
  te: "red",
  bn: "green",
};

export function LanguageBadge({ lang }: { lang: string }) {
  const label = LANGUAGE_LABELS[lang] ?? lang.toUpperCase();
  return <Badge tone={LANGUAGE_TONE[lang] ?? "neutral"}>{label}</Badge>;
}