"use client";
import { useEffect, useRef, useState } from "react";
import { fmtSize, fmtTime } from "./AppShell";

export const ACCEPT = ".mp3,.wav,.flac,.m4a,audio/mpeg,audio/wav,audio/flac,audio/mp4,audio/x-m4a";
const EXT = ["mp3", "wav", "flac", "m4a"];
const MAX_MB = Number(process.env.NEXT_PUBLIC_MAX_UPLOAD_MB || 50);

export type Picked = { file: File; duration: number | null; peaks: number[] | null; error: string | null; warning?: string; analyzing?: boolean };

/** Drag & drop + file browser with local preview (duration, size, waveform, player). */
export function AudioDrop({ value, onChange }: { value: Picked | null; onChange: (p: Picked | null) => void }) {
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!value) return setUrl(null);
    const u = URL.createObjectURL(value.file);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [value?.file]); // eslint-disable-line react-hooks/exhaustive-deps

  async function pick(file: File | undefined) {
    if (!file) return;
    const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
    let error: string | null = null;
    if (!EXT.includes(ext)) error = `Format .${ext} tidak didukung. Gunakan MP3, WAV, FLAC, atau M4A.`;
    else if (file.size === 0) error = "File kosong.";
    else if (file.size > MAX_MB * 1024 * 1024) error = `File ${fmtSize(file.size)} melebihi batas ${MAX_MB} MB.`;
    onChange({ file, duration: null, peaks: null, error, analyzing: !error });
    if (error) return;
    try {
      const buf = await file.arrayBuffer();
      const ctx = new OfflineAudioContext(1, 1, 44100);
      const audio = await ctx.decodeAudioData(buf);
      const ch = audio.getChannelData(0);
      const N = 400, step = Math.max(1, Math.floor(ch.length / N));
      const peaks: number[] = [];
      for (let i = 0; i < N; i++) {
        let m = 0;
        for (let j = i * step, e = Math.min(ch.length, j + step); j < e; j += 8) m = Math.max(m, Math.abs(ch[j]));
        peaks.push(m);
      }
      onChange({ file, duration: audio.duration, peaks, error: null });
    } catch {
      onChange({ file, duration: null, peaks: null, error: null, warning: "Browser ini tidak bisa membuat preview file ini. Server tetap akan memvalidasi; jika rusak, upload akan ditolak." });
    }
  }

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files[0]); }}
        onClick={() => input.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed p-8 text-center transition ${over ? "border-volt bg-volt/5" : "border-ink-600 hover:border-ink-400"}`}
      >
        <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#39ff88" strokeWidth="1.6"><path d="M12 16V4m0 0l-4 4m4-4l4 4M4 16v3h16v-3" /></svg>
        <p className="mt-3 font-semibold">Tarik & lepas lagu di sini</p>
        <p className="text-sm text-ink-400">atau ketuk untuk pilih file · MP3, WAV, FLAC, M4A · maks {MAX_MB} MB</p>
        <input ref={input} type="file" accept={ACCEPT} className="hidden" onChange={(e) => pick(e.target.files?.[0])} />
      </div>
      {value && (
        <div className="rounded-2xl border border-ink-700 bg-ink-850 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span className="truncate font-medium">{value.file.name}</span>
            <span className="text-ink-400">{fmtSize(value.file.size)}{value.duration != null && ` · ${fmtTime(value.duration)}`}</span>
          </div>
          {value.error && <p className="mt-2 text-sm text-bad">{value.error}</p>}
          {value.warning && <p className="mt-2 text-sm text-warn">{value.warning}</p>}
          {value.peaks && (
            <svg viewBox={`0 0 ${value.peaks.length} 60`} preserveAspectRatio="none" className="mt-3 h-14 w-full">
              {value.peaks.map((p, i) => <rect key={i} x={i} width={0.7} y={30 - p * 28} height={Math.max(0.5, p * 56)} fill="#39ff88" opacity={0.8} />)}
            </svg>
          )}
          {url && !value.error && <audio controls src={url} className="mt-3 w-full" />}
          {value.analyzing && <p className="mt-2 text-xs text-ink-400">Menganalisis file…</p>}
        </div>
      )}
    </div>
  );
}
