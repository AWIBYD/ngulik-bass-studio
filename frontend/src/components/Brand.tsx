export function Logo({ size = 28 }: { size?: number }) {
  // Four strings + one lit fret: a simple, original mark.
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <rect x="1" y="1" width="30" height="30" rx="8" fill="#16191b" stroke="#39ff88" strokeOpacity=".5" />
      {[9, 14, 19, 24].map((y) => (
        <line key={y} x1="6" x2="26" y1={y} y2={y} stroke="#7d868d" strokeWidth={y === 24 ? 2 : 1.4} />
      ))}
      <circle cx="18" cy="14" r="3.2" fill="#39ff88" />
    </svg>
  );
}

export function Wordmark() {
  return (
    <div className="flex items-center gap-2.5">
      <Logo />
      <div className="leading-tight">
        <div className="text-sm font-black tracking-[0.18em]">NGULIK <span className="text-volt">BASS</span></div>
        <div className="text-[10px] font-semibold tracking-[0.3em] text-ink-400">STUDIO</div>
      </div>
    </div>
  );
}

export const TAGLINE = "FEEL THE GROOVE. READ THE NOTES.";
