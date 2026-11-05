import type { Note } from "./api";

export type EditorState = {
  notes: Note[];          // always sorted by start_time
  past: Note[][];
  future: Note[][];
  selected: string | null;
  dirty: boolean;
};

export type EditorAction =
  | { type: "load"; notes: Note[] }
  | { type: "saved"; notes: Note[] }
  | { type: "add"; note: Note }
  | { type: "update"; id: string; patch: Partial<Note> }
  | { type: "remove"; id: string }
  | { type: "select"; id: string | null }
  | { type: "undo" }
  | { type: "redo" };

const HISTORY = 200;
const sort = (ns: Note[]) => [...ns].sort((a, b) => a.start_time - b.start_time || a.string_number - b.string_number);

export const initialEditor: EditorState = { notes: [], past: [], future: [], selected: null, dirty: false };

function commit(s: EditorState, notes: Note[], selected = s.selected): EditorState {
  return { notes: sort(notes), past: [...s.past, s.notes].slice(-HISTORY), future: [], selected, dirty: true };
}

export function editorReducer(s: EditorState, a: EditorAction): EditorState {
  switch (a.type) {
    case "load":
      return { ...initialEditor, notes: sort(a.notes) };
    case "saved": // server copy replaces local, history kept (ids are stable)
      return { ...s, notes: sort(a.notes), dirty: false };
    case "add":
      return commit(s, [...s.notes, a.note], a.note.id);
    case "update": {
      if (!s.notes.some((n) => n.id === a.id)) return s;
      // user corrections clear the "needs review" flag of AI notes
      return commit(s, s.notes.map((n) => (n.id === a.id ? { ...n, ...a.patch, needs_review: false } : n)));
    }
    case "remove":
      return commit(s, s.notes.filter((n) => n.id !== a.id), s.selected === a.id ? null : s.selected);
    case "select":
      return { ...s, selected: a.id };
    case "undo": {
      if (!s.past.length) return s;
      const prev = s.past[s.past.length - 1];
      return { ...s, notes: prev, past: s.past.slice(0, -1), future: [s.notes, ...s.future], dirty: true,
        selected: prev.some((n) => n.id === s.selected) ? s.selected : null };
    }
    case "redo": {
      if (!s.future.length) return s;
      const next = s.future[0];
      return { ...s, notes: next, past: [...s.past, s.notes], future: s.future.slice(1), dirty: true,
        selected: next.some((n) => n.id === s.selected) ? s.selected : null };
    }
  }
}

export const newId = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (c) =>
        (+c ^ (Math.random() * 16) >> (+c / 4)).toString(16));

/** Same pitch on other strings (fret 0..24) — lets the user pick an alternative position. */
export function alternativePositions(tuningMidiByString: number[], midi: number): { string: number; fret: number }[] {
  const out: { string: number; fret: number }[] = [];
  tuningMidiByString.forEach((open, i) => {
    const fret = midi - open;
    if (fret >= 0 && fret <= 24) out.push({ string: i + 1, fret });
  });
  return out;
}
