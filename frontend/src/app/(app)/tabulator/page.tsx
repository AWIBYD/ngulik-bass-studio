"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { StatusChip } from "@/components/AppShell";
import { api, type Project } from "@/lib/api";

export default function Tabulator() {
  const [ps, setPs] = useState<Project[] | null>(null);
  useEffect(() => { api<Project[]>("/projects").then(setPs).catch(() => setPs([])); }, []);
  return (
    <div className="space-y-5">
      <div>
        <p className="text-xs font-semibold tracking-[0.2em] text-volt">TABULATOR</p>
        <h1 className="mt-1 text-2xl font-bold">Tab otomatis & editor</h1>
      </div>
      <div className="card space-y-2 text-sm text-ink-300">
        <p><b className="text-ink-100">Alur terbaik:</b> upload lagu → Ekstrak bass → Buat tab otomatis → cek nada bergaris kuning → simpan.</p>
        <p>AI mendeteksi nada, durasi, BPM, lalu memilih senar & fret dengan perpindahan tangan paling sedikit. Teknik (hammer-on, pull-off, slide, vibrato, dead note) hanya ditebak — selalu cek.</p>
      </div>
      <div className="card">
        <h2 className="mb-3 font-semibold">Pilih proyek</h2>
        {ps?.length === 0 && <p className="text-ink-400">Belum ada proyek. <Link href="/projects/new" className="text-volt">Upload lagu</Link>.</p>}
        <ul className="divide-y divide-ink-800">
          {ps?.map((p) => (
            <li key={p.id}><Link href={`/projects/${p.id}`} className="flex items-center justify-between gap-3 py-3 hover:text-volt">
              <span className="truncate">{p.name} <span className="text-xs text-ink-400">· {p.note_count} nada</span></span>
              <StatusChip status={p.status} />
            </Link></li>
          ))}
        </ul>
      </div>
    </div>
  );
}
