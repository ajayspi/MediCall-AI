import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TalkByte AI — Restaurant Voice Ordering",
  description: "AI phone ordering for Australian restaurants",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#0f172a] text-slate-100 antialiased font-sans">{children}</body>
    </html>
  );
}