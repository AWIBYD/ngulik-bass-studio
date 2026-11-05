"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { fmtTime, StatusChip, useUser } from "@/components/AppShell";
import { api, type Project } from "@/lib/api";

type Dash = {
  total_projects: number;
  recent: Project[];
  processing: { id: string; project_id: string; type: string; status: string; progress: number }[];
  last_tab: Project | null;
};

export default function Dashboard() {
  const user = useUser();
  const [d, setD] = useState<Dash | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api<Dash>("/dashboard").then(setD).catch((e) => setErr(e.message)); }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-semibold tracking-[0.2em] text-volt">DASHBOARD</p>
          <h1 className="mt-1 text-2xl font-bold">Halo, {user?.display_name}</h1>
        </div>
        <Link href="/projects/new" className="btn-primary">+ New Project</Link>
      </div>
      {err && <p className="text-bad">{err}</p>}
      {d && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Total proyek" value={d.total_projects} />
            <Stat label="Sedang diproses" value={d.processing.length} />
            <Stat label="Proyek terakhir" value={d.recent[0]?.name ?? "—"} small href={d.recent[0] ? `/projects/${d.recent[0].id}` : undefined} />
            <Stat label="Tab terakhir" value={d.last_tab ? `${d.last_tab.name} · ${d.last_tab.note_count} nada` : "—"} small
              href={d.last_tab ? `/projects/${d.last_tab.id}` : undefined} />
          </div>
          {d.processing.length > 0 && (
            <div className="card">
              <h2 className="mb-3 font-semibold">Audio yang sedang diproses</h2>
              {d.processing.map((j) => (
                <div key={j.id} className="flex justify-between text-sm"><span>{j.type === "separation" ? "Ekstraksi bass" : j.type}</span><span>{Math.round(j.progress * 100)}%</span></div>
              ))}
            </div>
          )}
          <div className="card">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-semibold">Riwayat proyek</h2>
              <Link href="/projects" className="text-sm text-volt">Lihat semua</Link>
            </div>
            {d.recent.length === 0 ? (
              <div className="py-10 text-center text-ink-400">
                Belum ada proyek. <Link href="/projects/new" className="text-volt">Mulai upload lagu pertama</Link>.
              </div>
            ) : (
              <ul className="divide-y divide-ink-800">
                {d.recent.map((p) => (
                  <li key={p.id}>
                    <Link href={`/projects/${p.id}`} className="flex items-center justify-between gap-3 py-3 hover:text-volt">
                      <div className="min-w-0">
                        <div className="truncate font-medium">{p.name}</div>
                        <div className="text-xs text-ink-400">
                          {p.audio ? fmtTime(p.audio.duration_sec) : "tanpa audio"} · {p.bpm} BPM · {p.tuning.length} senar · {p.note_count} nada
                        </div>
                      </div>
                      <StatusChip status={p.status} />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function Stat({ label, value, small, href }: { label: string; value: string | number; small?: boolean; href?: string }) {
  const inner = (
    <div className="card h-full">
      <div className="label">{label}</div>
      <div className={`${small ? "truncate text-base" : "text-3xl"} font-bold`}>{value}</div>
    </div>
  );
  return href ? <Link href={href} className="block hover:opacity-90">{inner}</Link> : inner;
}
