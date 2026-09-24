import Link from "next/link";

export default function Home() {
  return (
    <main className="flex flex-col items-center justify-center min-h-screen px-6 text-center">
      <div className="inline-flex px-3 py-1 rounded-full bg-primary-500/20 text-primary-400 text-xs font-bold uppercase tracking-wider mb-8">
        Voice-first · India
      </div>

      <h1 className="text-5xl md:text-7xl font-black text-white mb-6">
        <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary-400 to-primary-500">
          MediCall AI
        </span>
      </h1>

      <p className="text-xl text-slate-300 max-w-2xl mx-auto mb-10">
        AI phone reception for Indian clinics — 5-language triage, appointments,
        prescriptions and payments by voice.
      </p>

      <div className="flex flex-col sm:flex-row gap-4">
        <Link href="/dashboard" className="btn-primary inline-block !px-8 !py-4">
          Clinic Dashboard →
        </Link>
        <Link href="/admin" className="btn-secondary inline-block !px-8 !py-4">
          Platform Admin →
        </Link>
      </div>

      <p className="mt-10 text-sm text-slate-500">
        Marketing site, auth and signup land in a later phase.
      </p>
    </main>
  );
}