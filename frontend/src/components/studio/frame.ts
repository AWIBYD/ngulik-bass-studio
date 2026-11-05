/** Per-animation-frame broadcast of the audio-clock position and the set of sounding notes. */
export type FrameFn = (t: number, active: ReadonlySet<string>, playing: boolean) => void;
export type Subscribe = (fn: FrameFn) => () => void;
