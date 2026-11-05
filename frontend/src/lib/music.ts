// Mirrors backend/app/services/music.py. string 1 = highest string (top line of the tab).
export const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const FLATS: Record<string, string> = { Db: "C#", Eb: "D#", Gb: "F#", Ab: "G#", Bb: "A#" };

export const PRESETS: { label: string; tuning: string[] }[] = [
  { label: "4 senar E-A-D-G", tuning: ["E1", "A1", "D2", "G2"] },
  { label: "5 senar B-E-A-D-G", tuning: ["B0", "E1", "A1", "D2", "G2"] },
  { label: "6 senar B-E-A-D-G-C", tuning: ["B0", "E1", "A1", "D2", "G2", "C3"] },
  { label: "Drop D (D-A-D-G)", tuning: ["D1", "A1", "D2", "G2"] },
];

export function noteToMidi(name: string): number {
  const m = /^([A-Ga-g])([#b]?)(-?\d)$/.exec(name.trim());
  if (!m) throw new Error(`Nada tidak valid: ${name}`);
  let pc = m[1].toUpperCase() + m[2];
  pc = FLATS[pc] ?? pc;
  const i = NOTE_NAMES.indexOf(pc);
  if (i < 0) throw new Error(`Nada tidak valid: ${name}`);
  return (Number(m[3]) + 1) * 12 + i;
}

export const midiToNote = (m: number) => `${NOTE_NAMES[m % 12]}${Math.floor(m / 12) - 1}`;

export function stringOpenMidi(tuning: string[], stringNumber: number): number {
  return noteToMidi(tuning[tuning.length - stringNumber]);
}

export const pitchOf = (tuning: string[], s: number, fret: number) => midiToNote(stringOpenMidi(tuning, s) + fret);

/** Display label for a string, e.g. "G" (no octave), top to bottom order. */
export const stringLabels = (tuning: string[]) => [...tuning].reverse().map((n) => n.replace(/-?\d$/, ""));

export function barDuration(bpm: number, num: number, den: number) {
  return num * (60 / bpm) * (4 / den);
}

/** Grid step in seconds: BPM counts quarter notes; division 4 = 1/16 notes. */
export const gridStep = (bpm: number, division = 4) => 60 / bpm / division;

/** Snap a time to the grid, anchored at the bar-1 offset. */
export function snapTime(t: number, bpm: number, offset: number, division = 4) {
  const s = gridStep(bpm, division);
  return Math.max(0, +(offset + Math.round((t - offset) / s) * s).toFixed(6));
}

export const TECHNIQUES: { value: string; label: string; mark: string }[] = [
  { value: "normal", label: "Normal", mark: "" },
  { value: "hammer_on", label: "Hammer-on", mark: "h" },
  { value: "pull_off", label: "Pull-off", mark: "p" },
  { value: "slide_up", label: "Slide naik", mark: "/" },
  { value: "slide_down", label: "Slide turun", mark: "\\" },
  { value: "ghost", label: "Ghost note", mark: "()" },
  { value: "slap", label: "Slap", mark: "T" },
  { value: "pop", label: "Pop", mark: "P" },
  { value: "mute", label: "Muted", mark: "x" },
  { value: "bend", label: "Bend", mark: "b" },
  { value: "vibrato", label: "Vibrato", mark: "~" },
];
