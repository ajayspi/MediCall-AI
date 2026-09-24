"use client";

// src/app/login/page.tsx — auth entry (password + OTP tabs, spec-auth.md Q3).
// Calls the /api/auth/* client surface; in mock/dev mode (NEXT_PUBLIC_USE_MOCK
// != false) a demo login unlocks the dashboard shells without a backend.

import { useState } from "react";
import { useRouter } from "next/navigation";
import { loginOtpRequest, loginOtpVerify, loginPassword } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const USE_MOCK = (process.env.NEXT_PUBLIC_USE_MOCK ?? "auto").toLowerCase();

type Mode = "password" | "otp";

export default function LoginPage() {
  const { adoptSession, demoLogin } = useAuth();
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("password");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // password tab
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  // otp tab
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [otpSent, setOtpSent] = useState(false);

  async function submitPassword(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      adoptSession(await loginPassword(username.trim(), password));
      router.push("/dashboard");
    } catch {
      setError("Invalid phone/email or password.");
    } finally {
      setBusy(false);
    }
  }

  async function sendOtp(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await loginOtpRequest(phone.trim());
      setOtpSent(true);
    } catch {
      setError("Could not send OTP — check the phone number.");
    } finally {
      setBusy(false);
    }
  }

  async function submitOtp(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      adoptSession(await loginOtpVerify(phone.trim(), code.trim()));
      router.push("/dashboard");
    } catch {
      setError("Invalid or expired code.");
    } finally {
      setBusy(false);
    }
  }

  function enterDemo() {
    if (demoLogin()) router.push("/dashboard");
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-background p-6">
      <div className="w-full max-w-sm rounded-2xl border bg-card p-8 shadow-sm">
        <h1 className="text-2xl font-semibold text-foreground">MediCall AI</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Sign in to the call center console
        </p>

        <div className="mt-6 grid grid-cols-2 gap-1 rounded-lg bg-muted p-1 text-sm">
          {(["password", "otp"] as Mode[]).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => {
                setMode(m);
                setError("");
              }}
              className={
                mode === m
                  ? "rounded-md bg-background px-3 py-1.5 font-medium"
                  : "px-3 py-1.5 text-muted-foreground"
              }
            >
              {m === "password" ? "Password" : "OTP"}
            </button>
          ))}
        </div>

        {mode === "password" ? (
          <form onSubmit={submitPassword} className="mt-6 space-y-4">
            <label className="block text-sm font-medium">
              Phone or email
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoComplete="username"
                className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
                placeholder="+91 98…  or you@clinic.in"
              />
            </label>
            <label className="block text-sm font-medium">
              Password
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
                placeholder="••••••••"
              />
            </label>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60"
            >
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>
        ) : (
          <form onSubmit={otpSent ? submitOtp : sendOtp} className="mt-6 space-y-4">
            <label className="block text-sm font-medium">
              Phone number
              <input
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                required
                autoComplete="tel"
                className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
                placeholder="+91 98…"
              />
            </label>
            {otpSent && (
              <label className="block text-sm font-medium">
                Verification code
                <input
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  required
                  pattern="[0-9]{6}"
                  className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
                  placeholder="123456"
                />
              </label>
            )}
            {error && <p className="text-sm text-destructive">{error}</p>}
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60"
            >
              {busy ? "Please wait…" : otpSent ? "Verify code" : "Send OTP"}
            </button>
          </form>
        )}

        {USE_MOCK !== "false" && (
          <button
            type="button"
            onClick={enterDemo}
            className="mt-4 w-full text-center text-sm text-muted-foreground underline underline-offset-2"
          >
            Continue with demo data (offline)
          </button>
        )}
      </div>
    </main>
  );
}