"""Rights-free synthetic bass audio with an exact answer key (for transcription accuracy tests)."""
import subprocess
from pathlib import Path

import numpy as np

SR = 44100


def pluck(freq: float, dur: float, vel: float = 0.8, seed: int = 0) -> np.ndarray:
    """Karplus-Strong plucked string: realistic attack, harmonics and decay like a bass string."""
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    period = SR / freq
    p = int(period)
    frac = period - p
    buf = rng.uniform(-1, 1, p) * vel
    # low-pass the excitation a bit (finger pluck, not pick)
    buf = np.convolve(buf, np.ones(4) / 4, mode="same")
    out = np.empty(n, dtype=np.float32)
    decay = 0.996
    idx = 0
    for i in range(n):
        out[i] = buf[idx]
        nxt = (idx + 1) % p
        buf[idx] = decay * ((1 - frac) * 0.5 * (buf[idx] + buf[nxt]) + frac * buf[nxt])
        idx = nxt
    # short release so notes end where they should (palm/fret release)
    rel = min(n, int(0.015 * SR))
    out[-rel:] *= np.linspace(1, 0, rel)
    return out


def render(notes: list[tuple[float, float, int]], total: float, path: Path, noise: float = 0.002,
           detune_cents: float = 0.0, bleed: float = 0.0) -> None:
    """notes: (start_s, duration_s, midi). detune/bleed simulate a real separated stem."""
    rng = np.random.default_rng(7)
    y = np.zeros(int(total * SR), dtype=np.float32)
    for k, (s, d, m) in enumerate(notes):
        cents = rng.uniform(-detune_cents, detune_cents)
        seg = pluck(440 * 2 ** ((m - 69 + cents / 100) / 12), d, 0.7 + 0.25 * ((k * 37) % 10) / 10, seed=k)
        a = int(s * SR)
        y[a:a + len(seg)] += seg[: len(y) - a]
    if bleed:
        t = np.arange(len(y)) / SR
        # leftover kick/snare hits every beat + a quiet vocal-like tone, as Demucs leaves behind
        for hit in np.arange(0.5, total, 0.6):
            a = int(hit * SR)
            burst = rng.normal(0, 1, int(0.05 * SR)) * np.exp(-np.linspace(0, 8, int(0.05 * SR)))
            y[a:a + burst.size] += (bleed * burst)[: len(y) - a]
        y += (bleed * 0.5 * np.sin(2 * np.pi * 330 * t) * (np.sin(2 * np.pi * 0.3 * t) > 0)).astype(np.float32)
    y += np.random.default_rng(1).normal(0, noise, len(y)).astype(np.float32)
    y /= np.max(np.abs(y)) * 1.05
    raw = np.repeat(y[:, None], 2, axis=1).astype(np.float32).tobytes()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", str(path)],
                   input=raw, check=True)


def groove(bpm: float = 100.0) -> list[tuple[float, float, int]]:
    """A 16-bar-ish bass line: roots, fifths, octaves, repeated 8ths, chromatic walk, low E/B range."""
    q = 60 / bpm
    e = q / 2
    pat = []
    t = 0.5
    bars = [
        [(28, e)] * 4 + [(35, e), (35, e), (33, e), (31, e)],            # E1 8ths, walk B1 A1 G1
        [(33, q), (40, e), (33, e), (38, q), (36, e), (37, e)],            # A1, E2 octave-ish, D2, C2, C#2
        [(38, e), (38, e), (45, e), (38, e), (43, q), (41, q)],            # D2 octave jumps, G2, F2
        [(31, q), (31, e), (38, e), (35, q), (40, q)],                     # G1 root/fifth
        [(29, e), (30, e), (31, e), (32, e), (33, q), (28, q)],            # chromatic F1..A1, E1
        [(45, e), (47, e), (48, e), (50, e), (52, q), (50, q)],            # higher register A2..E3
    ]
    for bar in bars:
        for m, d in bar:
            pat.append((round(t, 4), round(d * 0.92, 4), m))
            t += d
    return pat
