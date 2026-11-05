"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { fmtSize, fmtTime, StatusChip } from "@/components/AppShell";
import { AudioDrop, type Picked } from "@/components/AudioDrop";
import type { FrameFn } from "@/components/studio/frame";
import { ExtractorPanel } from "@/components/studio/ExtractorPanel";
import { Fretboard } from "@/components/studio/Fretboard";
import { Inspector } from "@/components/studio/Inspector";
import { TabView } from "@/components/studio/TabView";
import { Waveform } from "@/components/studio/Waveform";
import { TuningPicker } from "@/components/TuningPicker";
import { api, ApiError, json, streamUrl, uploadAudio, type Note, type Project, type Stem, type Tab, type UserSettings } from "@/lib/api";
import { activeNoteIds } from "@/lib/clock";
import { editorReducer, initialEditor, newId } from "@/lib/editor";
import { gridStep, snapTime } from "@/lib/music";
import { SPEEDS, Transport } from "@/lib/transport";

type View = "tab" | "both" | "fretboard";

export default function Studio() {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [tab, setTab] = useState<Tab | null>(null);
  const [peaks, setPeaks] = useState<number[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [ed, dispatch] = useReducer(editorReducer, initialEditor);
  const [transport, setTransport] = useState<Transport | null>(null);
  const [, force] = useReducer((x: number) => x + 1, 0);
  const [view, setView] = useState<View>("both");
  const [pps, setPps] = useState(140);
  const [snap, setSnap] = useState(true);
  const [autoScroll, setAutoScroll] = useState(true);
  const [saving, setSaving] = useState(false);
  const [picked, setPicked] = useState<Picked | null>(null);
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const lastFret = useRef(0);
  const [stems, setStems] = useState<Stem[]>([]);
  const [source, setSource] = useState<string>("original"); // "original" or a stem id

  // ---------- load ----------
  const loadAll = useCallback(async () => {
    try {
      const [p, t] = await Promise.all([api<Project>(`/projects/${id}`), api<Tab>(`/projects/${id}/tab`)]);
      setProject(p);
      setTab(t);
      dispatch({ type: "load", notes: t.notes });
      if (p.audio) setStems(await api<Stem[]>(`/projects/${id}/stems`));
    } catch (e) { setErr((e as Error).message); }
  }, [id]);
  useEffect(() => { loadAll(); }, [loadAll]);
  useEffect(() => { api<UserSettings>("/settings").then((s) => { setAutoScroll(s.auto_scroll); transport?.setRate(s.default_playback_rate); }).catch(() => {}); }, [transport]);

  // ---------- audio source (original / bass / backing track ...) ----------
  const sourceStem = stems.find((s) => s.id === source) ?? null;
  useEffect(() => { if (source !== "original" && !sourceStem) setSource("original"); }, [source, sourceStem]);
  const url = project ? (sourceStem ? sourceStem.stream_url : streamUrl(project)) : null;
  const waveUrl = project?.audio ? (sourceStem ? sourceStem.waveform_url : `/api/projects/${id}/audio/${project.audio.id}/waveform`) : null;
  useEffect(() => {
    if (!waveUrl) return;
    api<{ points: number[] }>(waveUrl.replace(/^\/api/, "")).then((w) => setPeaks(w.points)).catch(() => setPeaks(null));
  }, [waveUrl]);

  // ---------- transport ----------
  // When the source changes, the new player continues at the same song position, speed, loop and volume.
  const carry = useRef<{ t: number; rate: number; vol: number; loop: Transport["loop"]; playing: boolean; offset: number } | null>(null);
  const transportRef = useRef<Transport | null>(null);
  useEffect(() => {
    if (!url) return;
    const t = new Transport(url);
    transportRef.current = t;
    const c = carry.current;
    if (c) {
      t.setVolume(c.vol);
      t.userOffsetMs = c.offset;
      t.loop = { ...c.loop };
      t.el.addEventListener("loadedmetadata", () => {
        t.seek(c.t);
        t.setRate(c.rate);
        if (c.playing) t.play().catch(() => {});
      }, { once: true });
    }
    const unsub = t.subscribe(force);
    setTransport(t);
    // Diagnostics for automated sync tests only (opt-in per browser).
    try { if (localStorage.getItem("nbs-debug") === "1") (window as unknown as { __nbs: Transport }).__nbs = t; } catch { /* storage blocked */ }
    return () => {
      carry.current = { t: t.time(), rate: t.rate, vol: t.getVolume(), loop: { ...t.loop }, playing: t.playing, offset: t.userOffsetMs };
      unsub(); t.dispose(); setTransport(null);
    };
  }, [url]);

  // ---------- frame loop: one clock, many views ----------
  const subs = useRef(new Set<FrameFn>());
  const subscribe = useCallback((fn: FrameFn) => { subs.current.add(fn); return () => { subs.current.delete(fn); }; }, []);
  const notesRef = useRef<Note[]>([]);
  const startsRef = useRef<number[]>([]);
  const maxDurRef = useRef(0);
  useEffect(() => {
    notesRef.current = ed.notes;
    startsRef.current = ed.notes.map((n) => n.start_time);
    maxDurRef.current = ed.notes.reduce((m, n) => Math.max(m, n.duration), 0);
  }, [ed.notes]);
  useEffect(() => {
    let raf = 0;
    const loop = () => {
      const t = transport ? transport.time() : 0;
      const active = new Set(activeNoteIds(notesRef.current, startsRef.current, t, maxDurRef.current));
      const playing = transport?.playing ?? false;
      subs.current.forEach((f) => f(t, active, playing));
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [transport]);

  const timeLabel = useRef<HTMLSpanElement>(null);
  useEffect(() => subscribe((t) => { if (timeLabel.current) timeLabel.current.textContent = fmtTime(t); }), [subscribe]);

  // ---------- editing ----------
  const grid = project ? gridStep(project.bpm, 4) : 0.125;
  const selected = ed.notes.find((n) => n.id === ed.selected) ?? null;
  const tuning = project?.tuning ?? ["E1", "A1", "D2", "G2"];
  const measures = useMemo(() => tab?.measures ?? [], [tab]);

  const addNote = useCallback((t: number, s: number) => {
    if (!project) return;
    const start = snap ? snapTime(t, project.bpm, project.offset_sec, 4) : +t.toFixed(4);
    dispatch({ type: "add", note: { id: newId(), string_number: s, fret_number: lastFret.current, start_time: start,
      duration: +(grid * 2).toFixed(6), technique: "normal", confidence_score: 1, source: "manual", needs_review: false } });
  }, [project, snap, grid]);

  const update = useCallback((patch: Partial<Note>) => {
    if (!ed.selected) return;
    if (patch.fret_number !== undefined) lastFret.current = patch.fret_number;
    dispatch({ type: "update", id: ed.selected, patch });
  }, [ed.selected]);

  const save = useCallback(async () => {
    if (!tab || saving) return;
    setSaving(true);
    setMsg(null);
    try {
      const out = await api<Tab>(`/projects/${id}/tab`, { method: "PUT", body: json({ version: tab.version, notes: ed.notes.map(
        ({ id, string_number, fret_number, start_time, duration, technique, confidence_score, source, needs_review, velocity }) =>
          ({ id, string_number, fret_number, start_time, duration, technique, confidence_score, source, needs_review, velocity })) }) });
      setTab(out);
      dispatch({ type: "saved", notes: out.notes });
      setMsg("Tab tersimpan.");
    } catch (e) {
      setMsg((e as ApiError).status === 409 ? "Konflik: tab berubah di tab/perangkat lain. Muat ulang halaman." : (e as Error).message);
    } finally { setSaving(false); }
  }, [tab, saving, id, ed.notes]);

  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (ed.dirty) { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [ed.dirty]);

  // ---------- keyboard ----------
  const digitBuf = useRef<{ v: string; at: number }>({ v: "", at: 0 });
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "s") { e.preventDefault(); save(); return; }
      if (mod && e.key.toLowerCase() === "z") { e.preventDefault(); dispatch({ type: e.shiftKey ? "redo" : "undo" }); return; }
      if (mod && e.key.toLowerCase() === "y") { e.preventDefault(); dispatch({ type: "redo" }); return; }
      if (e.key === " ") { e.preventDefault(); transport?.toggle(); return; }
      if (!selected) return;
      if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); dispatch({ type: "remove", id: selected.id }); }
      else if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        e.preventDefault();
        update({ start_time: Math.max(0, +(selected.start_time + (e.key === "ArrowLeft" ? -grid : grid)).toFixed(6)) });
      } else if (e.key === "ArrowUp" || e.key === "ArrowDown") {
        e.preventDefault();
        const s = selected.string_number + (e.key === "ArrowUp" ? -1 : 1);
        if (s >= 1 && s <= tuning.length) update({ string_number: s });
      } else if (/^\d$/.test(e.key)) {
        const now = performance.now();
        const b = digitBuf.current;
        const two = now - b.at < 700 && b.v.length === 1 ? Number(b.v + e.key) : NaN;
        const fret = !Number.isNaN(two) && two <= 24 ? two : Number(e.key);
        digitBuf.current = { v: !Number.isNaN(two) && two <= 24 ? "" : e.key, at: now };
        update({ fret_number: fret });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected, transport, save, update, grid, tuning.length]);

  // ---------- transport helpers ----------
  const seek = useCallback((t: number) => transport?.seek(t), [transport]);
  const barAt = (t: number) => measures.findLast?.((m) => m.start_time <= t + 1e-6) ?? measures.filter((m) => m.start_time <= t + 1e-6).pop();
  const jumpBar = (dir: -1 | 1) => {
    if (!transport) return;
    const t = transport.time();
    const cur = barAt(t);
    const idx = cur ? cur.index : 0;
    const target = dir === 1 ? measures[idx + 1] : (cur && t - cur.start_time > 0.3 ? cur : measures[Math.max(0, idx - 1)]);
    if (target) transport.seek(target.start_time);
  };
  const loopBar = () => {
    if (!transport) return;
    const m = barAt(transport.time());
    if (m) transport.setLoop(true, m.start_time, m.start_time + m.duration);
  };

  async function uploadHere() {
    if (!picked || picked.error) return;
    setErr(null);
    try {
      setUploadPct(0);
      await uploadAudio(id, picked.file, setUploadPct);
      setPicked(null);
      await loadAll();
    } catch (e) { setErr((e as Error).message); }
    finally { setUploadPct(null); }
  }

  if (err && !project) return <p className="text-bad">{err}</p>;
  if (!project || !tab) return <p className="text-ink-400">Memuat studio…</p>;

  const tr = transport;
  return (
    <div className="space-y-4">
      {/* header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link href="/projects" className="text-xs text-ink-400 hover:text-volt">← My Projects</Link>
          <h1 className="truncate text-2xl font-bold">{project.name}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-400">
            <StatusChip status={project.status} />
            <span>{project.bpm} BPM · {project.time_sig_num}/{project.time_sig_den}</span>
            <span>· {project.tuning.map((n) => n.replace(/\d/, "")).join("-")}</span>
            {project.audio && <span>· {project.audio.format.toUpperCase()} {fmtSize(project.audio.size_bytes)}</span>}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {ed.dirty && <span className="chip bg-warn/15 text-warn">Belum disimpan</span>}
          <button className="btn-ghost" disabled={!ed.past.length} onClick={() => dispatch({ type: "undo" })} title="Undo (Ctrl+Z)">Undo</button>
          <button className="btn-ghost" disabled={!ed.future.length} onClick={() => dispatch({ type: "redo" })} title="Redo (Ctrl+Y)">Redo</button>
          <button className="btn-primary" disabled={!ed.dirty || saving} onClick={save}>{saving ? "Menyimpan…" : "Simpan tab"}</button>
        </div>
      </div>
      {msg && <p className="text-sm text-volt">{msg}</p>}
      {err && <p className="text-sm text-bad">{err}</p>}

      {/* audio */}
      {project.audio ? (
        <div className="card space-y-3 p-4">
          <Waveform peaks={peaks} duration={project.audio.duration_sec} subscribe={subscribe} onSeek={seek} loop={tr?.loop ?? { enabled: false, a: 0, b: 0 }} />
          <div className="flex flex-wrap items-center gap-2">
            <button className="icon-btn" onClick={() => jumpBar(-1)} disabled={!tr} title="Bar sebelumnya" aria-label="Previous">⏮</button>
            <button className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-volt text-xl text-ink-950 disabled:opacity-40"
              onClick={() => tr?.toggle().catch((e) => setErr(`Audio tidak bisa diputar: ${e.message}`))} disabled={!tr} aria-label={tr?.playing ? "Pause" : "Play"}>
              {tr?.playing ? "❚❚" : "▶"}
            </button>
            <button className="icon-btn" onClick={() => tr?.stop()} disabled={!tr} title="Stop" aria-label="Stop">■</button>
            <button className="icon-btn" onClick={() => jumpBar(1)} disabled={!tr} title="Bar berikutnya" aria-label="Next">⏭</button>
            <span className="ml-1 font-mono text-sm tabular-nums"><span ref={timeLabel}>0:00.0</span> <span className="text-ink-400">/ {fmtTime(project.audio.duration_sec)}</span></span>
            <div className="ml-auto flex flex-wrap items-center gap-2">
              <select className="input w-auto py-2" value={tr?.rate ?? 1} onChange={(e) => tr?.setRate(Number(e.target.value))} aria-label="Kecepatan">
                {SPEEDS.map((r) => <option key={r} value={r}>{Math.round(r * 100)}%</option>)}
              </select>
              <label className="flex items-center gap-2 text-xs text-ink-400">Vol
                <input type="range" min={0} max={1} step={0.05} value={tr?.getVolume() ?? 1} onChange={(e) => tr?.setVolume(Number(e.target.value))} className="w-20 accent-[#39ff88]" />
              </label>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 border-t border-ink-800 pt-3 text-xs">
            <span className="text-ink-400">Loop:</span>
            <button className="btn-ghost px-3 py-1.5" disabled={!tr} onClick={() => tr && tr.setLoop(tr.loop.enabled, tr.time(), Math.max(tr.loop.b, tr.time() + 0.5))}>Set A {tr && tr.loop.b > tr.loop.a ? fmtTime(tr.loop.a) : ""}</button>
            <button className="btn-ghost px-3 py-1.5" disabled={!tr} onClick={() => tr && tr.setLoop(tr.loop.enabled, Math.min(tr.loop.a, tr.time()), tr.time())}>Set B {tr && tr.loop.b > tr.loop.a ? fmtTime(tr.loop.b) : ""}</button>
            <button className="btn-ghost px-3 py-1.5" disabled={!tr} onClick={loopBar}>Loop bar ini</button>
            <button className={`btn px-3 py-1.5 ${tr?.loop.enabled ? "bg-volt text-ink-950" : "border border-ink-600"}`} disabled={!tr || !(tr.loop.b > tr.loop.a)}
              onClick={() => tr?.setLoop(!tr.loop.enabled)}>{tr?.loop.enabled ? "Loop ON" : "Loop OFF"}</button>
            <label className="ml-auto flex items-center gap-1 text-ink-400" title="Geser visual bila pakai headset Bluetooth (latensi)">
              Sync offset
              <input type="number" step={10} className="input w-20 py-1" defaultValue={0} onChange={(e) => { if (tr) tr.userOffsetMs = Number(e.target.value) || 0; }} /> ms
            </label>
          </div>
        </div>
      ) : (
        <div className="card space-y-3">
          <p className="font-semibold">Proyek ini belum punya audio</p>
          <AudioDrop value={picked} onChange={setPicked} />
          {uploadPct !== null && <p className="text-sm text-ink-300">{uploadPct < 100 ? `Mengunggah ${uploadPct}%…` : "Memvalidasi di server…"}</p>}
          <button className="btn-primary" disabled={!picked || !!picked.error || !!picked.analyzing || uploadPct !== null} onClick={uploadHere}>Upload & validasi</button>
        </div>
      )}

      {project.audio && stems.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-ink-400">Dengarkan:</span>
          {[{ id: "original", label: "Lagu asli" }, ...stems.map((s) => ({ id: s.id, label: s.stem_type === "no_bass" ? "Tanpa bass" : s.label }))].map((o) => (
            <button key={o.id} onClick={() => setSource(o.id)}
              className={`rounded-full border px-3 py-1 text-xs font-semibold ${source === o.id ? "border-volt bg-volt text-ink-950" : "border-ink-600 text-ink-300"}`}>
              {o.label}
            </button>
          ))}
        </div>
      )}

      {/* view switch */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="inline-flex rounded-xl border border-ink-700 p-1">
          {([["tab", "Tab"], ["both", "Tab + Fretboard"], ["fretboard", "Fretboard"]] as [View, string][]).map(([v, l]) => (
            <button key={v} onClick={() => setView(v)} className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${view === v ? "bg-volt text-ink-950" : "text-ink-300"}`}>{l}</button>
          ))}
        </div>
        {view !== "fretboard" && (
          <>
            <button className="icon-btn h-8 w-8" onClick={() => setPps((p) => Math.max(40, p / 1.25))} aria-label="Zoom out">−</button>
            <button className="icon-btn h-8 w-8" onClick={() => setPps((p) => Math.min(480, p * 1.25))} aria-label="Zoom in">+</button>
            <label className="flex items-center gap-1.5 text-xs text-ink-300"><input type="checkbox" className="accent-[#39ff88]" checked={snap} onChange={(e) => setSnap(e.target.checked)} />Snap 1/16</label>
            <label className="flex items-center gap-1.5 text-xs text-ink-300"><input type="checkbox" className="accent-[#39ff88]" checked={autoScroll} onChange={(e) => setAutoScroll(e.target.checked)} />Auto-scroll</label>
          </>
        )}
        <span className="text-xs text-ink-400">{ed.notes.length} nada</span>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
        <div className="min-w-0 space-y-4">
          {view !== "fretboard" && (
            <TabView notes={ed.notes} measures={measures} tuning={tuning} duration={project.audio?.duration_sec ?? 0} pps={pps}
              subscribe={subscribe} selectedId={ed.selected} autoScroll={autoScroll}
              onSelect={(nid) => dispatch({ type: "select", id: nid })} onAdd={addNote} onSeek={seek} />
          )}
          {view !== "tab" && <Fretboard notes={ed.notes} tuning={tuning} subscribe={subscribe} />}
        </div>
        <div className="space-y-4">
          <ExtractorPanel project={project} onStemsChanged={(s) => { setStems(s); api<Project>(`/projects/${id}`).then(setProject).catch(() => {}); }} />
          <Inspector note={selected} tuning={tuning} grid={grid} onChange={update}
            onDelete={() => selected && dispatch({ type: "remove", id: selected.id })} onSeek={(t) => { seek(t); tr?.play(); }} />
          <SongSettings project={project} locked={ed.dirty} onSaved={async (p) => { setProject(p); const t = await api<Tab>(`/projects/${id}/tab`); setTab(t); dispatch({ type: "load", notes: t.notes }); }} />
        </div>
      </div>
    </div>
  );
}

function SongSettings({ project, locked, onSaved }: { project: Project; locked: boolean; onSaved: (p: Project) => void }) {
  const [f, setF] = useState({ name: project.name, bpm: project.bpm, sig: `${project.time_sig_num}/${project.time_sig_den}`, offset: project.offset_sec, tuning: project.tuning });
  const [msg, setMsg] = useState<string | null>(null);
  async function save() {
    const [num, den] = f.sig.split("/").map(Number);
    try {
      const p = await api<Project>(`/projects/${project.id}`, { method: "PATCH", body: json({ name: f.name, bpm: f.bpm, time_sig_num: num, time_sig_den: den, offset_sec: f.offset, tuning: f.tuning }) });
      onSaved(p);
      setMsg("Tersimpan.");
    } catch (e) { setMsg((e as Error).message); }
  }
  return (
    <details className="card">
      <summary className="cursor-pointer font-semibold">Pengaturan lagu (BPM, bar, tuning)</summary>
      <div className="mt-3 space-y-3">
        <div><label className="label">Nama</label><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
        <div className="grid grid-cols-2 gap-3">
          <div><label className="label">BPM</label><input type="number" step={0.1} min={20} max={320} className="input" value={f.bpm} onChange={(e) => setF({ ...f, bpm: Number(e.target.value) })} /></div>
          <div><label className="label">Birama</label>
            <select className="input" value={f.sig} onChange={(e) => setF({ ...f, sig: e.target.value })}>
              {["4/4", "3/4", "6/8", "2/4", "5/4", "7/8", "12/8"].map((s) => <option key={s}>{s}</option>)}
            </select>
          </div>
        </div>
        <div><label className="label">Bar 1 mulai di detik</label><input type="number" step={0.01} min={0} className="input" value={f.offset} onChange={(e) => setF({ ...f, offset: Number(e.target.value) })} /></div>
        <div><label className="label">Tuning</label><TuningPicker value={f.tuning} onChange={(t) => setF({ ...f, tuning: t })} /></div>
        {locked && <p className="text-xs text-warn">Simpan tab dulu sebelum mengubah pengaturan lagu.</p>}
        {msg && <p className="text-xs text-volt">{msg}</p>}
        <button className="btn-primary w-full" disabled={locked} onClick={save}>Simpan pengaturan</button>
      </div>
    </details>
  );
}
