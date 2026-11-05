"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import { api, ApiError, type User } from "@/lib/api";
import { TAGLINE, Wordmark } from "./Brand";

const NAV = [
  { href: "/", label: "Dashboard", icon: "M3 12l9-8 9 8M5 10v10h14V10" },
  { href: "/projects/new", label: "New Project", icon: "M12 5v14M5 12h14" },
  { href: "/extractor", label: "Bass Extractor", icon: "M4 12h3l2-6 4 12 2-6h5" },
  { href: "/tabulator", label: "Tabulator", icon: "M4 6h16M4 10h16M4 14h16M4 18h16" },
  { href: "/projects", label: "My Projects", icon: "M4 5h6l2 2h8v12H4z" },
  { href: "/settings", label: "Settings", icon: "M12 15a3 3 0 100-6 3 3 0 000 6zM19 12l2-1-2-4-2 1-2-1V5h-4v2l-2 1-2-1-2 4 2 1v0l-2 1 2 4 2-1 2 1v2h4v-2l2-1 2 1 2-4z" },
];

const UserCtx = createContext<User | null>(null);
export const useUser = () => useContext(UserCtx);

function Icon({ d }: { d: string }) {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg>;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api<User>("/auth/me").then(setUser).catch((e: ApiError) => {
      if (e.status === 401) router.replace("/login");
      else setErr("Server tidak dapat dihubungi. Cek backend.");
    });
  }, [router]);

  const active = (href: string) => (href === "/" ? path === "/" : path === href || (href === "/projects" ? /^\/projects\/(?!new)/.test(path) : path.startsWith(href + "/")));

  async function logout() {
    await api("/auth/logout", { method: "POST" }).catch(() => {});
    router.replace("/login");
  }

  if (err) return <div className="p-8 text-bad">{err}</div>;
  if (!user) return <div className="flex min-h-screen items-center justify-center text-ink-400">Memuat…</div>;

  return (
    <UserCtx.Provider value={user}>
      <div className="flex min-h-screen">
        <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-ink-800 bg-ink-950 p-4 lg:flex">
          <Link href="/"><Wordmark /></Link>
          <p className="mt-3 text-[9px] font-semibold tracking-[0.2em] text-ink-400">{TAGLINE}</p>
          <nav className="mt-8 space-y-1">
            {NAV.map((n) => (
              <Link key={n.href} href={n.href}
                className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${active(n.href) ? "bg-volt/10 text-volt" : "text-ink-300 hover:bg-ink-850 hover:text-ink-100"}`}>
                <Icon d={n.icon} />{n.label}
              </Link>
            ))}
          </nav>
          <div className="mt-auto border-t border-ink-800 pt-4 text-sm">
            <div className="truncate font-semibold">{user.display_name}</div>
            <div className="truncate text-xs text-ink-400">{user.email}</div>
            <button onClick={logout} className="mt-3 text-xs text-ink-400 hover:text-bad">Keluar</button>
          </div>
        </aside>
        <div className="min-w-0 flex-1 pb-20 lg:pb-0">
          <header className="flex items-center justify-between border-b border-ink-800 px-4 py-3 lg:hidden">
            <Link href="/"><Wordmark /></Link>
            <button onClick={logout} className="text-xs text-ink-400">Keluar</button>
          </header>
          <main className="mx-auto max-w-7xl p-4 sm:p-6">{children}</main>
        </div>
        <nav className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-6 border-t border-ink-800 bg-ink-950/95 backdrop-blur lg:hidden">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} className={`flex flex-col items-center gap-1 py-2 text-[9px] ${active(n.href) ? "text-volt" : "text-ink-400"}`}>
              <Icon d={n.icon} /><span className="truncate">{n.label.replace("Bass ", "")}</span>
            </Link>
          ))}
        </nav>
      </div>
    </UserCtx.Provider>
  );
}

export function StatusChip({ status }: { status: string }) {
  const map: Record<string, string> = {
    draft: "bg-ink-700 text-ink-300", ready: "bg-volt/15 text-volt", queued: "bg-warn/15 text-warn",
    processing: "bg-warn/15 text-warn", completed: "bg-volt/15 text-volt", failed: "bg-bad/15 text-bad",
  };
  const label: Record<string, string> = { draft: "Belum ada audio", ready: "Siap", queued: "Antre ekstraksi", processing: "Mengekstrak", completed: "Stem siap", failed: "Ekstraksi gagal" };
  return <span className={`chip ${map[status] ?? "bg-ink-700"}`}>{label[status] ?? status}</span>;
}

export const fmtTime = (s: number) => {
  if (!Number.isFinite(s)) return "0:00";
  const m = Math.floor(s / 60), r = s - m * 60;
  return `${m}:${r < 10 ? "0" : ""}${r.toFixed(1)}`;
};
export const fmtSize = (b: number) => (b > 1 << 20 ? `${(b / (1 << 20)).toFixed(1)} MB` : `${Math.round(b / 1024)} KB`);
