from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AnalysisJob, Project, User, UserSettings
from ..schemas import SettingsIO
from ..security import get_current_user
from ..services.music import PRESET_TUNINGS
from .projects import _project_out

router = APIRouter(prefix="/api", tags=["misc"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/tunings")
def tunings():
    return PRESET_TUNINGS


@router.get("/capabilities")
def capabilities():
    """Honest feature status so the UI never shows a fake button."""
    return {
        "upload": True, "manual_tab_editor": True, "sync_player": True,
        "bass_extraction": True, "ai_transcription": False, "export": False,
        "notes": "AI tabulator = Phase 3, export = Phase 5.",
    }


@router.get("/dashboard")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    projects = db.scalars(select(Project).where(Project.owner_id == user.id)
                          .order_by(Project.updated_at.desc())).all()
    processing = db.scalars(select(AnalysisJob).join(Project).where(
        Project.owner_id == user.id, AnalysisJob.status.in_(["queued", "processing"]))).all()
    outs = [_project_out(p, db) for p in projects]
    last_tab = next((o for o in outs if o.note_count > 0), None)
    return {
        "total_projects": len(outs),
        "recent": outs[:5],
        "processing": [{"id": str(j.id), "project_id": str(j.project_id), "type": j.job_type,
                        "status": j.status, "progress": j.progress} for j in processing],
        "last_tab": last_tab,
    }


def _settings(user: User, db: Session) -> UserSettings:
    s = db.get(UserSettings, user.id)
    if not s:
        s = UserSettings(user_id=user.id)
        db.add(s)
        db.commit()
    return s


@router.get("/settings", response_model=SettingsIO)
def get_settings_(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _settings(user, db)


@router.put("/settings", response_model=SettingsIO)
def put_settings(body: SettingsIO, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = _settings(user, db)
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    db.commit()
    return s
