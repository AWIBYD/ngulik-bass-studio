import { describe, expect, it } from "vitest";
import { activeNoteIds, DRIFT_LIMIT, lastStartedIndex, SyncClock } from "./clock";
import { noteToMidi, pitchOf, snapTime } from "./music";

/** Fake hardware: an audio clock and a media element that advances with it. */
function rig() {
  const s = { audio: 0, media: 0 };
  const clock = new SyncClock({ audioNow: () => s.audio, mediaTime: () => s.media });
  const advance = (dt: number, rate = 1) => { s.audio += dt; s.media += dt * rate; };
  return { s, clock, advance };
}

describe("SyncClock", () => {
  it("follows the audio clock while playing", () => {
    const { clock, advance } = rig();
    clock.start(1);
    advance(1.234);
    expect(clock.now()).toBeCloseTo(1.234, 6);
  });

  it("does not fall behind after a long browser stall (frames skipped)", () => {
    const { clock, advance } = rig();
    clock.start(1);
    for (let i = 0; i < 10; i++) advance(0.016);
    advance(0.75); // 750 ms without any animation frame
    expect(clock.now()).toBeCloseTo(0.16 + 0.75, 6);
  });

  it("honours playback rate", () => {
    const { clock, advance } = rig();
    clock.start(0.5);
    advance(2, 0.5);
    expect(clock.now()).toBeCloseTo(1, 6);
    clock.setRate(0.75);
    advance(2, 0.75);
    expect(clock.now()).toBeCloseTo(2.5, 6);
  });

  it("freezes on pause and resumes from the same spot", () => {
    const { s, clock, advance } = rig();
    clock.start(1);
    advance(3);
    clock.stop();
    s.audio += 10; // wall time passes while paused, media does not move
    expect(clock.now()).toBeCloseTo(3, 6);
    clock.start(1);
    advance(1);
    expect(clock.now()).toBeCloseTo(4, 6);
  });

  it("re-anchors on seek", () => {
    const { s, clock, advance } = rig();
    clock.start(1);
    advance(5);
    s.media = 42;
    clock.anchor();
    advance(0.5);
    expect(clock.now()).toBeCloseTo(42.5, 6);
  });

  it("corrects drift when media and clock disagree (e.g. decoder stall)", () => {
    const { s, clock, advance } = rig();
    clock.start(1);
    advance(2);
    s.audio += 0.5; // audio clock ran, media stuck
    expect(clock.now()).toBeCloseTo(2, 6);
    expect(clock.resyncs).toBe(1);
  });

  it("ignores tiny jitter below the drift limit", () => {
    const { s, clock, advance } = rig();
    clock.start(1);
    advance(1);
    s.media += DRIFT_LIMIT / 2;
    expect(clock.now()).toBeCloseTo(1, 6);
    expect(clock.resyncs).toBe(0);
  });
});

describe("note lookup", () => {
  const notes = [
    { id: "a", start_time: 0, duration: 0.5 },
    { id: "b", start_time: 0.5, duration: 1.5 },
    { id: "c", start_time: 1.0, duration: 0.25 },
    { id: "d", start_time: 3.0, duration: 0.5 },
  ];
  const starts = notes.map((n) => n.start_time);
  it("binary search", () => {
    expect(lastStartedIndex(starts, -1)).toBe(-1);
    expect(lastStartedIndex(starts, 1.1)).toBe(2);
    expect(lastStartedIndex(starts, 99)).toBe(3);
  });
  it("active notes incl. overlapping", () => {
    expect(activeNoteIds(notes, starts, 1.1, 2).sort()).toEqual(["b", "c"]);
    expect(activeNoteIds(notes, starts, 2.5, 2)).toEqual([]);
    expect(activeNoteIds(notes, starts, 0.5, 2)).toEqual(["b"]);
  });
});

describe("music", () => {
  it("pitch from string/fret", () => {
    const t = ["E1", "A1", "D2", "G2"];
    expect(pitchOf(t, 4, 0)).toBe("E1");
    expect(pitchOf(t, 3, 5)).toBe("D2");
    expect(pitchOf(["B0", "E1", "A1", "D2", "G2", "C3"], 1, 0)).toBe("C3");
    expect(noteToMidi("Bb1")).toBe(noteToMidi("A#1"));
  });
  it("snaps to 1/16 grid at 120 bpm with offset", () => {
    expect(snapTime(0.13, 120, 0, 4)).toBeCloseTo(0.125, 6);
    expect(snapTime(1.06, 120, 0.1, 4)).toBeCloseTo(1.1, 6);
  });
});
