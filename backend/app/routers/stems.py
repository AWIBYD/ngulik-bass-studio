"""Phase 2 API: bass extraction jobs, stems, and manual bass-stem upload."""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import jobqueue
from ..config import get_settings
from ..db import get_db
from ..models import AnalysisJob, AudioStem, Project, User
from ..security import get_current_user, get_owned_project, limiter
from ..separation_models import DEFAULT_MODEL, MODELS, STEM_LABELS
from ..services import audio as audio_svc

router = APIRouter(prefix="/api", tags=["stems"])

ACTIVE = ("queued", "processing")
DEAD_MSG = "Worker berhenti di tengah proses (kemungkinan RAM habis atau container restart). Silakan coba lagi."


class SeparateIn(BaseModel):
    model: str = DEFAULT_MODEL


class TranscribeIn(BaseModel):
    source: Literal["auto", "bass_stem", "original"] = "auto"
    method: Literal["pyin", "crepe"] = "pyin"
    mode: Literal["replace", "merge"] = "replace"
    apply_bpm: bool = True


def _job_out(j: AnalysisJob) -> dict:
    return {"id": str(j.id), "type": j.job_type, "status": j.status, "progress": j.progress, "stage": j.stage,
            "model": j.model_name, "error": j.error, "params": j.params, "result": j.result, "created_at": j.created_at, "started_at": j.started_at,
            "finished_at": j.finished_at}


def _stem_out(p: Project, st: AudioStem) -> dict:
    return {"id": str(st.id), "stem_type": st.stem_type, "label": STEM_LABELS.get(st.stem_type, st.stem_type),
            "origin": st.origin, "model": st.model_name, "format": st.format, "size_bytes": st.size_bytes,
            "duration_sec": st.duration_sec, "created_at": st.created_at,
            "stream_url": f"/api/projects/{p.id}/stems/{st.id}/stream",
            "download_url": f"/api/projects/{p.id}/stems/{st.id}/download",
            "waveform_url": f"/api/projects/{p.id}/stems/{st.id}/waveform"}


def reconcile(db: Session, jobs: list[AnalysisJob]) -> None:
    """Mark jobs whose RQ job vanished/crashed (e.g. OOM kill) as failed, so nothing stays 'processing' forever."""
    changed = False
    for j in jobs:
        if j.status in ACTIVE:
            st = jobqueue.rq_status(j.rq_job_id)
            if st in jobqueue.DEAD_STATUSES or (st == "finished"):
                db.refresh(j)  # the worker may have just written the final state
                if j.status in ACTIVE:
                    j.status, j.error, j.stage = "failed", DEAD_MSG, "Gagal"
                    j.finished_at = datetime.now(timezone.utc)
                    p = db.get(Project, j.project_id)
                    if p and p.status in ACTIVE:
                        p.status = "failed"
                    changed = True
    if changed:
        db.commit()


def _speed_estimates(db: Session) -> dict[str, float]:
    """Measured processing-time / audio-duration ratio per model on THIS server (median of last 10)."""
    out: dict[str, float] = {}
    for key in MODELS:
        rows = db.execute(
            select(AnalysisJob.started_at, AnalysisJob.finished_at, Project.id)
            .join(Project, Project.id == AnalysisJob.project_id)
            .where(AnalysisJob.model_name == key, AnalysisJob.job_type == "separation",
                   AnalysisJob.status == "completed", AnalysisJob.started_at.is_not(None))
            .order_by(AnalysisJob.finished_at.desc()).limit(10)
        ).all()
        ratios = []
        for started, finished, pid in rows:
            p = db.get(Project, pid)
            a = next((x for x in p.audio_files if x.kind == "original"), None) if p else None
            if a and finished and a.duration_sec:
                ratios.append((finished - started).total_seconds() / a.duration_sec)
        if ratios:
            ratios.sort()
            out[key] = round(ratios[len(ratios) // 2], 3)
    return out


@router.get("/separation/status")
def separation_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        jobqueue.redis_conn().ping()
        redis_ok = True
    except Exception:
        redis_ok = False
    speeds = _speed_estimates(db)
    return {
        "redis_online": redis_ok,
        "workers_online": jobqueue.workers_online() if redis_ok else 0,
        "queue_length": jobqueue.queue_length() if redis_ok else 0,
        "default_model": DEFAULT_MODEL,
        "models": [{"key": k, "label": v["label"], "description": v["description"], "stems": v["stems"],
                    "relative_cost": v["relative_cost"], "measured_ratio": speeds.get(k)} for k, v in MODELS.items()],
    }


@router.post("/projects/{project_id}/separate", status_code=202)
@limiter.limit(lambda: get_settings().rate_limit_separation)
def start_separation(request: Request, project_id: uuid.UUID, body: SeparateIn,
                     user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = get_owned_project(project_id, user, db)
    if body.model not in MODELS:
        raise HTTPException(422, "Model tidak dikenal.")
    if not any(a.kind == "original" for a in p.audio_files):
        raise HTTPException(409, "Upload lagu dulu sebelum ekstraksi.")
    active = db.scalars(select(AnalysisJob).where(AnalysisJob.project_id == p.id, AnalysisJob.job_type == "separation",
                                                  AnalysisJob.status.in_(ACTIVE))).all()
    reconcile(db, list(active))
    if any(j.status in ACTIVE for j in active):
        raise HTTPException(409, "Ekstraksi untuk proyek ini masih berjalan.")
    try:
        jobqueue.redis_conn().ping()
    except Exception:
        raise HTTPException(503, "Antrean pemrosesan (Redis) tidak aktif. Cek container redis & worker.")
    if jobqueue.workers_online() == 0:
        raise HTTPException(503, "Worker ekstraksi sedang tidak aktif. Cek container worker di VPS.")
    job = AnalysisJob(project_id=p.id, job_type="separation", status="queued", model_name=body.model,
                      stage="Menunggu antrean")
    db.add(job)
    p.status = "queued"
    db.commit()
    try:
        job.rq_job_id = jobqueue.enqueue_separation(str(job.id))
    except Exception as e:
        job.status, job.error = "failed", f"Gagal masuk antrean: {e}"
        p.status = "failed"
        db.commit()
        raise HTTPException(503, job.error)
    db.commit()
    return _job_out(job)


@router.get("/projects/{project_id}/jobs")
def list_jobs(project_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = get_owned_project(project_id, user, db)
    jobs = db.scalars(select(AnalysisJob).where(AnalysisJob.project_id == p.id)
                      .order_by(AnalysisJob.created_at.desc()).limit(20)).all()
    reconcile(db, list(jobs))
    return [_job_out(j) for j in jobs]


@router.post("/projects/{project_id}/jobs/{job_id}/cancel")
def cancel_job(project_id: uuid.UUID, job_id: uuid.UUID, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    p = get_owned_project(project_id, user, db)
    j = db.get(AnalysisJob, job_id)
    if not j or j.project_id != p.id:
        raise HTTPException(404, "Job not found")
    if j.status not in ACTIVE:
        raise HTTPException(409, "Job sudah selesai.")
    jobqueue.cancel(j.rq_job_id)
    j.status, j.error, j.stage, j.finished_at = "failed", "Dibatalkan oleh pengguna.", "Dibatalkan", datetime.now(timezone.utc)
    p.status = "ready" if not p.stems else "completed"
    db.commit()
    return _job_out(j)


@router.get("/projects/{project_id}/stems")
def list_stems(project_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = get_owned_project(project_id, user, db)
    order = list(STEM_LABELS)
    return [_stem_out(p, s) for s in sorted(p.stems, key=lambda s: order.index(s.stem_type) if s.stem_type in order else 99)]


def _owned_stem(project_id: uuid.UUID, stem_id: uuid.UUID, user: User, db: Session) -> AudioStem:
    p = get_owned_project(project_id, user, db)
    st = next((s for s in p.stems if s.id == stem_id), None)
    if not st:
        raise HTTPException(404, "Stem not found")
    return st


@router.get("/projects/{project_id}/stems/{stem_id}/stream")
def stream_stem(project_id: uuid.UUID, stem_id: uuid.UUID, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    st = _owned_stem(project_id, stem_id, user, db)
    return FileResponse(st.playback_path or st.storage_path, media_type="audio/mp4",
                        headers={"Cache-Control": "private, max-age=3600"})


@router.get("/projects/{project_id}/stems/{stem_id}/download")
def download_stem(project_id: uuid.UUID, stem_id: uuid.UUID, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    st = _owned_stem(project_id, stem_id, user, db)
    p = db.get(Project, st.project_id)
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in p.name).strip() or "stem"
    ext = Path(st.storage_path).suffix
    return FileResponse(st.storage_path, filename=f"{safe} - {STEM_LABELS.get(st.stem_type, st.stem_type)}{ext}",
                        media_type="application/octet-stream")


@router.get("/projects/{project_id}/stems/{stem_id}/waveform")
def stem_waveform(project_id: uuid.UUID, stem_id: uuid.UUID, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    st = _owned_stem(project_id, stem_id, user, db)
    if not st.waveform_path:
        raise HTTPException(404, "No waveform")
    return FileResponse(st.waveform_path, media_type="application/json")


@router.delete("/projects/{project_id}/stems/{stem_id}", status_code=204)
def delete_stem(project_id: uuid.UUID, stem_id: uuid.UUID, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    st = _owned_stem(project_id, stem_id, user, db)
    for f in (st.storage_path, st.playback_path, st.waveform_path):
        if f:
            Path(f).unlink(missing_ok=True)
    db.delete(st)
    db.commit()


@router.post("/projects/{project_id}/stems/bass-upload", status_code=201)
@limiter.limit(lambda: get_settings().rate_limit_upload)
async def upload_bass_stem(request: Request, project_id: uuid.UUID, file: UploadFile = File(...),
                           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Fallback when AI separation is unavailable: the user uploads a bass stem they already have."""
    s = get_settings()
    p = get_owned_project(project_id, user, db)
    ext = Path(file.filename or "").suffix.lower().lstrip(".")
    if ext not in s.allowed_ext:
        raise HTTPException(415, f"Ekstensi .{ext or '?'} tidak didukung.")
    pdir = s.storage_dir / str(p.owner_id) / str(p.id) / "stems"
    pdir.mkdir(parents=True, exist_ok=True)
    tmp = pdir / f"upload-{uuid.uuid4().hex}.part"
    size = 0
    try:
        with tmp.open("wb") as out:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > s.max_upload_bytes:
                    raise HTTPException(413, f"File melebihi batas {s.max_upload_mb} MB.")
                out.write(chunk)
        if size == 0:
            raise HTTPException(400, "File kosong.")
        try:
            info = await run_in_threadpool(audio_svc.probe, tmp)
            points = await run_in_threadpool(audio_svc.decode_check_and_waveform, tmp, info.duration)
        except audio_svc.AudioValidationError as e:
            raise HTTPException(422, str(e))
        sid = uuid.uuid4()
        orig = pdir / f"{sid.hex}.{info.format}"
        play = pdir / f"{sid.hex}.play.m4a"
        wave = pdir / f"{sid.hex}.waveform.json"
        tmp.rename(orig)
        try:
            await run_in_threadpool(audio_svc.make_playback, orig, play)
        except audio_svc.AudioValidationError as e:
            orig.unlink(missing_ok=True)
            raise HTTPException(422, str(e))
        wave.write_text(json.dumps({"duration": info.duration, "points": points}))
    finally:
        tmp.unlink(missing_ok=True)

    warning = None
    original = next((a for a in p.audio_files if a.kind == "original"), None)
    if original and abs(original.duration_sec - info.duration) > 1.0:
        warning = (f"Durasi bass ({info.duration:.1f} dtk) beda dengan lagu asli ({original.duration_sec:.1f} dtk). "
                   "Pastikan stem dimulai di detik yang sama agar tetap sinkron.")
    for old in [st for st in p.stems if st.stem_type == "bass"]:
        for f in (old.storage_path, old.playback_path, old.waveform_path):
            if f:
                Path(f).unlink(missing_ok=True)
        db.delete(old)
    db.flush()
    st = AudioStem(id=sid, project_id=p.id, source_audio_id=original.id if original else None, stem_type="bass",
                   origin="user_upload", model_name=None, storage_path=str(orig), playback_path=str(play),
                   waveform_path=str(wave), format=info.format, size_bytes=size, duration_sec=info.duration)
    db.add(st)
    db.commit()
    return {"stem": _stem_out(p, st), "warning": warning}


@router.post("/projects/{project_id}/transcribe", status_code=202)
@limiter.limit(lambda: get_settings().rate_limit_separation)
def start_transcription(request: Request, project_id: uuid.UUID, body: TranscribeIn,
                        user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = get_owned_project(project_id, user, db)
    has_bass = any(s.stem_type == "bass" for s in p.stems)
    has_audio = any(a.kind == "original" for a in p.audio_files)
    if body.source == "bass_stem" and not has_bass:
        raise HTTPException(409, "Belum ada bass stem. Jalankan Bass Extractor atau upload bass stem dulu.")
    if not (has_audio or has_bass):
        raise HTTPException(409, "Upload lagu dulu.")
    active = db.scalars(select(AnalysisJob).where(AnalysisJob.project_id == p.id, AnalysisJob.status.in_(ACTIVE))).all()
    reconcile(db, list(active))
    if any(j.status in ACTIVE for j in active):
        raise HTTPException(409, "Masih ada proses AI yang berjalan untuk proyek ini. Tunggu sampai selesai.")
    try:
        jobqueue.redis_conn().ping()
    except Exception:
        raise HTTPException(503, "Antrean pemrosesan (Redis) tidak aktif.")
    if jobqueue.workers_online() == 0:
        raise HTTPException(503, "Worker AI sedang tidak aktif. Cek container worker di VPS.")
    job = AnalysisJob(project_id=p.id, job_type="transcription", status="queued", model_name=body.method,
                      params=body.model_dump(), stage="Menunggu antrean")
    db.add(job)
    p.status = "queued"
    db.commit()
    try:
        job.rq_job_id = jobqueue.enqueue_transcription(str(job.id))
    except Exception as e:
        job.status, job.error = "failed", f"Gagal masuk antrean: {e}"
        p.status = "failed"
        db.commit()
        raise HTTPException(503, job.error)
    db.commit()
    return _job_out(job)
