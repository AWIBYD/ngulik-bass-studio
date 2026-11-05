"use client";
import { useEffect, useState } from "react";
import { TuningPicker } from "@/components/TuningPicker";
import { api, json, type UserSettings } from "@/lib/api";
import { SPEEDS } from "@/lib/transport";

export default function Settings() {
  const [s, setS] = useState<UserSettings | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { api<UserSettings>("/settings").then(setS).catch((e) => setMsg(e.message)); }, []);

  async function save() {
    if (!s) return;
    try { setS(await api<UserSettings>("/settings", { method: "PUT", body: json(s) })); setMsg("Tersimpan."); }
    catch (e) { setMsg((e as Error).message); }
  }

  if (!s) return <p className="text-ink-400">{msg ?? "Memuat…"}</p>;
  return (
    <div className="mx-auto max-w-xl space-y-5">
      <div>
        <p className="text-xs font-semibold tracking-[0.2em] text-volt">SETTINGS</p>
        <h1 className="mt-1 text-2xl font-bold">Pengaturan</h1>
      </div>
      <div className="card space-y-4">
        <div><label className="label">Tuning default proyek baru</label><TuningPicker value={s.default_tuning} onChange={(t) => setS({ ...s, default_tuning: t })} /></div>
        <div>
          <label className="label" htmlFor="rate">Kecepatan default player</label>
          <select id="rate" className="input" value={s.default_playback_rate} onChange={(e) => setS({ ...s, default_playback_rate: Number(e.target.value) })}>
            {SPEEDS.map((r) => <option key={r} value={r}>{Math.round(r * 100)}%</option>)}
          </select>
        </div>
        <label className="flex items-center gap-3 text-sm">
          <input type="checkbox" className="h-4 w-4 accent-[#39ff88]" checked={s.auto_scroll} onChange={(e) => setS({ ...s, auto_scroll: e.target.checked })} />
          Auto-scroll tab mengikuti playhead
        </label>
        {msg && <p className="text-sm text-volt">{msg}</p>}
        <button className="btn-primary" onClick={save}>Simpan</button>
      </div>
    </div>
  );
}
