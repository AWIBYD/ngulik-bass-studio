"""Bass transcription: audio -> list of notes with timing, pitch, confidence and technique guesses.

Worker-only (needs librosa; CREPE mode also needs torch + torchcrepe).

Pipeline
1. Decode the bass stem to mono 11.025 kHz (bass lives far below 5 kHz; 4x less work).
2. Frame-level f0 with pYIN (default) or CREPE, plus voicing probability.
3. Onset detection (attacks) so repeated notes of the same pitch are split correctly.
4. Segment frames into notes: stable semitone + voiced, split on onsets / pitch changes,
   bridge tiny unvoiced gaps, drop blips shorter than MIN_NOTE.
5. Per note: median pitch, confidence (voicing x pitch stability), velocity (RMS),
   heuristics for hammer-on / pull-off / slide / vibrato / dead notes.
6. Anything uncertain is FLAGGED (needs_review) instead of being guessed silently.
"""
from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass, field

import numpy as np

from ..config import get_settings

SR = 11025
HOP = 128                      # 11.6 ms
FRAME = 2048                   # 186 ms: resolves the low B (30.9 Hz)
MIN_NOTE = 0.045               # s
GAP_BRIDGE = 3                 # frames of unvoiced allowed inside a note
REVIEW_BELOW = 0.55            # confidence threshold for "needs review"


@dataclass
class DetNote:
    start: float
    duration: float
    midi: int
    frequency: float
    confidence: float
    velocity: float
    technique: str = "normal"
    needs_review: bool = False
    reasons: list[str] = field(default_factory=list)


@dataclass
class Analysis:
    notes: list[DetNote]
    bpm: float | None
    bpm_confidence: float
    first_beat: float | None
    method: str


def load_mono(path: str, sr: int = SR) -> np.ndarray:
    s = get_settings()
    r = subprocess.run([s.ffmpeg_bin, "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"],
                       capture_output=True, timeout=900)
    if r.returncode != 0:
        raise RuntimeError("Gagal membaca audio: " + r.stderr.decode(errors="ignore")[-300:])
    return np.frombuffer(r.stdout, dtype=np.float32).copy()


def hz_to_midi(f: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return 69 + 12 * np.log2(f / 440.0)


def pitch_track(y: np.ndarray, method: str, fmin: float, fmax: float, on_progress=None):
    """Returns (midi_float[frames], voiced_prob[frames]) on the HOP grid at SR. NaN = unvoiced."""
    import librosa

    n_frames = 1 + len(y) // HOP
    if method == "crepe":
        crepe_model = "full"  # "tiny" was measured unusable on bass (F1 0.15)
        import torch
        import torchcrepe
        sr_c, hop_c = 16000, 160
        y16 = librosa.resample(y, orig_sr=SR, target_sr=sr_c)
        audio = torch.from_numpy(y16)[None]
        pitch, periodicity = torchcrepe.predict(audio, sr_c, hop_c, max(fmin, 32.0), fmax, crepe_model,
                                                return_periodicity=True, batch_size=512, device="cpu",
                                                pad=True)
        periodicity = torchcrepe.filter.median(periodicity, 3)
        pitch = torchcrepe.filter.mean(pitch, 3)
        p = pitch[0].numpy()
        conf = periodicity[0].numpy()
        # resample CREPE 10 ms grid onto our 11.6 ms grid
        t_c = np.arange(len(p)) * hop_c / sr_c
        t = np.arange(n_frames) * HOP / SR
        midi = np.interp(t, t_c, hz_to_midi(p))
        prob = np.interp(t, t_c, conf)
        midi[prob < 0.45] = np.nan
        return midi, prob
    # pYIN in chunks so we can report progress on long songs
    chunk = SR * 30
    mids, probs = [], []
    total = max(1, math.ceil(len(y) / chunk))
    for i in range(total):
        seg = y[i * chunk:(i + 1) * chunk + FRAME]  # overlap one frame
        f0, vflag, vprob = librosa.pyin(seg, fmin=fmin, fmax=fmax, sr=SR, frame_length=FRAME, hop_length=HOP,
                                        center=True, fill_na=np.nan)
        keep = math.ceil(min(chunk, len(y) - i * chunk) / HOP) if i < total - 1 else len(f0)
        m = hz_to_midi(f0[:keep])
        m[~vflag[:keep]] = np.nan
        mids.append(m)
        probs.append(vprob[:keep])
        if on_progress:
            on_progress((i + 1) / total)
    midi = np.concatenate(mids)[:n_frames]
    prob = np.concatenate(probs)[:n_frames]
    # pYIN's voicing probability is systematically low for low bass notes; rescale so the
    # typical voiced frame of THIS track scores ~1 and relative doubt is preserved.
    voiced = ~np.isnan(midi)
    if np.any(voiced):
        prob = np.clip(prob / (np.percentile(prob[voiced], 75) + 1e-9), 0, 1)
    if len(midi) < n_frames:
        pad = n_frames - len(midi)
        midi = np.concatenate([midi, np.full(pad, np.nan)])
        prob = np.concatenate([prob, np.zeros(pad)])
    return midi, prob


def detect_onsets(y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Onset times (s) and strength (0..1).

    Bass attacks are best seen as jumps in LOG energy (a re-plucked low note barely changes
    the spectrum, so spectral-flux detectors miss repeated notes). Measured on the synthetic
    answer-key groove: 37/37 attacks found vs 15/37 for librosa's default spectral flux.
    """
    import librosa
    rms = librosa.feature.rms(y=y, frame_length=512, hop_length=HOP)[0]
    lr = np.log(rms + 1e-4)
    env = np.maximum(0.0, np.diff(lr, prepend=lr[0]))
    env = np.convolve(env, np.ones(3) / 3, mode="same")
    ref = float(np.percentile(env[env > 0], 99)) if np.any(env > 0) else 1.0
    env = env / (ref or 1.0)
    frames = librosa.onset.onset_detect(onset_envelope=env, sr=SR, hop_length=HOP, delta=0.07, wait=6)
    return frames * HOP / SR, np.clip(env[frames], 0, 1)


def detect_tempo(path_for_tempo: str) -> tuple[float | None, float, float | None]:
    """BPM from the full mix (drums carry the beat better than the bass stem)."""
    import librosa
    y = load_mono(path_for_tempo, 22050)
    if len(y) < 22050 * 4:
        return None, 0.0, None
    env = librosa.onset.onset_strength(y=y, sr=22050, hop_length=512)
    tempo, beats = librosa.beat.beat_track(onset_envelope=env, sr=22050, hop_length=512, units="time")
    bpm = float(np.atleast_1d(tempo)[0])
    if not beats.size or not bpm:
        return None, 0.0, None
    ibi = np.diff(beats)
    stability = float(np.clip(1 - np.std(ibi) / (np.mean(ibi) + 1e-9) * 4, 0, 1)) if len(ibi) > 4 else 0.0
    # keep bass-friendly range: 60..200
    while bpm < 60:
        bpm *= 2
    while bpm > 200:
        bpm /= 2
    return round(bpm, 1), round(stability, 2), float(beats[0])


def fundamental_ratio(y: np.ndarray, start: float, dur: float, midi: int) -> float:
    """Spectral energy at the detected pitch relative to one octave above (window inside the note).
    A real fundamental is present in the spectrum; a subharmonic octave error is not."""
    a, b = int((start + 0.03) * SR), int((start + min(dur, 0.35)) * SR)
    seg = y[a:b]
    if seg.size < 1024:
        return 1.0
    n = 1 << int(np.ceil(np.log2(max(seg.size, 4096))))
    spec = np.abs(np.fft.rfft(seg * np.hanning(seg.size), n))
    f = 440 * 2 ** ((midi - 69) / 12)

    def band(freq):
        k = freq * n / SR
        lo, hi = int(k * 0.97), int(k * 1.03) + 1
        return float(spec[lo:hi].max()) if hi < spec.size and hi > lo else 0.0
    up = band(2 * f)
    return band(f) / up if up > 0 else 10.0


def harmonicity(y: np.ndarray, start: float, dur: float, midi: int) -> float:
    """Share of spectral energy sitting on the harmonics of the detected pitch (0..1).
    A plucked string is ~0.6-0.9; drum hits / noise mis-read as a pitch are ~0.1-0.2."""
    a, b = int((start + 0.02) * SR), int((start + min(dur, 0.4)) * SR)
    seg = y[a:b]
    if seg.size < 1024:
        return 0.5
    n = 1 << int(np.ceil(np.log2(max(seg.size, 8192))))
    p = np.abs(np.fft.rfft(seg * np.hanning(seg.size), n)) ** 2
    f0 = 440 * 2 ** ((midi - 69) / 12)
    hz = np.arange(p.size) * SR / n
    lo_hz, hi_hz = 0.5 * f0, min(8.5 * f0, SR / 2 - 1)
    total = p[(hz >= lo_hz) & (hz <= hi_hz)].sum()
    if total <= 0:
        return 0.0
    on = np.zeros_like(p, dtype=bool)
    for k in range(1, 9):
        fk = k * f0
        if fk >= hi_hz:
            break
        on |= (hz >= fk * 0.97) & (hz <= fk * 1.03)
    return float(p[on].sum() / total)


def segment(midi: np.ndarray, prob: np.ndarray, rms: np.ndarray, onsets: np.ndarray,
            onset_strength: np.ndarray) -> list[DetNote]:
    t_of = lambda i: i * HOP / SR  # noqa: E731
    onset_frames = set(int(round(o * SR / HOP)) for o in onsets)
    segs: list[tuple[int, int, int]] = []  # (start_frame, end_frame_exclusive, semitone)
    cur_start, cur_pitch, gap, off = None, None, 0, 0
    n = len(midi)
    for i in range(n + 1):
        m = midi[i] if i < n else np.nan
        voiced = not np.isnan(m)
        if cur_start is None:
            if voiced:
                cur_start, cur_pitch, gap, off = i, int(round(m)), 0, 0
            continue
        new_onset = i in onset_frames and i - cur_start >= 4
        if not voiced:
            gap += 1
            if gap > GAP_BRIDGE or i == n:
                segs.append((cur_start, i - gap + 1, cur_pitch))
                cur_start = None
            continue
        gap = 0
        if abs(m - cur_pitch) > 0.6:
            off += 1
        else:
            off = 0
        if off >= 3 or new_onset:  # pitch really changed (3 frames ~35 ms) or a new attack
            end = i - (off - 1 if off >= 3 else 0)
            segs.append((cur_start, end, cur_pitch))
            cur_start, cur_pitch, off = end, int(round(np.nanmedian(midi[end:i + 1]))), 0
    notes: list[DetNote] = []
    rms_ref = float(np.percentile(rms[rms > 0], 95)) if np.any(rms > 0) else 1.0
    onset_arr = np.array(sorted(onsets))
    for a, b, _ in segs:
        if b - a < 1:
            continue
        seg = midi[a:b]
        seg = seg[~np.isnan(seg)]
        if seg.size == 0:
            continue
        start, end = t_of(a), t_of(b)
        # the long analysis window "hears" a note up to ~90 ms before/after its attack:
        # align the start with the nearest detected attack
        if onset_arr.size:
            k = int(np.argmin(np.abs(onset_arr - start)))
            if abs(onset_arr[k] - start) <= 0.09 and onset_arr[k] < end - MIN_NOTE:
                start = float(onset_arr[k])
        if end - start < MIN_NOTE:
            continue
        med = float(np.median(seg))
        semitone = int(round(med))
        cents = (seg - semitone) * 100
        stability = float(np.clip(1 - (np.std(cents) - 15) / 60, 0, 1))
        voiced_frac = float(np.mean(~np.isnan(midi[a:b])))
        voicing = float(np.clip(np.mean(prob[a:b]) * 2, 0, 1))  # weak signal: pYIN under-scores low notes
        short = float(np.clip((end - start - MIN_NOTE) / 0.06, 0, 1))
        conf = round(0.35 * voiced_frac + 0.35 * stability + 0.15 * voicing + 0.15 * short, 3)
        vel = float(np.clip(np.mean(rms[a:b]) / rms_ref, 0, 1)) if rms_ref else None
        tech = "normal"
        # vibrato: oscillating pitch (>= 2 swings) of 25-100 cents around a stable centre
        if seg.size >= 20:
            detr = cents - np.convolve(cents, np.ones(9) / 9, mode="same")
            swings = np.sum(np.diff(np.sign(detr[4:-4])) != 0)
            if 25 <= np.ptp(cents) <= 120 and swings >= 4:
                tech = "vibrato"
        dn = DetNote(round(start, 4), round(end - start, 4), semitone, round(440 * 2 ** ((semitone - 69) / 12), 3),
                     conf, round(vel, 3) if vel is not None else 0.0, tech)
        if conf < REVIEW_BELOW:
            dn.needs_review = True
            dn.reasons.append("confidence rendah")
        notes.append(dn)

    # legato transitions: no new attack + (almost) no gap -> hammer-on / pull-off / slide
    for prev, nxt in zip(notes, notes[1:]):
        gap_s = nxt.start - (prev.start + prev.duration)
        if gap_s > 0.03 or nxt.midi == prev.midi:
            continue
        has_attack = onset_arr.size and np.min(np.abs(onset_arr - nxt.start)) < 0.03
        if has_attack:
            continue
        a = int(nxt.start * SR / HOP)
        glide = midi[max(0, a - 6):a + 3]
        glide = glide[~np.isnan(glide)]
        step = nxt.midi - prev.midi
        is_slide = glide.size >= 4 and np.ptp(glide) >= abs(step) * 0.6 and abs(step) >= 2 and \
            np.sum((glide > min(prev.midi, nxt.midi) + 0.4) & (glide < max(prev.midi, nxt.midi) - 0.4)) >= 2
        if is_slide:
            nxt.technique = "slide_up" if step > 0 else "slide_down"
        elif abs(step) <= 5:
            nxt.technique = "hammer_on" if step > 0 else "pull_off"
        nxt.reasons.append("teknik ditebak dari transisi legato")

    # octave slips: a short note exactly one octave away from both neighbours
    for i in range(1, len(notes) - 1):
        p, c, nx = notes[i - 1], notes[i], notes[i + 1]
        if c.duration < 0.2 and abs(c.midi - p.midi) == 12 and abs(c.midi - nx.midi) == 12:
            c.needs_review = True
            c.reasons.append("kemungkinan salah oktaf")

    # dead / muted notes: a clear attack with no pitched note starting near it
    starts = np.array([x.start for x in notes]) if notes else np.array([])
    dead: list[DetNote] = []
    for o, strength in zip(onsets, onset_strength):
        if strength < 0.35:
            continue
        if starts.size and np.min(np.abs(starts - o)) < 0.07:
            continue
        inside = any(x.start <= o < x.start + x.duration for x in notes)
        if inside:
            continue
        ref = max((x for x in notes if x.start <= o), key=lambda x: x.start, default=None) or \
            min((x for x in notes if x.start > o), key=lambda x: x.start, default=None)
        if ref is None:
            continue
        dead.append(DetNote(round(float(o), 4), 0.08, ref.midi, ref.frequency, 0.3, round(float(strength), 3),
                            "mute", True, ["attack tanpa nada jelas (dead note?)"]))
    notes.extend(dead)
    notes.sort(key=lambda x: x.start)
    return notes


def analyze(stem_path: str, tempo_path: str | None, method: str = "pyin", fmin: float = 28.0, fmax: float = 420.0,
            on_progress=None) -> Analysis:
    import librosa
    y = load_mono(stem_path)
    peak = float(np.max(np.abs(y))) if y.size else 0.0
    if peak < 1e-3:
        return Analysis([], None, 0.0, None, method)
    y = y / peak
    midi, prob = pitch_track(y, method, fmin, fmax, (lambda f: on_progress(0.1 + 0.6 * f)) if on_progress else None)
    if on_progress:
        on_progress(0.72)
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=HOP, center=True)[0]
    rms = rms[:len(midi)] if len(rms) >= len(midi) else np.pad(rms, (0, len(midi) - len(rms)))
    # energy gate: pitch trackers happily "hear" notes in bleed/noise; ignore frames 35 dB below the loud parts
    gate = np.percentile(rms[rms > 0], 95) * 10 ** (-35 / 20) if np.any(rms > 0) else 0
    midi = midi.copy()
    midi[rms < gate] = np.nan
    onsets, strength = detect_onsets(y)
    notes = segment(midi, prob, rms, onsets, strength)
    # octave check: if the "fundamental" is missing from the spectrum, the note is really an octave higher
    for nt in notes:
        if nt.technique == "mute":
            continue
        r = fundamental_ratio(y, nt.start, nt.duration, nt.midi)
        h = harmonicity(y, nt.start, nt.duration, nt.midi)
        harm = float(np.clip((h - 0.2) / 0.35, 0, 1))
        nt.confidence = round(0.55 * nt.confidence + 0.45 * harm, 3)
        if h < 0.3:
            nt.needs_review = True
            nt.reasons.append("nada tidak jelas (mungkin bocoran drum/noise)")
        if nt.midi > 60:
            nt.needs_review = True
            nt.reasons.append("di atas range bass umum (mungkin bocoran vokal/gitar)")
        if nt.confidence < REVIEW_BELOW and "confidence rendah" not in nt.reasons:
            nt.needs_review = True
            nt.reasons.append("confidence rendah")
        elif nt.confidence >= REVIEW_BELOW and nt.reasons == ["confidence rendah"]:
            nt.needs_review, nt.reasons = False, []
        if r < 0.12:
            nt.midi += 12
            nt.frequency = round(440 * 2 ** ((nt.midi - 69) / 12), 3)
            nt.reasons.append("oktaf dikoreksi otomatis (cek ulang)")
            nt.needs_review = True
    if on_progress:
        on_progress(0.82)
    bpm, bpm_conf, first_beat = detect_tempo(tempo_path or stem_path)
    return Analysis(notes, bpm, bpm_conf, first_beat, method)
