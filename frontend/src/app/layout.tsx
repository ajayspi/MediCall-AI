import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MediCall AI — Voice-First Medical Call Center",
  description:
    "AI phone reception for Indian clinics: 5-language triage, appointments, prescriptions and payments.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-background text-slate-100 antialiased font-sans">{children}</body>
    </html>
  );
}