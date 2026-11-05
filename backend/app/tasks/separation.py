"""Bass stem separation job — runs ONLY inside the worker container (needs torch + demucs).

Pipeline: original audio -> FFmpeg decode (float32, 44.1 kHz stereo) -> Demucs on CPU
-> stems written as FLAC (download) + AAC (browser playback) + waveform JSON.
Nothing is faked: if the model cannot be loaded or runs out of memory the job fails
with a readable error and no stem is written.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_engine
from ..models import AnalysisJob, AudioStem, Project
from ..separation_models import MODELS
from ..services.audio import peaks

log = logging.getLogger("nbs.separation")
SR = 44100


def _now():
    return datetime.now(timezone.utc)


def _decode(path: str) -> np.ndarray:
    """Decode any validated input to float32 stereo [2, N] at 44.1 kHz."""
    s = get_settings()
    r = subprocess.run([s.ffmpeg_bin, "-v", "error", "-i", path, "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                       capture_output=True, timeout=900)
    if r.returncode != 0:
        raise RuntimeError("Gagal membaca audio asli: " + r.stderr.decode(errors="ignore")[-300:])
    return np.frombuffer(r.stdout, dtype=np.float32).reshape(-1, 2).T.copy()


def _encode(stereo: np.ndarray, out: Path, args: list[str]) -> None:
    s = get_settings()
    data = np.ascontiguousarray(np.clip(stereo, -1.0, 1.0).T.astype(np.float32)).tobytes()
    r = subprocess.run([s.ffmpeg_bin, "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                        *args, str(out)], input=data, capture_output=True, timeout=900)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError("Gagal menyimpan stem: " + r.stderr.decode(errors="ignore")[-300:])


class _Progress:
    """Turns Demucs chunk callbacks into a 0..1 progress value written to the DB (throttled)."""

    def __init__(self, db: Session, job: AnalysisJob, start: float, span: float, n_models: int):
        self.db, self.job, self.start, self.span, self.n_models = db, job, start, span, max(1, n_models)
        self.last = 0.0

    def __call__(self, d: dict) -> None:
        if d.get("state") != "end":
            return
        length = d.get("audio_length") or 1
        frac = (d.get("model_idx_in_bag", 0) + min(1.0, d.get("segment_offset", 0) / length)) / self.n_models
        now = time.monotonic()
        if now - self.last >= 2.0:
            self.last = now
            self.job.progress = round(self.start + self.span * frac, 4)
            self.db.commit()


def _set(db: Session, job: AnalysisJob, *, progress: float | None = None, stage: str | None = None, **kw) -> None:
    if progress is not None:
        job.progress = progress
    if stage is not None:
        job.stage = stage
    for k, v in kw.items():
        setattr(job, k, v)
    db.commit()


def _separate(mix: np.ndarray, model_key: str, on_progress) -> dict[str, np.ndarray]:
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    torch.set_num_threads(int(os.environ.get("WORKER_THREADS", "2")))
    spec = MODELS[model_key]
    model = get_model(spec["demucs_name"])
    only = spec.get("only_source")
    if only and hasattr(model, "models"):
        # pick the bag member specialised for this source (largest weight)
        idx = model.sources.index(only)
        best = max(range(len(model.models)), key=lambda i: model.weights[i][idx])
        model = model.models[best]
    model.eval()
    if getattr(model, "samplerate", SR) != SR:
        raise RuntimeError(f"Model samplerate {model.samplerate} tidak didukung")

    wav = torch.from_numpy(mix)
    ref = wav.mean(0)
    mean, std = ref.mean(), ref.std() + 1e-8
    norm = (wav - mean) / std
    n_models = len(getattr(model, "models", [model]))
    with torch.no_grad():
        out = apply_model(model, norm[None], device="cpu", shifts=1, split=True, overlap=0.25, progress=False,
                          callback=on_progress(n_models), callback_arg={"audio_length": norm.shape[-1]})[0]
    out = out * std + mean
    stems = {name: out[i].numpy() for i, name in enumerate(model.sources)}
    if only:
        stems = {only: stems[only]}
    return stems


def run_separation(job_id: str) -> None:
    """RQ entry point."""
    logging.basicConfig(level=logging.INFO)
    s = get_settings()
    db = Session(bind=get_engine(), expire_on_commit=False)
    job = db.get(AnalysisJob, uuid.UUID(job_id))
    if job is None or job.status not in ("queued", "processing"):
        db.close()
        return
    project = db.get(Project, job.project_id)
    t0 = time.monotonic()
    try:
        original = next((a for a in project.audio_files if a.kind == "original"), None)
        if original is None:
            raise RuntimeError("Proyek belum punya audio asli.")
        _set(db, job, status="processing", started_at=_now(), progress=0.01, stage="Membaca audio")
        project.status = "processing"
        db.commit()

        mix = _decode(original.storage_path)
        _set(db, job, progress=0.03, stage="Memuat model AI (unduhan pertama bisa beberapa menit)")
        stems = _separate(mix, job.model_name, lambda n: _Progress(db, job, 0.05, 0.85, n))

        spec = MODELS[job.model_name]
        if "bass" in stems:
            stems["no_bass"] = mix - stems["bass"] if len(stems) == 1 else sum(v for k, v in stems.items() if k != "bass")
        wanted = [k for k in spec["stems"] if k in stems]

        _set(db, job, progress=0.9, stage="Menyimpan stem")
        pdir = s.storage_dir / str(project.owner_id) / str(project.id) / "stems"
        pdir.mkdir(parents=True, exist_ok=True)
        new_rows: list[AudioStem] = []
        for i, name in enumerate(wanted):
            arr = stems[name]
            sid = uuid.uuid4()
            flac, play, wave = pdir / f"{sid.hex}.flac", pdir / f"{sid.hex}.play.m4a", pdir / f"{sid.hex}.waveform.json"
            _encode(arr, flac, ["-c:a", "flac", "-sample_fmt", "s16"])
            _encode(arr, play, ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"])
            dur = arr.shape[-1] / SR
            wave.write_text(json.dumps({"duration": dur, "points": peaks(arr.mean(0))}))
            new_rows.append(AudioStem(id=sid, project_id=project.id, source_audio_id=original.id, job_id=job.id,
                                      stem_type=name, origin="separated", model_name=job.model_name,
                                      storage_path=str(flac), playback_path=str(play), waveform_path=str(wave),
                                      format="flac", size_bytes=flac.stat().st_size, duration_sec=dur))
            _set(db, job, progress=0.9 + 0.09 * (i + 1) / len(wanted))

        # replace older stems of the same type (files first, then rows)
        for old in [st for st in project.stems if st.stem_type in wanted]:
            for f in (old.storage_path, old.playback_path, old.waveform_path):
                if f:
                    Path(f).unlink(missing_ok=True)
            db.delete(old)
        db.flush()
        db.add_all(new_rows)
        elapsed = time.monotonic() - t0
        _set(db, job, status="completed", progress=1.0, finished_at=_now(),
             stage=f"Selesai dalam {elapsed / 60:.1f} menit")
        project.status = "completed"
        db.commit()
        log.info("separation %s done in %.1fs (%s, %.1fs audio)", job_id, elapsed, job.model_name, mix.shape[-1] / SR)
    except MemoryError:
        db.rollback()
        _fail(db, job, project, "RAM server tidak cukup untuk model ini. Coba model 'HTDemucs — cepat' atau lagu yang lebih pendek.")
    except Exception as e:  # noqa: BLE001
        db.rollback()
        log.error("separation %s failed: %s", job_id, traceback.format_exc())
        msg = str(e) or e.__class__.__name__
        if "huggingface" in msg.lower() or "connection" in msg.lower():
            msg = "Gagal mengunduh model AI. Cek koneksi internet VPS lalu coba lagi. (" + msg[:200] + ")"
        _fail(db, job, project, msg[:1000])
    finally:
        db.close()


def _fail(db: Session, job: AnalysisJob, project: Project, msg: str) -> None:
    job.status, job.error, job.finished_at, job.stage = "failed", msg, _now(), "Gagal"
    project.status = "failed"
    db.commit()
