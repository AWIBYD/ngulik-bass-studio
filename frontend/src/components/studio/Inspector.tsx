"use client";
import type { Note, Technique } from "@/lib/api";
import { alternativePositions } from "@/lib/editor";
import { pitchOf, stringLabels, stringOpenMidi, TECHNIQUES } from "@/lib/music";

/** Edit panel for the selected note. Every change goes through the editor reducer (undoable). */
export function Inspector({ note, tuning, grid, onChange, onDelete, onSeek }: {
  note: Note | null; tuning: string[]; grid: number;
  onChange: (patch: Partial<Note>) => void; onDelete: () => void; onSeek: (t: number) => void;
}) {
  if (!note) {
    return (
      <div className="card text-sm text-ink-400">
        <p className="font-semibold text-ink-100">Editor tab</p>
        <ul className="mt-2 list-disc space-y-1 pl-4">
          <li>Ketuk garis senar untuk menambah nada (snap ke grid 1/16).</li>
          <li>Ketuk nada untuk memilih & mengedit.</li>
          <li>Keyboard: angka = fret, ←/→ geser waktu, ↑/↓ pindah senar, Del hapus, Ctrl+Z/Ctrl+Y undo/redo, Ctrl+S simpan, Spasi play/pause.</li>
        </ul>
      </div>
    );
  }
  const labels = stringLabels(tuning);
  const opens = tuning.map((_, i) => stringOpenMidi(tuning, i + 1));
  const midi = stringOpenMidi(tuning, note.string_number) + note.fret_number;
  const alts = alternativePositions(opens, midi).filter((a) => a.string !== note.string_number);
  const num = (v: string, f: (n: number) => void) => { const n = Number(v); if (Number.isFinite(n)) f(n); };

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs text-ink-400">Nada terpilih</div>
          <div className="font-mono text-2xl font-bold text-volt">{pitchOf(tuning, note.string_number, note.fret_number)}</div>
        </div>
        <div className="text-right text-xs text-ink-400">
          <div>sumber: {note.source === "ai" ? "AI" : "manual"}</div>
          <div>confidence: {Math.round(note.confidence_score * 100)}%</div>
          {note.needs_review && <div className="text-warn">perlu dicek</div>}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label" htmlFor="ins-s">Senar</label>
          <select id="ins-s" className="input" value={note.string_number} onChange={(e) => onChange({ string_number: Number(e.target.value) })}>
            {labels.map((l, i) => <option key={i} value={i + 1}>{i + 1} · {l}</option>)}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="ins-f">Fret</label>
          <input id="ins-f" type="number" min={0} max={24} className="input" value={note.fret_number}
            onChange={(e) => num(e.target.value, (n) => onChange({ fret_number: Math.min(24, Math.max(0, Math.round(n))) }))} />
        </div>
        <div>
          <label className="label" htmlFor="ins-t">Mulai (detik)</label>
          <input id="ins-t" type="number" min={0} step={grid} className="input" value={+note.start_time.toFixed(4)}
            onChange={(e) => num(e.target.value, (n) => onChange({ start_time: Math.max(0, n) }))} />
        </div>
        <div>
          <label className="label" htmlFor="ins-d">Durasi (detik)</label>
          <input id="ins-d" type="number" min={0.01} step={grid} className="input" value={+note.duration.toFixed(4)}
            onChange={(e) => num(e.target.value, (n) => n > 0 && onChange({ duration: n }))} />
        </div>
        <div className="col-span-2">
          <label className="label" htmlFor="ins-tech">Teknik</label>
          <select id="ins-tech" className="input" value={note.technique} onChange={(e) => onChange({ technique: e.target.value as Technique })}>
            {TECHNIQUES.map((t) => <option key={t.value} value={t.value}>{t.label}{t.mark && ` (${t.mark})`}</option>)}
          </select>
        </div>
      </div>
      {alts.length > 0 && (
        <div>
          <div className="label">Posisi lain untuk nada ini</div>
          <div className="flex flex-wrap gap-2">
            {alts.map((a) => (
              <button key={a.string} className="btn-ghost px-3 py-1.5 font-mono"
                onClick={() => onChange({ string_number: a.string, fret_number: a.fret })}>
                {labels[a.string - 1]} fret {a.fret}
              </button>
            ))}
          </div>
        </div>
      )}
      <div className="flex gap-2">
        <button className="btn-ghost flex-1" onClick={() => onSeek(note.start_time)}>Putar dari sini</button>
        <button className="btn-danger" onClick={onDelete}>Hapus</button>
      </div>
    </div>
  );
}
