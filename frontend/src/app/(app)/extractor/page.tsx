"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { fmtTime, StatusChip } from "@/components/AppShell";
import { api, type Project, type SepStatus } from "@/lib/api";

export default function Extractor() {
  const [status, setStatus] = useState<SepStatus | null>(null);
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const load = () => Promise.all([api<SepStatus>("/separation/status"), api<Project[]>("/projects")])
      .then(([s, p]) => { setStatus(s); setProjects(p); }).catch((e) => setErr(e.message));
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  const down = status && (!status.redis_online || status.workers_online === 0);
  return (
    <div className="space-y-5">
      <div>
        <p className="text-xs font-semibold tracking-[0.2em] text-volt">BASS EXTRACTOR</p>
        <h1 className="mt-1 text-2xl font-bold">Pisahkan bass dari lagu</h1>
      </div>
      {err && <p className="text-bad">{err}</p>}
      {status && (
        <div className="card grid gap-3 sm:grid-cols-3">
          <div><div className="label">Worker AI</div>
            <div className={`text-lg font-bold ${down ? "text-bad" : "text-volt"}`}>{down ? "Offline" : `${status.workers_online} online`}</div></div>
          <div><div className="label">Antrean</div><div className="text-lg font-bold">{status.queue_length} job</div></div>
          <div><div className="label">Mode</div><div className="text-lg font-bold">CPU</div></div>
          <ul className="space-y-1 text-xs text-ink-400 sm:col-span-3">
            {status.models.map((m) => (
              <li key={m.key}><b className="text-ink-100">{m.label}</b> — {m.description}
                {m.measured_ratio && <> · terukur ±{m.measured_ratio.toFixed(2)}× durasi lagu</>}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="card">
        <h2 className="mb-3 font-semibold">Pilih proyek</h2>
        {projects?.length === 0 && <p className="text-ink-400">Belum ada proyek. <Link href="/projects/new" className="text-volt">Upload lagu</Link>.</p>}
        <ul className="divide-y divide-ink-800">
          {projects?.map((p) => (
            <li key={p.id}>
              <Link href={`/projects/${p.id}`} className="flex items-center justify-between gap-3 py-3 hover:text-volt">
                <div className="min-w-0">
                  <div className="truncate font-medium">{p.name}</div>
                  <div className="text-xs text-ink-400">{p.audio ? fmtTime(p.audio.duration_sec) : "tanpa audio"}</div>
                </div>
                <StatusChip status={p.status} />
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
