"""Automatic bass tab job (worker only). bass stem/original -> notes -> string/fret -> tab notes.

Raw AI output is kept in detected_notes; the editable tab gets source='ai' notes with
confidence and a needs_review flag. Manual notes are never overwritten in 'merge' mode.
"""
from __future__ import annotations

import logging
import time
import traceback
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..db import get_engine
from ..models import AnalysisJob, DetectedNote, Project, TabNote, TabTrack
from ..services.fingering import MAX_FRET, assign
from ..services.music import midi_to_freq, midi_to_note, note_to_midi, string_open_midi

log = logging.getLogger("nbs.transcription")


def _now():
    return datetime.now(timezone.utc)


def _rebuild_measures(project: Project, track: TabTrack, db: Session, audio_end: float) -> None:
    from ..models import TabMeasure
    bar = project.time_sig_num * (60.0 / project.bpm) * (4.0 / project.time_sig_den)
    end = max([audio_end] + [n.start_time + n.duration for n in track.notes] + [bar])
    count = min(5000, max(1, int((end - project.offset_sec) / bar) + 1))
    track.measures.clear()
    db.flush()
    for i in range(count):
        track.measures.append(TabMeasure(index=i, start_time=round(project.offset_sec + i * bar, 6), duration=bar,
                                         bpm=project.bpm, time_sig_num=project.time_sig_num,
                                         time_sig_den=project.time_sig_den))


def run_transcription(job_id: str) -> None:
    logging.basicConfig(level=logging.INFO)
    from ..services.transcribe import analyze  # heavy import (librosa) only inside the worker

    db = Session(bind=get_engine(), expire_on_commit=False)
    job = db.get(AnalysisJob, uuid.UUID(job_id))
    if job is None or job.status not in ("queued", "processing"):
        db.close()
        return
    project = db.get(Project, job.project_id)
    params = job.params or {}
    t0 = time.monotonic()
    last = [0.0]

    def progress(v: float, stage: str | None = None):
        now = time.monotonic()
        if stage or now - last[0] > 2:
            last[0] = now
            job.progress = round(v, 3)
            if stage:
                job.stage = stage
            db.commit()

    try:
        job.status, job.started_at = "processing", _now()
        project.status = "processing"
        progress(0.02, "Menyiapkan audio")
        original = next((a for a in project.audio_files if a.kind == "original"), None)
        bass = next((s for s in project.stems if s.stem_type == "bass"), None)
        src = params.get("source", "auto")
        if src in ("auto", "bass_stem") and bass:
            path, used = bass.storage_path, "bass stem"
        elif src == "bass_stem":
            raise RuntimeError("Belum ada bass stem. Jalankan Bass Extractor atau upload bass stem dulu.")
        elif original:
            path, used = original.storage_path, "lagu asli (kurang akurat, ada instrumen lain)"
        else:
            raise RuntimeError("Proyek belum punya audio.")

        tuning = project.tuning
        opens = [note_to_midi(n) for n in tuning]
        fmin = 440 * 2 ** ((min(opens) - 1 - 69) / 12)
        fmax = min(420.0, 440 * 2 ** ((max(opens) + MAX_FRET - 69) / 12))
        method = params.get("method", "pyin")
        progress(0.08, f"Deteksi nada ({'CREPE' if method == 'crepe' else 'pYIN'}) dari {used.split(' (')[0]}")
        result = analyze(path, original.storage_path if original else None, method=method, fmin=fmin, fmax=fmax,
                         on_progress=lambda v: progress(v))
        progress(0.86, "Menentukan senar & fret")

        pitched = [n for n in result.notes]
        placed = assign([(n.start, n.duration, n.midi) for n in pitched], tuning)

        # raw detections
        db.execute(delete(DetectedNote).where(DetectedNote.project_id == project.id))
        for n in pitched:
            db.add(DetectedNote(job_id=job.id, project_id=project.id, pitch_midi=n.midi, frequency=n.frequency,
                                start_time=n.start, duration=n.duration, velocity=n.velocity,
                                confidence_score=n.confidence))

        track = project.tab_track or TabTrack(project_id=project.id)
        if project.tab_track is None:
            project.tab_track = track
            db.flush()
        mode = params.get("mode", "replace")
        cols = ("string_number", "fret_number", "pitch", "pitch_midi", "frequency", "start_time", "duration",
                "velocity", "technique", "confidence_score", "source", "needs_review")
        keep = [TabNote(**{c: getattr(m, c) for c in cols}) for m in track.notes if m.source == "manual"] \
            if mode == "merge" else []
        track.notes.clear()
        db.flush()
        busy = [(m.start_time, m.start_time + m.duration) for m in keep]
        added = flagged = 0
        for n, pl in zip(pitched, placed):
            if any(a - 0.02 < n.start < b - 0.02 for a, b in busy):
                continue  # merge mode: manual note already there
            midi = string_open_midi(tuning, pl.string) + pl.fret
            reasons = list(n.reasons) + (["dipindah oktaf agar muat di bass ini"] if pl.transposed else [])
            review = n.needs_review or bool(pl.transposed)
            track.notes.append(TabNote(string_number=pl.string, fret_number=pl.fret, pitch=midi_to_note(midi),
                                       pitch_midi=midi, frequency=round(midi_to_freq(midi), 4), start_time=n.start,
                                       duration=n.duration, velocity=n.velocity, technique=n.technique,
                                       confidence_score=n.confidence, source="ai", needs_review=review))
            added += 1
            flagged += review
        for k in keep:
            track.notes.append(k)

        applied_bpm = False
        if params.get("apply_bpm") and result.bpm and result.bpm_confidence >= 0.3:
            project.bpm = result.bpm
            project.offset_sec = round(result.first_beat or 0.0, 4)
            applied_bpm = True
        track.version += 1
        db.flush()
        _rebuild_measures(project, track, db, original.duration_sec if original else 0.0)

        elapsed = time.monotonic() - t0
        job.result = {"notes": added, "needs_review": flagged, "kept_manual": len(keep), "bpm": result.bpm,
                      "bpm_confidence": result.bpm_confidence, "bpm_applied": applied_bpm, "source": used,
                      "method": method, "seconds": round(elapsed, 1)}
        bpm_txt = f" · BPM {result.bpm}" + (" (dipakai)" if applied_bpm else "") if result.bpm else ""
        job.status, job.progress, job.finished_at = "completed", 1.0, _now()
        job.stage = f"{added} nada · {flagged} perlu dicek{bpm_txt} · {elapsed / 60:.1f} menit"
        project.status = "completed"
        db.commit()
        log.info("transcription %s: %s", job_id, job.result)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        log.error("transcription %s failed: %s", job_id, traceback.format_exc())
        job = db.get(AnalysisJob, uuid.UUID(job_id))
        project = db.get(Project, job.project_id)
        job.status, job.error, job.finished_at, job.stage = "failed", (str(e) or e.__class__.__name__)[:1000], _now(), "Gagal"
        project.status = "failed"
        db.commit()
    finally:
        db.close()
