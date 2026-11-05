/**
 * SyncClock — the single source of truth for "where is the song right now".
 *
 * Audio is played by an HTMLMediaElement (so playback-rate changes keep pitch:
 * `preservesPitch`), routed through the Web Audio graph. Position is NOT read from
 * a timer: it is extrapolated from the AudioContext's hardware clock since the last
 * anchor point, then cross-checked against the media element's own position.
 *
 *   position = anchorMedia + (audioNow - anchorAudio) * rate
 *
 * - A late animation frame (browser lag) cannot make the playhead fall behind: the
 *   next frame computes the position from the audio clock, not by accumulating ticks.
 * - If the extrapolation and the media element disagree by more than DRIFT_LIMIT
 *   (buffer stall, decoder hiccup, tab throttling) we re-anchor to the element.
 * - Pause / seek / rate change / loop all re-anchor, so no drift accumulates.
 */
export interface ClockSource {
  /** Monotonic audio-hardware time in seconds (AudioContext). */
  audioNow(): number;
  /** Media element position in seconds. */
  mediaTime(): number;
}

export const DRIFT_LIMIT = 0.08; // s

export class SyncClock {
  private anchorMedia = 0;
  private anchorAudio = 0;
  private running = false;
  rate = 1;
  resyncs = 0;

  constructor(private src: ClockSource) {}

  get isRunning() { return this.running; }

  anchor(mediaTime = this.src.mediaTime()) {
    this.anchorMedia = mediaTime;
    this.anchorAudio = this.src.audioNow();
  }

  start(rate = this.rate) {
    this.rate = rate;
    this.running = true;
    this.anchor();
  }

  stop() {
    this.running = false;
    this.anchorMedia = this.src.mediaTime();
  }

  setRate(rate: number) {
    if (this.running) this.anchor(this.now());
    this.rate = rate;
  }

  /** Current song position in seconds. */
  now(): number {
    if (!this.running) return this.src.mediaTime();
    const predicted = this.anchorMedia + (this.src.audioNow() - this.anchorAudio) * this.rate;
    const media = this.src.mediaTime();
    if (Math.abs(predicted - media) > DRIFT_LIMIT * Math.max(1, this.rate)) {
      this.resyncs++;
      this.anchor(media);
      return media;
    }
    return predicted;
  }
}

/** Index of the last note whose start_time <= t (notes sorted by start). -1 if none. */
export function lastStartedIndex(starts: number[], t: number): number {
  let lo = 0, hi = starts.length - 1, ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (starts[mid] <= t) { ans = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return ans;
}

/** IDs of notes sounding at time t. `maxDur` bounds the backward scan. */
export function activeNoteIds(
  notes: { id: string; start_time: number; duration: number }[],
  starts: number[],
  t: number,
  maxDur: number,
): string[] {
  const out: string[] = [];
  for (let i = lastStartedIndex(starts, t); i >= 0 && t - notes[i].start_time <= maxDur; i--) {
    const n = notes[i];
    if (t < n.start_time + n.duration) out.push(n.id);
  }
  return out;
}
