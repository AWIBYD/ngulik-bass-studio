"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, json } from "@/lib/api";
import { TAGLINE, Wordmark } from "./Brand";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      const body = mode === "login" ? { email, password } : { email, password, display_name: name };
      await api(`/auth/${mode}`, { method: "POST", body: json(body) });
      router.replace("/");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-5">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4">
        <Wordmark />
        <p className="text-[11px] font-semibold tracking-[0.2em] text-ink-400">{TAGLINE}</p>
        <h1 className="pt-2 text-xl font-bold">{mode === "login" ? "Masuk" : "Buat akun"}</h1>
        {mode === "register" && (
          <div>
            <label className="label" htmlFor="name">Nama</label>
            <input id="name" className="input" value={name} onChange={(e) => setName(e.target.value)} required maxLength={80} />
          </div>
        )}
        <div>
          <label className="label" htmlFor="email">Email</label>
          <input id="email" type="email" autoComplete="email" className="input" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </div>
        <div>
          <label className="label" htmlFor="pw">Password</label>
          <input id="pw" type="password" minLength={mode === "register" ? 8 : undefined} autoComplete={mode === "login" ? "current-password" : "new-password"}
            className="input" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </div>
        {err && <p className="text-sm text-bad">{err}</p>}
        <button className="btn-primary w-full" disabled={busy}>{busy ? "Memproses…" : mode === "login" ? "Masuk" : "Daftar"}</button>
        <p className="text-center text-sm text-ink-400">
          {mode === "login" ? <>Belum punya akun? <Link className="text-volt" href="/register">Daftar</Link></>
            : <>Sudah punya akun? <Link className="text-volt" href="/login">Masuk</Link></>}
        </p>
      </form>
    </main>
  );
}
