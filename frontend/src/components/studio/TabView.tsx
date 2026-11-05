"use client";
import { memo, useEffect, useRef } from "react";
import type { Measure, Note } from "@/lib/api";
import { stringLabels, TECHNIQUES } from "@/lib/music";
import type { Subscribe } from "./frame";

const TOP = 34, LANE = 30, BOTTOM = 14, PADL = 44;
const MARK: Record<string, string> = Object.fromEntries(TECHNIQUES.map((t) => [t.value, t.mark]));

type Props = {
  notes: Note[]; measures: Measure[]; tuning: string[]; duration: number; pps: number;
  subscribe: Subscribe; selectedId: string | null; autoScroll: boolean;
  onSelect: (id: string | null) => void; onAdd: (t: number, string: number) => void; onSeek: (t: number) => void;
};

/** Horizontal bass tablature (SVG) on the same seconds timeline as the audio. */
export function TabView(p: Props) {
  const { notes, measures, tuning, duration, pps, subscribe, selectedId, autoScroll } = p;
  const scroller = useRef<HTMLDivElement>(null);
  const head = useRef<SVGGElement>(null);
  const noteEls = useRef(new Map<string, SVGGElement>());
  const lit = useRef(new Set<string>());
  const autoRef = useRef(autoScroll);
  autoRef.current = autoScroll;

  const strings = tuning.length;
  const lastEnd = notes.reduce((m, n) => Math.max(m, n.start_time + n.duration), 0);
  const total = Math.max(duration, lastEnd, measures.length ? measures[measures.length - 1].start_time + measures[measures.length - 1].duration : 0, 4);
  const width = PADL + total * pps + 40;
  const height = TOP + strings * LANE + BOTTOM;
  const laneY = (s: number) => TOP + (s - 0.5) * LANE;
  const x = (t: number) => PADL + t * pps;

  useEffect(() => subscribe((t, active, playing) => {
    const px = x(t);
    head.current?.setAttribute("transform", `translate(${px},0)`);
    // highlight diff only
    lit.current.forEach((id) => { if (!active.has(id)) { noteEls.current.get(id)?.setAttribute("data-active", "0"); lit.current.delete(id); } });
    active.forEach((id) => { if (!lit.current.has(id)) { noteEls.current.get(id)?.setAttribute("data-active", "1"); lit.current.add(id); } });
    const sc = scroller.current;
    if (sc && autoRef.current) {
      const w = sc.clientWidth;
      if (playing) {
        const target = px - w * 0.3;
        if (Math.abs(sc.scrollLeft - target) > 1) sc.scrollLeft = target;
      } else if (px < sc.scrollLeft || px > sc.scrollLeft + w) {
        sc.scrollLeft = px - w * 0.3;
      }
    }
  }), [subscribe, pps]); // eslint-disable-line react-hooks/exhaustive-deps

  // re-apply highlight after notes re-render
  useEffect(() => { lit.current.forEach((id) => noteEls.current.get(id)?.setAttribute("data-active", "1")); }, [notes]);

  function pointToTimeString(e: React.MouseEvent) {
    const svg = e.currentTarget.closest("svg")!;
    const r = svg.getBoundingClientRect();
    const t = (e.clientX - r.left - PADL) / pps;
    const s = Math.floor((e.clientY - r.top - TOP) / LANE) + 1;
    return { t: Math.max(0, t), s };
  }

  const labels = stringLabels(tuning);

  return (
    <div className="relative rounded-2xl border border-ink-700 bg-ink-950">
      <div ref={scroller} className="overflow-x-auto overscroll-x-contain" style={{ scrollbarColor: "#363c41 transparent" }}>
        <svg width={width} height={height} className="block select-none font-mono" data-testid="tab-svg">
          {/* ruler: click to seek */}
          <rect x={0} y={0} width={width} height={TOP - 6} fill="#111315" className="cursor-pointer"
            onClick={(e) => p.onSeek(pointToTimeString(e).t)} />
          {/* lane hit areas: click to add a note */}
          {Array.from({ length: strings }, (_, i) => (
            <rect key={i} x={PADL} y={TOP + i * LANE} width={width - PADL} height={LANE} fill="transparent" className="cursor-crosshair"
              onClick={(e) => { const { t, s } = pointToTimeString(e); p.onAdd(t, Math.min(strings, Math.max(1, s))); }} />
          ))}
          {measures.map((m) => {
            const beats = m.time_sig_num, bd = m.duration / beats;
            return (
              <g key={m.index} pointerEvents="none">
                <line x1={x(m.start_time)} x2={x(m.start_time)} y1={laneY(1)} y2={laneY(strings)} stroke="#7d868d" strokeWidth={1.4} />
                <text x={x(m.start_time) + 4} y={14} fontSize={10} fill="#a9b1b7">{m.index + 1}</text>
                {m.index === 0 && <text x={x(m.start_time) + 4} y={TOP - 10} fontSize={9} fill="#39ff88">{m.time_sig_num}/{m.time_sig_den} ♩={Math.round(m.bpm)}</text>}
                {Array.from({ length: beats - 1 }, (_, b) => (
                  <line key={b} x1={x(m.start_time + (b + 1) * bd)} x2={x(m.start_time + (b + 1) * bd)} y1={TOP} y2={TOP + strings * LANE}
                    stroke="#262b2f" strokeDasharray="2 4" />
                ))}
              </g>
            );
          })}
          {Array.from({ length: strings }, (_, i) => (
            <line key={i} x1={PADL - 6} x2={width} y1={laneY(i + 1)} y2={laneY(i + 1)} stroke="#4a5157" strokeWidth={1 + i * 0.25} pointerEvents="none" />
          ))}
          {notes.map((n) => (
            <NoteGlyph key={n.id} n={n} x={x(n.start_time)} w={n.duration * pps} y={laneY(n.string_number)} selected={n.id === selectedId}
              register={(el) => { if (el) noteEls.current.set(n.id, el); else noteEls.current.delete(n.id); }}
              onSelect={p.onSelect} />
          ))}
          <g ref={head} pointerEvents="none" data-testid="playhead">
            <line x1={0} x2={0} y1={0} y2={height} stroke="#ffffff" strokeWidth={2} />
            <line x1={0} x2={0} y1={0} y2={height} stroke="#39ff88" strokeWidth={8} opacity={0.15} />
          </g>
        </svg>
      </div>
      {/* sticky string names */}
      <div className="pointer-events-none absolute left-0 top-0 w-9 rounded-l-2xl bg-gradient-to-r from-ink-950 via-ink-950/90 to-transparent" style={{ height }}>
        {labels.map((l, i) => (
          <div key={i} className="absolute left-2 font-mono text-xs font-bold text-volt" style={{ top: laneY(i + 1) - 8 }}>{l}</div>
        ))}
      </div>
    </div>
  );
}

const NoteGlyph = memo(function NoteGlyph({ n, x, w, y, selected, register, onSelect }: {
  n: Note; x: number; w: number; y: number; selected: boolean;
  register: (el: SVGGElement | null) => void; onSelect: (id: string) => void;
}) {
  const label = n.technique === "ghost" ? `(${n.fret_number})` : n.technique === "mute" ? "x" : String(n.fret_number);
  const bw = Math.max(16, label.length * 8 + 6);
  const mark = n.technique !== "ghost" && n.technique !== "mute" ? MARK[n.technique] : "";
  return (
    <g ref={register} data-note-id={n.id} data-start={n.start_time} className="tab-note cursor-pointer" data-selected={selected ? "1" : "0"} data-review={n.needs_review ? "1" : "0"}
      onClick={(e) => { e.stopPropagation(); onSelect(n.id); }}>
      <rect x={x} y={y - 1.5} width={Math.max(2, w)} height={3} fill="#39ff88" opacity={0.25} />
      <rect className="box" x={x - 2} y={y - 10} width={bw} height={20} rx={5} />
      <text x={x - 2 + bw / 2} y={y + 4} fontSize={13} fontWeight={700} textAnchor="middle">{label}</text>
      {mark && <text x={x - 2 + bw / 2} y={y - 13} fontSize={10} fill="#39ff88" textAnchor="middle" style={{ fill: "#39ff88" }}>{mark}</text>}
    </g>
  );
});
