import { describe, expect, it } from "vitest";
import type { Note } from "./api";
import { alternativePositions, editorReducer, initialEditor } from "./editor";

const n = (id: string, start: number, extra: Partial<Note> = {}): Note => ({
  id, string_number: 3, fret_number: 0, start_time: start, duration: 0.5, technique: "normal",
  confidence_score: 1, source: "manual", needs_review: false, ...extra,
});

describe("editor reducer", () => {
  it("add / update / remove with undo & redo", () => {
    let s = editorReducer(initialEditor, { type: "load", notes: [n("a", 1)] });
    s = editorReducer(s, { type: "add", note: n("b", 0.5) });
    expect(s.notes.map((x) => x.id)).toEqual(["b", "a"]); // kept sorted by time
    expect(s.selected).toBe("b");
    s = editorReducer(s, { type: "update", id: "b", patch: { start_time: 2, fret_number: 7 } });
    expect(s.notes.map((x) => x.id)).toEqual(["a", "b"]);
    s = editorReducer(s, { type: "remove", id: "a" });
    expect(s.notes).toHaveLength(1);
    s = editorReducer(s, { type: "undo" });
    s = editorReducer(s, { type: "undo" });
    expect(s.notes.find((x) => x.id === "b")!.fret_number).toBe(0);
    s = editorReducer(s, { type: "redo" });
    expect(s.notes.find((x) => x.id === "b")!.fret_number).toBe(7);
    expect(s.dirty).toBe(true);
    // a new edit clears redo
    s = editorReducer(s, { type: "add", note: n("c", 3) });
    expect(s.future).toHaveLength(0);
  });

  it("correcting an AI note clears needs_review", () => {
    let s = editorReducer(initialEditor, { type: "load", notes: [n("a", 0, { source: "ai", needs_review: true })] });
    s = editorReducer(s, { type: "update", id: "a", patch: { fret_number: 2 } });
    expect(s.notes[0].needs_review).toBe(false);
  });

  it("alternative positions for A1 on 4-string", () => {
    // string 1..4 open midi: G2=43, D2=38, A1=33, E1=28
    expect(alternativePositions([43, 38, 33, 28], 33)).toEqual([{ string: 3, fret: 0 }, { string: 4, fret: 5 }]);
  });
});
