"use client";
import { useEffect, useMemo, useState } from "react";
import type { Note } from "@/lib/api";
import { stringLabels } from "@/lib/music";
import type { Subscribe } from "./frame";

const INLAYS = [3, 5, 7, 9, 15, 17, 19, 21];

/** Real-time fingerboard: highlights the string/fret of every sounding note. */
export function Fretboard({ notes, tuning, subscribe }: { notes: Note[]; tuning: string[]; subscribe: Subscribe }) {
  const [active, setActive] = useState<string[]>([]);
  useEffect(() => {
    let prev = "";
    return subscribe((_t, set) => {
      const key = [...set].sort().join(",");
      if (key !== prev) { prev = key; setActive([...set]); }
    });
  }, [subscribe]);

  const byId = useMemo(() => new Map(notes.map((n) => [n.id, n])), [notes]);
  const maxFret = Math.max(12, Math.min(24, notes.reduce((m, n) => Math.max(m, n.fret_number), 0) + 1));
  const strings = tuning.length;
  const W = 900, NUT = 40, H = 28 + strings * 26;
  // classic fret spacing (rule of 18 approximated by 2^(1/12)), normalized to width
  const scale = (f: number) => (1 - Math.pow(2, -f / 12)) / (1 - Math.pow(2, -maxFret / 12));
  const fx = (f: number) => NUT + scale(f) * (W - NUT - 10);
  const sy = (s: number) => 14 + (s - 0.5) * 26;
  const labels = stringLabels(tuning);

  return (
    <div className="overflow-x-auto rounded-2xl border border-ink-700 bg-ink-950 p-2">
      <svg viewBox={`0 0 ${W} ${H}`} className="block min-w-[640px] w-full font-mono">
        <rect x={NUT} y={8} width={W - NUT - 10} height={H - 16} rx={4} fill="#1a1612" />
        {INLAYS.filter((f) => f <= maxFret).map((f) => <circle key={f} cx={(fx(f - 1) + fx(f)) / 2} cy={H / 2} r={5} fill="#3a332b" />)}
        {[12, 24].filter((f) => f <= maxFret).map((f) => (
          <g key={f}><circle cx={(fx(f - 1) + fx(f)) / 2} cy={H / 2 - 18} r={5} fill="#3a332b" /><circle cx={(fx(f - 1) + fx(f)) / 2} cy={H / 2 + 18} r={5} fill="#3a332b" /></g>
        ))}
        <rect x={NUT - 4} y={8} width={5} height={H - 16} fill="#d8d2c4" />
        {Array.from({ length: maxFret }, (_, i) => (
          <g key={i}>
            <line x1={fx(i + 1)} x2={fx(i + 1)} y1={8} y2={H - 8} stroke="#8a8f94" strokeWidth={2} />
            <text x={(fx(i) + fx(i + 1)) / 2} y={H - 1} fontSize={9} textAnchor="middle" fill="#7d868d">{i + 1}</text>
          </g>
        ))}
        {labels.map((l, i) => (
          <g key={i}>
            <line x1={NUT} x2={W - 10} y1={sy(i + 1)} y2={sy(i + 1)} stroke="#c9c2b0" strokeWidth={1 + i * 0.5} />
            <text x={12} y={sy(i + 1) + 4} fontSize={12} fontWeight={700} fill="#39ff88">{l}</text>
          </g>
        ))}
        {active.map((id) => {
          const n = byId.get(id);
          if (!n || n.string_number > strings) return null;
          const cx = n.fret_number === 0 ? NUT - 16 : (fx(n.fret_number - 1) + fx(n.fret_number)) / 2;
          return (
            <g key={id}>
              <circle cx={cx} cy={sy(n.string_number)} r={13} fill="#39ff88" opacity={0.25} />
              <circle cx={cx} cy={sy(n.string_number)} r={10} fill="#39ff88" />
              <text x={cx} y={sy(n.string_number) + 4} fontSize={11} fontWeight={800} textAnchor="middle" fill="#0b0c0d">{n.fret_number}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
