import json
import math
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import AudioFile, Project, TabMeasure, TabNote, TabTrack, User
from ..schemas import AudioOut, ProjectIn, ProjectOut, ProjectPatch, TabIn, TabOut
from ..security import get_current_user, get_owned_project, limiter
from ..services import audio as audio_svc
from ..services.music import midi_to_freq, midi_to_note, string_open_midi

router = APIRouter(prefix="/api/projects", tags=["projects"])


# ---------- helpers ----------
def _project_dir(p: Project) -> Path:
    d = get_settings().storage_dir / str(p.owner_id) / str(p.id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _original_audio(p: Project) -> AudioFile | None:
    return next((a for a in p.audio_files if a.kind == "original"), None)


def _ensure_track(p: Project, db: Session) -> TabTrack:
    if p.tab_track is None:
        p.tab_track = TabTrack(project_id=p.id)
        db.flush()
    return p.tab_track


def _project_out(p: Project, db: Session) -> ProjectOut:
    out = ProjectOut.model_validate(p)
    a = _original_audio(p)
    out.audio = AudioOut.model_validate(a) if a else None
    if p.tab_track:
        out.note_count = db.scalar(select(func.count()).select_from(TabNote).where(TabNote.track_id == p.tab_track.id)) or 0
    return out


def _fill_pitch(n: TabNote, tuning: list[str]) -> None:
    midi = string_open_midi(tuning, n.string_number) + n.fret_number
    n.pitch_midi, n.pitch, n.frequency = midi, midi_to_note(midi), round(midi_to_freq(midi), 4)


def _rebuild_measures(p: Project, track: TabTrack, db: Session) -> None:
    """Bar grid derived from tempo/time-signature. Shares the audio timeline (seconds)."""
    bar = p.time_sig_num * (60.0 / p.bpm) * (4.0 / p.time_sig_den)
    a = _original_audio(p)
    end = max([a.duration_sec if a else 0.0] + [n.start_time + n.duration for n in track.notes] + [bar])
    count = min(5000, max(1, math.ceil((end - p.offset_sec) / bar)))
    track.measures.clear()
    db.flush()
    for i in range(count):
        track.measures.append(TabMeasure(index=i, start_time=round(p.offset_sec + i * bar, 6), duration=bar,
                                         bpm=p.bpm, time_sig_num=p.time_sig_num, time_sig_den=p.time_sig_den))


def _tab_out(p: Project, track: TabTrack) -> TabOut:
    return TabOut.model_validate({"version": track.version, "tuning": p.tuning,
                                  "notes": track.notes, "measures": track.measures}, from_attributes=True)


# ---------- projects ----------
@router.get("", response_model=list[ProjectOut])
def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ps = db.scalars(select(Project).where(Project.owner_id == user.id).order_by(Project.updated_at.desc())).all()
    return [_project_out(p, db) for p in ps]


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = Project(owner_id=user.id, **body.model_dump())
    db.add(p)
    db.flush()
    _rebuild_measures(p, _ensure_track(p, db), db)
    db.commit()
    return _project_out(p, db)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _project_out(get_owned_project(project_id, user, db), db)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: uuid.UUID, body: ProjectPatch, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    p = get_owned_project(project_id, user, db)
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    track = _ensure_track(p, db)
    if "tuning" in data and track.notes:
        n_strings = len(data["tuning"])
        if any(n.string_number > n_strings for n in track.notes):
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "Ada nada di senar yang akan dihapus. Pindahkan/hapus nada itu dulu.")
    for k, v in data.items():
        setattr(p, k, v)
    for n in track.notes:
        _fill_pitch(n, p.tuning)
    _rebuild_measures(p, track, db)
    if data:
        track.version += 1
    db.commit()
    return _project_out(p, db)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = get_owned_project(project_id, user, db)
    from .. import jobqueue
    from ..models import AnalysisJob
    for j in db.scalars(select(AnalysisJob).where(AnalysisJob.project_id == p.id,
                                                  AnalysisJob.status.in_(["queued", "processing"]))):
        try:
            jobqueue.cancel(j.rq_job_id)
        except Exception:
            pass
    d = get_settings().storage_dir / str(p.owner_id) / str(p.id)
    db.delete(p)
    db.commit()
    shutil.rmtree(d, ignore_errors=True)


# ---------- audio ----------
@router.post("/{project_id}/audio", response_model=ProjectOut, status_code=201)
@limiter.limit(lambda: get_settings().rate_limit_upload)
async def upload_audio(request: Request, project_id: uuid.UUID, file: UploadFile = File(...),
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = get_settings()
    p = get_owned_project(project_id, user, db)
    ext = Path(file.filename or "").suffix.lower().lstrip(".")
    if ext not in s.allowed_ext:
        raise HTTPException(415, f"Ekstensi .{ext or '?'} tidak didukung. Gunakan: {', '.join(sorted(s.allowed_ext))}.")

    pdir = _project_dir(p)
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
            # FFmpeg work runs in a worker thread so the event loop keeps serving other users.
            info = await run_in_threadpool(audio_svc.probe, tmp)
            waveform = await run_in_threadpool(audio_svc.decode_check_and_waveform, tmp, info.duration)
        except audio_svc.AudioValidationError as e:
            raise HTTPException(422, str(e))

        aid = uuid.uuid4()
        orig = pdir / f"{aid.hex}.{info.format}"
        play = pdir / f"{aid.hex}.play.m4a"
        wave = pdir / f"{aid.hex}.waveform.json"
        tmp.rename(orig)
        try:
            await run_in_threadpool(audio_svc.make_playback, orig, play)
        except audio_svc.AudioValidationError as e:
            orig.unlink(missing_ok=True)
            raise HTTPException(422, str(e))
        wave.write_text(json.dumps({"duration": info.duration, "points": waveform}))
    finally:
        tmp.unlink(missing_ok=True)

    old = _original_audio(p)
    if old:
        for f in (old.storage_path, old.playback_path, old.waveform_path):
            Path(f).unlink(missing_ok=True)
        p.audio_files.remove(old)
        db.flush()
    p.audio_files.append(AudioFile(
        id=aid, kind="original", original_filename=(file.filename or "audio")[:255],
        storage_path=str(orig), playback_path=str(play), waveform_path=str(wave), format=info.format,
        codec=info.codec, size_bytes=size, duration_sec=info.duration, sample_rate=info.sample_rate,
        channels=info.channels, sha256=await run_in_threadpool(audio_svc.sha256_file, orig)))
    p.status = "ready"
    db.flush()
    _rebuild_measures(p, _ensure_track(p, db), db)
    db.commit()
    db.refresh(p)
    return _project_out(p, db)


def _owned_audio(project_id: uuid.UUID, audio_id: uuid.UUID, user: User, db: Session) -> AudioFile:
    p = get_owned_project(project_id, user, db)
    a = next((x for x in p.audio_files if x.id == audio_id), None)
    if not a:
        raise HTTPException(404, "Audio not found")
    return a


@router.get("/{project_id}/audio/{audio_id}/stream")
def stream_audio(project_id: uuid.UUID, audio_id: uuid.UUID, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    a = _owned_audio(project_id, audio_id, user, db)
    # FileResponse honours HTTP Range requests -> precise seeking in the browser.
    return FileResponse(a.playback_path, media_type="audio/mp4", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/{project_id}/audio/{audio_id}/original")
def download_original(project_id: uuid.UUID, audio_id: uuid.UUID, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    a = _owned_audio(project_id, audio_id, user, db)
    return FileResponse(a.storage_path, filename=a.original_filename, media_type="application/octet-stream")


@router.get("/{project_id}/audio/{audio_id}/waveform")
def waveform(project_id: uuid.UUID, audio_id: uuid.UUID, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    a = _owned_audio(project_id, audio_id, user, db)
    return FileResponse(a.waveform_path, media_type="application/json")


# ---------- tab ----------
@router.get("/{project_id}/tab", response_model=TabOut)
def get_tab(project_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = get_owned_project(project_id, user, db)
    track = _ensure_track(p, db)
    if not track.measures:
        _rebuild_measures(p, track, db)
    db.commit()
    return _tab_out(p, track)


@router.put("/{project_id}/tab", response_model=TabOut)
def save_tab(project_id: uuid.UUID, body: TabIn, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    p = get_owned_project(project_id, user, db)
    track = _ensure_track(p, db)
    if body.version != track.version:
        raise HTTPException(409, "Tab sudah diubah di tempat lain. Muat ulang sebelum menyimpan.")
    n_strings = len(p.tuning)
    for n in body.notes:
        if n.string_number > n_strings:
            raise HTTPException(422, f"string_number {n.string_number} melebihi jumlah senar ({n_strings}).")
    track.notes.clear()
    db.flush()
    for n in sorted(body.notes, key=lambda x: (x.start_time, x.string_number)):
        tn = TabNote(**n.model_dump(exclude={"id"}), id=n.id or uuid.uuid4())
        _fill_pitch(tn, p.tuning)
        track.notes.append(tn)
    track.version += 1
    db.flush()
    _rebuild_measures(p, track, db)
    db.commit()
    db.refresh(track)
    return _tab_out(p, track)
