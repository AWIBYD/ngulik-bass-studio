"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { fmtSize, fmtTime, StatusChip } from "@/components/AppShell";
import { api, type Project } from "@/lib/api";

export default function Projects() {
  const [ps, setPs] = useState<Project[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = () => api<Project[]>("/projects").then(setPs).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  async function remove(p: Project) {
    if (!confirm(`Hapus proyek "${p.name}" beserta audio dan tab-nya? Tindakan ini tidak bisa dibatalkan.`)) return;
    try { await api(`/projects/${p.id}`, { method: "DELETE" }); load(); } catch (e) { setErr((e as Error).message); }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between">
        <div>
          <p className="text-xs font-semibold tracking-[0.2em] text-volt">MY PROJECTS</p>
          <h1 className="mt-1 text-2xl font-bold">Proyek saya</h1>
        </div>
        <Link href="/projects/new" className="btn-primary">+ New Project</Link>
      </div>
      {err && <p className="text-bad">{err}</p>}
      {ps?.length === 0 && <div className="card text-center text-ink-400">Belum ada proyek.</div>}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {ps?.map((p) => (
          <div key={p.id} className="card flex flex-col gap-3">
            <div className="flex items-start justify-between gap-2">
              <Link href={`/projects/${p.id}`} className="truncate text-lg font-semibold hover:text-volt">{p.name}</Link>
              <StatusChip status={p.status} />
            </div>
            <dl className="grid grid-cols-2 gap-y-1 text-xs text-ink-400">
              <dt>Tuning</dt><dd className="text-ink-100">{p.tuning.map((n) => n.replace(/\d/, "")).join("-")}</dd>
              <dt>BPM</dt><dd className="text-ink-100">{p.bpm} · {p.time_sig_num}/{p.time_sig_den}</dd>
              <dt>Audio</dt><dd className="truncate text-ink-100">{p.audio ? `${fmtTime(p.audio.duration_sec)} · ${fmtSize(p.audio.size_bytes)}` : "—"}</dd>
              <dt>Nada di tab</dt><dd className="text-ink-100">{p.note_count}</dd>
              <dt>Dibuat</dt><dd className="text-ink-100">{new Date(p.created_at).toLocaleDateString("id-ID")}</dd>
            </dl>
            <div className="mt-auto flex gap-2">
              <Link href={`/projects/${p.id}`} className="btn-ghost flex-1">Buka</Link>
              {p.audio && <a className="btn-ghost" href={`/api/projects/${p.id}/audio/${p.audio.id}/original`}>Unduh audio</a>}
              <button className="btn-danger" onClick={() => remove(p)}>Hapus</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
