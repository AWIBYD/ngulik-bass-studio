import { SyncClock } from "./clock";

export const SPEEDS = [0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 1];

type Listener = () => void;

/**
 * Playback engine: HTMLAudioElement (pitch-preserving rate) -> MediaElementSource -> Gain -> destination.
 * Timing comes from SyncClock (AudioContext clock), never from setInterval.
 */
export class Transport {
  readonly el: HTMLAudioElement;
  private ctx: AudioContext | null = null;
  private gain: GainNode | null = null;
  private volume = 1;
  readonly clock: SyncClock;
  loop = { enabled: false, a: 0, b: 0 };
  /** User-tunable visual offset (ms) for Bluetooth headsets etc. Positive = visuals later. */
  userOffsetMs = 0;
  private listeners = new Set<Listener>();
  private disposed = false;

  constructor(url: string) {
    const el = new Audio();
    el.preload = "auto";
    el.crossOrigin = "use-credentials";
    el.src = url;
    // pitch-preserving time stretch for slow practice
    const anyEl = el as HTMLAudioElement & { mozPreservesPitch?: boolean; webkitPreservesPitch?: boolean };
    anyEl.preservesPitch = true;
    anyEl.mozPreservesPitch = true;
    anyEl.webkitPreservesPitch = true;
    this.el = el;

    this.clock = new SyncClock({
      audioNow: () => this.audioNow(),
      mediaTime: () => this.el.currentTime,
    });

    const on = (ev: string, fn: () => void) => el.addEventListener(ev, () => { fn(); this.emit(); });
    on("playing", () => this.clock.start(el.playbackRate));
    on("waiting", () => this.clock.stop()); // buffering: freeze, do not run ahead
    on("pause", () => this.clock.stop());
    on("ended", () => this.clock.stop());
    on("seeked", () => this.clock.anchor());
    on("ratechange", () => this.clock.setRate(el.playbackRate));
    on("loadedmetadata", () => {});
    on("error", () => {});
  }

  private audioNow(): number {
    const ctx = this.ctx;
    if (!ctx) return performance.now() / 1000;
    const ts = ctx.getOutputTimestamp?.();
    if (ts && ts.contextTime !== undefined && ts.performanceTime !== undefined && ts.performanceTime > 0) {
      // smooth between render quanta: audio clock + elapsed wall time since that sample was output
      return ts.contextTime + (performance.now() - ts.performanceTime) / 1000;
    }
    return ctx.currentTime;
  }

  private async ensureGraph() {
    if (!this.ctx) {
      const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      this.ctx = new Ctx({ latencyHint: "interactive" });
      const src = this.ctx.createMediaElementSource(this.el);
      this.gain = this.ctx.createGain();
      this.gain.gain.value = this.volume;
      src.connect(this.gain).connect(this.ctx.destination);
    }
    if (this.ctx.state !== "running") await this.ctx.resume();
  }

  /** Output latency of the device, so visuals line up with what is heard. */
  get latencySec(): number {
    const c = this.ctx;
    if (!c) return 0;
    return (c.baseLatency || 0) + ((c as AudioContext & { outputLatency?: number }).outputLatency || 0);
  }

  get duration() { return Number.isFinite(this.el.duration) ? this.el.duration : 0; }
  get playing() { return !this.el.paused && !this.el.ended; }
  get rate() { return this.el.playbackRate; }

  /** Song time that is audible right now. Call every animation frame. */
  time(): number {
    let t = this.clock.now();
    if (this.clock.isRunning) t -= this.latencySec * this.el.playbackRate + this.userOffsetMs / 1000;
    if (this.loop.enabled && this.playing && this.loop.b > this.loop.a && this.el.currentTime >= this.loop.b) {
      this.seek(this.loop.a);
      return this.loop.a;
    }
    return Math.min(Math.max(t, 0), this.duration || t);
  }

  async play() {
    await this.ensureGraph();
    if (this.loop.enabled && (this.el.currentTime < this.loop.a || this.el.currentTime >= this.loop.b)) this.seek(this.loop.a);
    await this.el.play();
  }
  pause() { this.el.pause(); }
  stop() { this.el.pause(); this.seek(this.loop.enabled ? this.loop.a : 0); }
  async toggle() { if (this.playing) this.pause(); else await this.play(); }

  seek(t: number) {
    const d = this.duration;
    this.el.currentTime = Math.min(Math.max(0, t), d ? d - 0.001 : t);
    this.clock.anchor(this.el.currentTime);
    this.emit();
  }

  setRate(r: number) { this.el.playbackRate = r; this.emit(); }

  setVolume(v: number) {
    this.volume = v;
    if (this.gain) this.gain.gain.value = v;
    else this.el.volume = v;
    this.emit();
  }
  getVolume() { return this.volume; }

  setLoop(enabled: boolean, a = this.loop.a, b = this.loop.b) {
    this.loop = { enabled, a: Math.min(a, b), b: Math.max(a, b) };
    this.emit();
  }

  subscribe(fn: Listener) { this.listeners.add(fn); return () => { this.listeners.delete(fn); }; }
  private emit() { if (!this.disposed) this.listeners.forEach((f) => f()); }

  dispose() {
    this.disposed = true;
    this.el.pause();
    this.el.removeAttribute("src");
    this.el.load();
    this.ctx?.close();
    this.listeners.clear();
  }
}
