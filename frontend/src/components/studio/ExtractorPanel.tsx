"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { fmtSize, fmtTime } from "@/components/AppShell";
import { ACCEPT } from "@/components/AudioDrop";
import { api, json, uploadBassStem, type Job, type Project, type SepStatus, type Stem } from "@/lib/api";

/** Bass extraction: pick model -> queue job -> live progress -> stems (preview / download) + manual bass upload. */
export function ExtractorPanel({ project, onStemsChanged }: { project: Project; onStemsChanged: (s: Stem[]) => void }) {
  const [status, setStatus] = useState<SepStatus | null>(null);
  const [model, setModel] = useState("htdemucs");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [stems, setStems] = useState<Stem[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [warn, setWarn] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [upPct, setUpPct] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const cbRef = useRef(onStemsChanged);
  cbRef.current = onStemsChanged;

  const active = jobs.find((j) => j.status === "queued" || j.status === "processing") ?? null;
  const last = jobs[0] ?? null;

  const refresh = useCallback(async () => {
    const [j, s] = await Promise.all([api<Job[]>(`/projects/${project.id}/jobs`), api<Stem[]>(`/projects/${project.id}/stems`)]);
    setJobs(j);
    setStems((prev) => {
      if (prev.map((x) => x.id).join() !== s.map((x) => x.id).join()) cbRef.current(s);
      return s;
    });
  }, [project.id]);

  useEffect(() => {
    api<SepStatus>("/separation/status").then((s) => { setStatus(s); setModel(s.default_model); }).catch(() => {});
    refresh().catch((e) => setErr(e.message));
  }, [refresh]);

  // poll only while a job is running
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => refresh().catch(() => {}), 2000);
    return () => clearInterval(t);
  }, [active, refresh]);

  async function start() {
    setErr(null);
    setBusy(true);
    try {
      await api(`/projects/${project.id}/separate`, { method: "POST", body: json({ model }) });
      await refresh();
    } catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  }

  async function cancel() {
    if (!active || !confirm("Batalkan ekstraksi yang sedang berjalan?")) return;
    try { await api(`/projects/${project.id}/jobs/${active.id}/cancel`, { method: "POST" }); await refresh(); }
    catch (e) { setErr((e as Error).message); }
  }

  async function uploadOwn(f: File | undefined) {
    if (!f) return;
    setErr(null); setWarn(null); setUpPct(0);
    try {
      const r = await uploadBassStem(project.id, f, setUpPct);
      setWarn(r.warning);
      await refresh();
    } catch (e) { setErr((e as Error).message); }
    finally { setUpPct(null); if (fileRef.current) fileRef.current.value = ""; }
  }

  async function removeStem(s: Stem) {
    if (!confirm(`Hapus stem ${s.label}?`)) return;
    await api(`/projects/${project.id}/stems/${s.id}`, { method: "DELETE" }).catch((e) => setErr(e.message));
    await refresh();
  }

  const sel = status?.models.find((m) => m.key === model);
  const dur = project.audio?.duration_sec ?? 0;
  const estimate = sel?.measured_ratio ? `±${fmtTime(sel.measured_ratio * dur)} (diukur dari job sebelumnya di server ini)` : null;
  const workerDown = status && (!status.redis_online || status.workers_online === 0);

  return (
    <div className="card space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-semibold">Bass Extractor</h2>
        {status && (
          <span className={`chip ${workerDown ? "bg-bad/15 text-bad" : "bg-volt/15 text-volt"}`}>
            {workerDown ? "Worker offline" : `Worker online${status.queue_length ? ` · antre ${status.queue_length}` : ""}`}
          </span>
        )}
      </div>

      {!project.audio ? (
        <p className="text-sm text-ink-400">Upload lagu dulu untuk mengekstrak bass.</p>
      ) : active ? (
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span>{active.status === "queued" ? "Menunggu antrean…" : active.stage}</span>
            <span className="font-mono">{Math.round(active.progress * 100)}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-ink-700">
            <div className="h-full bg-volt transition-all duration-700" style={{ width: `${Math.max(2, active.progress * 100)}%` }} />
          </div>
          <p className="text-xs text-ink-400">Diproses di CPU server. Halaman boleh ditutup, proses tetap jalan.</p>
          <button className="btn-danger w-full" onClick={cancel}>Batalkan</button>
        </div>
      ) : (
        <div className="space-y-3">
          <div>
            <label className="label" htmlFor="sep-model">Model AI</label>
            <select id="sep-model" className="input" value={model} onChange={(e) => setModel(e.target.value)}>
              {status?.models.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
            </select>
            {sel && <p className="mt-1.5 text-xs text-ink-400">{sel.description}{estimate && <><br />Perkiraan waktu: {estimate}</>}</p>}
          </div>
          <button className="btn-primary w-full" disabled={busy || !!workerDown} onClick={start}>
            {busy ? "Mengirim…" : stems.some((s) => s.origin === "separated") ? "Ekstrak ulang" : "Ekstrak bass"}
          </button>
          {workerDown && <p className="text-xs text-bad">Worker AI tidak aktif, jadi ekstraksi tidak bisa jalan sekarang. Kamu tetap bisa upload bass stem sendiri di bawah.</p>}
        </div>
      )}

      {last?.status === "failed" && !active && <p className="rounded-xl bg-bad/10 p-3 text-sm text-bad">Ekstraksi terakhir gagal: {last.error}</p>}
      {last?.status === "completed" && !active && <p className="text-xs text-volt">{last.stage}</p>}
      {err && <p className="text-sm text-bad">{err}</p>}
      {warn && <p className="text-sm text-warn">{warn}</p>}

      {stems.length > 0 && (
        <ul className="divide-y divide-ink-800 rounded-xl border border-ink-700">
          {stems.map((s) => (
            <li key={s.id} className="space-y-2 p-3">
              <div className="flex items-center justify-between gap-2 text-sm">
                <span className={`font-semibold ${s.stem_type === "bass" ? "text-volt" : ""}`}>{s.label}</span>
                <span className="text-xs text-ink-400">{s.origin === "user_upload" ? "upload sendiri" : s.model} · {s.size_bytes ? fmtSize(s.size_bytes) : ""}</span>
              </div>
              <audio controls preload="none" src={s.stream_url} className="h-9 w-full" />
              <div className="flex gap-2 text-xs">
                <a className="btn-ghost flex-1 py-1.5" href={s.download_url}>Download {s.format?.toUpperCase()}</a>
                <button className="btn-danger py-1.5" onClick={() => removeStem(s)}>Hapus</button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <div className="border-t border-ink-800 pt-3">
        <p className="text-xs text-ink-400">Sudah punya bass stem dari aplikasi lain? Upload di sini (harus mulai di detik yang sama dengan lagu asli).</p>
        <input ref={fileRef} type="file" accept={ACCEPT} className="hidden" onChange={(e) => uploadOwn(e.target.files?.[0])} />
        <button className="btn-ghost mt-2 w-full" disabled={upPct !== null} onClick={() => fileRef.current?.click()}>
          {upPct === null ? "Upload bass stem sendiri" : upPct < 100 ? `Mengunggah ${upPct}%…` : "Memvalidasi…"}
        </button>
      </div>
    </div>
  );
}
