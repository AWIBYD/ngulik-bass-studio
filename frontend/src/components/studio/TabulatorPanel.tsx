"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, json, type Job, type Project, type Stem } from "@/lib/api";

/** AI Tabulator: bass stem/original -> pitch detection -> string/fret -> editable tab (flagged notes in yellow). */
export function TabulatorPanel({ project, stems, dirty, hasNotes, onDone }: {
  project: Project; stems: Stem[]; dirty: boolean; hasNotes: boolean; onDone: () => void;
}) {
  const hasBass = stems.some((s) => s.stem_type === "bass");
  const [source, setSource] = useState<"auto" | "original">("auto");
  const [method, setMethod] = useState<"pyin" | "crepe">("pyin");
  const [mode, setMode] = useState<"replace" | "merge">("merge");
  const [applyBpm, setApplyBpm] = useState(true);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const doneRef = useRef(onDone);
  doneRef.current = onDone;

  const tjobs = jobs.filter((j) => j.type === "transcription");
  const active = tjobs.find((j) => j.status === "queued" || j.status === "processing") ?? null;
  const otherActive = jobs.some((j) => j.type !== "transcription" && (j.status === "queued" || j.status === "processing"));
  const last = tjobs[0] ?? null;
  const prevActive = useRef<string | null>(null);

  const refresh = useCallback(async () => {
    const j = await api<Job[]>(`/projects/${project.id}/jobs`);
    setJobs(j);
    const act = j.find((x) => x.type === "transcription" && (x.status === "queued" || x.status === "processing"));
    if (prevActive.current && !act) {
      const fin = j.find((x) => x.id === prevActive.current);
      if (fin?.status === "completed") doneRef.current();
    }
    prevActive.current = act?.id ?? null;
  }, [project.id]);

  useEffect(() => { refresh().catch(() => {}); }, [refresh]);
  useEffect(() => {
    if (!active && !otherActive) return;
    const t = setInterval(() => refresh().catch(() => {}), 2000);
    return () => clearInterval(t);
  }, [active, otherActive, refresh]);
  useEffect(() => { setMode(hasNotes ? "merge" : "replace"); }, [hasNotes]);

  async function start() {
    if (mode === "replace" && hasNotes && !confirm("Semua nada di tab sekarang akan diganti hasil AI. Lanjut?")) return;
    setErr(null);
    setBusy(true);
    try {
      const j = await api<Job>(`/projects/${project.id}/transcribe`, { method: "POST",
        body: json({ source: source === "auto" && hasBass ? "auto" : "original", method, mode, apply_bpm: applyBpm }) });
      prevActive.current = j.id;
      await refresh();
    } catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  }

  if (!project.audio && !hasBass) return null;
  return (
    <div className="card space-y-3">
      <h2 className="font-semibold">AI Tabulator</h2>
      {active ? (
        <div className="space-y-2">
          <div className="flex justify-between text-sm"><span>{active.status === "queued" ? "Menunggu antrean…" : active.stage}</span>
            <span className="font-mono">{Math.round(active.progress * 100)}%</span></div>
          <div className="h-2 overflow-hidden rounded-full bg-ink-700">
            <div className="h-full bg-volt transition-all duration-700" style={{ width: `${Math.max(2, active.progress * 100)}%` }} />
          </div>
        </div>
      ) : (
        <>
          <div>
            <label className="label" htmlFor="tb-src">Sumber</label>
            <select id="tb-src" className="input" value={source} onChange={(e) => setSource(e.target.value as "auto" | "original")}>
              <option value="auto">{hasBass ? "Bass stem (paling akurat)" : "Lagu asli (belum ada bass stem)"}</option>
              {hasBass && <option value="original">Lagu asli</option>}
            </select>
            {!hasBass && <p className="mt-1 text-xs text-warn">Hasil lebih akurat kalau ekstrak bass dulu.</p>}
          </div>
          <div>
            <label className="label" htmlFor="tb-m">Metode deteksi nada</label>
            <select id="tb-m" className="input" value={method} onChange={(e) => setMethod(e.target.value as "pyin" | "crepe")}>
              <option value="pyin">pYIN — cepat (±0,4× durasi lagu), dukung low B</option>
              <option value="crepe">CREPE — lebih tahan noise, ±3× durasi lagu</option>
            </select>
          </div>
          {hasNotes && (
            <div className="space-y-1 text-sm">
              <label className="flex items-center gap-2"><input type="radio" className="accent-[#39ff88]" checked={mode === "merge"} onChange={() => setMode("merge")} />Pertahankan nada manual, isi sisanya</label>
              <label className="flex items-center gap-2"><input type="radio" className="accent-[#39ff88]" checked={mode === "replace"} onChange={() => setMode("replace")} />Ganti semua nada</label>
            </div>
          )}
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-[#39ff88]" checked={applyBpm} onChange={(e) => setApplyBpm(e.target.checked)} />Pakai BPM & awal bar hasil deteksi</label>
          <button className="btn-primary w-full" disabled={busy || dirty || otherActive} onClick={start}>
            {busy ? "Mengirim…" : "Buat tab otomatis"}
          </button>
          {dirty && <p className="text-xs text-warn">Simpan tab dulu sebelum membuat tab otomatis.</p>}
          {otherActive && <p className="text-xs text-ink-400">Menunggu ekstraksi bass selesai…</p>}
        </>
      )}
      {last?.status === "completed" && !active && <p className="text-xs text-volt">Terakhir: {last.stage}</p>}
      {last?.status === "failed" && !active && <p className="rounded-xl bg-bad/10 p-3 text-sm text-bad">Gagal: {last.error}</p>}
      {err && <p className="text-sm text-bad">{err}</p>}
      <p className="text-xs text-ink-400">Nada bergaris kuning = AI ragu. Cek pakai tombol <b>Perlu dicek</b> di atas tab.</p>
    </div>
  );
}
