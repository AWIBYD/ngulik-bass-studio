"""Audio validation, normalization and waveform extraction using FFmpeg.

Nothing here trusts the file extension or the client's Content-Type: the container
and codec are identified by ffprobe and the whole stream is decoded once to catch
corrupt files before a project is allowed to use it.
"""
import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import get_settings

# ffprobe format_name -> our format label
_FORMAT_MAP = {
    "mp3": "mp3",
    "wav": "wav",
    "flac": "flac",
    "mov,mp4,m4a,3gp,3g2,mj2": "m4a",
}
_ALLOWED_CODECS = {
    "mp3": {"mp3"},
    "wav": {"pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le", "pcm_u8", "pcm_s16be"},
    "flac": {"flac"},
    "m4a": {"aac", "alac"},
}

WAVEFORM_POINTS = 2000


class AudioValidationError(ValueError):
    pass


@dataclass
class ProbeResult:
    format: str
    codec: str
    duration: float
    sample_rate: int
    channels: int


def _run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, timeout=timeout)


def probe(path: Path) -> ProbeResult:
    s = get_settings()
    r = _run([s.ffprobe_bin, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)], 60)
    if r.returncode != 0:
        raise AudioValidationError("File tidak dapat dibaca sebagai audio (rusak atau bukan audio).")
    info = json.loads(r.stdout or b"{}")
    fmt_name = info.get("format", {}).get("format_name", "")
    fmt = _FORMAT_MAP.get(fmt_name)
    if fmt is None or fmt not in s.allowed_ext:
        raise AudioValidationError(f"Format tidak didukung ({fmt_name or 'unknown'}).")
    streams = info.get("streams", [])
    audio = [st for st in streams if st.get("codec_type") == "audio"]
    if not audio:
        raise AudioValidationError("Tidak ada stream audio di file ini.")
    if any(st.get("codec_type") == "video" and not st.get("disposition", {}).get("attached_pic") for st in streams):
        raise AudioValidationError("File berisi video. Unggah file audio saja.")
    a = audio[0]
    codec = a.get("codec_name", "")
    if codec not in _ALLOWED_CODECS[fmt]:
        raise AudioValidationError(f"Codec {codec} tidak didukung untuk {fmt}.")
    try:
        duration = float(info["format"].get("duration") or a.get("duration"))
    except (TypeError, ValueError, KeyError):
        raise AudioValidationError("Durasi audio tidak terbaca.")
    if duration <= 0.5:
        raise AudioValidationError("Audio kosong atau terlalu pendek.")
    if duration > s.max_duration_sec:
        raise AudioValidationError(f"Durasi {duration:.0f} detik melebihi batas {s.max_duration_sec} detik.")
    return ProbeResult(fmt, codec, duration, int(a.get("sample_rate", 0)), int(a.get("channels", 0)))


def decode_check_and_waveform(path: Path, duration: float) -> list[float]:
    """Decode the full stream (corruption check) to mono 8 kHz and compute peak envelope."""
    s = get_settings()
    r = _run([s.ffmpeg_bin, "-v", "error", "-xerror", "-i", str(path), "-ac", "1", "-ar", "8000", "-f", "s16le", "-"], 600)
    if r.returncode != 0:
        raise AudioValidationError("Audio rusak: gagal di-decode sampai akhir.")
    samples = np.frombuffer(r.stdout, dtype=np.int16)
    if samples.size < 8000 * 0.5:
        raise AudioValidationError("Audio kosong.")
    peak = int(np.abs(samples).max())
    if peak < 33:  # ~ -60 dBFS: effectively silent
        raise AudioValidationError("Audio hanya berisi hening.")
    return peaks(samples.astype(np.float32) / 32768.0)


def peaks(mono: np.ndarray, points: int = WAVEFORM_POINTS) -> list[float]:
    """Peak envelope of a mono float signal in [-1, 1]."""
    buckets = np.array_split(np.abs(mono), points)
    return [round(float(b.max()) if b.size else 0.0, 4) for b in buckets]


def make_playback(src: Path, dst: Path) -> None:
    """Normalize to AAC/M4A 44.1 kHz with faststart: small for mobile, precise seeking."""
    s = get_settings()
    r = _run([s.ffmpeg_bin, "-v", "error", "-y", "-i", str(src), "-vn", "-map_metadata", "-1",
              "-ac", "2", "-ar", "44100", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dst)], 900)
    if r.returncode != 0 or not dst.exists():
        raise AudioValidationError("Gagal menyiapkan audio untuk diputar.")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
