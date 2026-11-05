"use client";
import { useState } from "react";
import { noteToMidi, PRESETS } from "@/lib/music";

/** Tuning is low -> high, e.g. ["E1","A1","D2","G2"]. */
export function TuningPicker({ value, onChange }: { value: string[]; onChange: (t: string[]) => void }) {
  const key = value.join(",");
  const preset = PRESETS.find((p) => p.tuning.join(",") === key);
  const [custom, setCustom] = useState(!preset);
  const [text, setText] = useState(value.join(" "));
  const [err, setErr] = useState<string | null>(null);

  function applyCustom(s: string) {
    setText(s);
    const parts = s.trim().split(/[\s,-]+/).filter(Boolean);
    try {
      if (parts.length < 4 || parts.length > 6) throw new Error("Isi 4–6 nada, dari senar terendah. Contoh: D1 A1 D2 G2");
      parts.forEach(noteToMidi);
      setErr(null);
      onChange(parts.map((p) => p[0].toUpperCase() + p.slice(1)));
    } catch (e) { setErr((e as Error).message); }
  }

  return (
    <div className="space-y-2">
      <select className="input" value={custom ? "custom" : key}
        onChange={(e) => {
          if (e.target.value === "custom") { setCustom(true); setText(value.join(" ")); return; }
          setCustom(false); onChange(e.target.value.split(","));
        }}>
        {PRESETS.map((p) => <option key={p.label} value={p.tuning.join(",")}>{p.label}</option>)}
        <option value="custom">Custom tuning…</option>
      </select>
      {custom && (
        <>
          <input className="input font-mono" value={text} onChange={(e) => applyCustom(e.target.value)} placeholder="B0 E1 A1 D2 G2" />
          <p className={`text-xs ${err ? "text-bad" : "text-ink-400"}`}>{err ?? "Nada + oktaf, dari senar terendah ke tertinggi. # atau b diperbolehkan (mis. Eb1)."}</p>
        </>
      )}
    </div>
  );
}
