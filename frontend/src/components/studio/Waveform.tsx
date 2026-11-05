"use client";
import { useEffect, useRef } from "react";
import type { Subscribe } from "./frame";

/** Overview waveform: click/drag to seek; shows playhead and loop region. */
export function Waveform({ peaks, duration, subscribe, onSeek, loop }: {
  peaks: number[] | null; duration: number; subscribe: Subscribe; onSeek: (t: number) => void;
  loop: { enabled: boolean; a: number; b: number };
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const head = useRef<HTMLDivElement>(null);
  const wrap = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const c = canvas.current;
    if (!c || !peaks) return;
    const draw = () => {
      const dpr = window.devicePixelRatio || 1;
      const w = c.clientWidth, h = c.clientHeight;
      c.width = w * dpr; c.height = h * dpr;
      const g = c.getContext("2d")!;
      g.scale(dpr, dpr);
      g.clearRect(0, 0, w, h);
      g.fillStyle = "#2bd36f";
      const max = Math.max(...peaks, 0.01);
      for (let x = 0; x < w; x++) {
        const p = peaks[Math.floor((x / w) * peaks.length)] / max;
        const bh = Math.max(1, p * (h - 4));
        g.fillRect(x, (h - bh) / 2, 0.8, bh);
      }
    };
    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(c);
    return () => ro.disconnect();
  }, [peaks]);

  useEffect(() => subscribe((t) => {
    if (head.current && duration > 0) head.current.style.transform = `translateX(${(t / duration) * (wrap.current?.clientWidth ?? 0)}px)`;
  }), [subscribe, duration]);

  function seekFromEvent(e: React.PointerEvent) {
    const r = wrap.current!.getBoundingClientRect();
    onSeek(Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) * duration);
  }

  return (
    <div ref={wrap} className="relative h-16 cursor-pointer touch-none select-none overflow-hidden rounded-xl bg-ink-850"
      onPointerDown={(e) => { (e.target as Element).setPointerCapture(e.pointerId); seekFromEvent(e); }}
      onPointerMove={(e) => e.buttons === 1 && seekFromEvent(e)}
      role="slider" aria-label="Posisi lagu" aria-valuemin={0} aria-valuemax={duration}>
      {peaks ? <canvas ref={canvas} className="h-full w-full opacity-70" /> : <div className="p-4 text-xs text-ink-400">Memuat waveform…</div>}
      {loop.enabled && duration > 0 && (
        <div className="pointer-events-none absolute inset-y-0 border-x border-volt bg-volt/10"
          style={{ left: `${(loop.a / duration) * 100}%`, width: `${((loop.b - loop.a) / duration) * 100}%` }} />
      )}
      <div ref={head} className="pointer-events-none absolute inset-y-0 left-0 w-0.5 bg-white shadow-[0_0_8px_#39ff88]" />
    </div>
  );
}
