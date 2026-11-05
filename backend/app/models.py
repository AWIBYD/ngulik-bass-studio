"""Database schema. All times are seconds stored as double precision."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Double,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


def uid() -> uuid.UUID:
    return uuid.uuid4()


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class UserSettings(Base):
    __tablename__ = "user_settings"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    default_tuning: Mapped[list] = mapped_column(JSON, default=lambda: ["E1", "A1", "D2", "G2"])
    default_playback_rate: Mapped[float] = mapped_column(Double, default=1.0)
    auto_scroll: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uid)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    # tuning is low string -> high string, e.g. ["E1","A1","D2","G2"]
    tuning: Mapped[list] = mapped_column(JSON, default=lambda: ["E1", "A1", "D2", "G2"])
    bpm: Mapped[float] = mapped_column(Double, default=120.0)
    time_sig_num: Mapped[int] = mapped_column(Integer, default=4)
    time_sig_den: Mapped[int] = mapped_column(Integer, default=4)
    offset_sec: Mapped[float] = mapped_column(Double, default=0.0)  # time of bar 1 beat 1
    # draft | ready | queued | processing | completed | failed
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    audio_files: Mapped[list["AudioFile"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    tab_track: Mapped["TabTrack | None"] = relationship(cascade="all, delete-orphan", passive_deletes=True, uselist=False)


class AudioFile(Base):
    __tablename__ = "audio_files"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="original")  # original | bass_upload
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(Text)          # validated original, private
    playback_path: Mapped[str] = mapped_column(Text)         # normalized AAC for precise browser seeking
    waveform_path: Mapped[str] = mapped_column(Text)
    format: Mapped[str] = mapped_column(String(20))
    codec: Mapped[str] = mapped_column(String(40))
    size_bytes: Mapped[int] = mapped_column(Integer)
    duration_sec: Mapped[float] = mapped_column(Double)
    sample_rate: Mapped[int] = mapped_column(Integer)
    channels: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AudioStem(Base):  # Phase 2
    __tablename__ = "audio_stems"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    source_audio_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("audio_files.id", ondelete="SET NULL"))
    stem_type: Mapped[str] = mapped_column(String(20))  # bass | drums | vocals | other
    origin: Mapped[str] = mapped_column(String(20), default="separated")  # separated | user_upload
    model_name: Mapped[str | None] = mapped_column(String(80))
    storage_path: Mapped[str] = mapped_column(Text)
    duration_sec: Mapped[float | None] = mapped_column(Double)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AnalysisJob(Base):  # Phase 2/3
    __tablename__ = "analysis_jobs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    job_type: Mapped[str] = mapped_column(String(30))  # separation | transcription
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|processing|completed|failed
    progress: Mapped[float] = mapped_column(Double, default=0.0)
    model_name: Mapped[str | None] = mapped_column(String(80))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DetectedNote(Base):  # Phase 3 raw AI output, kept separate from the editable tab
    __tablename__ = "detected_notes"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uid)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    pitch_midi: Mapped[int] = mapped_column(Integer)
    frequency: Mapped[float] = mapped_column(Double)
    start_time: Mapped[float] = mapped_column(Double)
    duration: Mapped[float] = mapped_column(Double)
    velocity: Mapped[float | None] = mapped_column(Double)
    confidence_score: Mapped[float] = mapped_column(Double)


class TabTrack(Base):
    __tablename__ = "tab_tracks"
    __table_args__ = (UniqueConstraint("project_id"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80), default="Bass")
    version: Mapped[int] = mapped_column(Integer, default=0)  # optimistic concurrency
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    notes: Mapped[list["TabNote"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="TabNote.start_time"
    )
    measures: Mapped[list["TabMeasure"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="TabMeasure.index"
    )


class TabMeasure(Base):
    __tablename__ = "tab_measures"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uid)
    track_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tab_tracks.id", ondelete="CASCADE"), index=True)
    index: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[float] = mapped_column(Double)
    duration: Mapped[float] = mapped_column(Double)
    bpm: Mapped[float] = mapped_column(Double)
    time_sig_num: Mapped[int] = mapped_column(Integer)
    time_sig_den: Mapped[int] = mapped_column(Integer)


class TabNote(Base):
    __tablename__ = "tab_notes"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uid)  # note_id
    track_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tab_tracks.id", ondelete="CASCADE"), index=True)
    string_number: Mapped[int] = mapped_column(Integer)  # 1 = highest string (tab convention)
    fret_number: Mapped[int] = mapped_column(Integer)
    pitch: Mapped[str] = mapped_column(String(6))        # e.g. "A1"
    pitch_midi: Mapped[int] = mapped_column(Integer)
    frequency: Mapped[float] = mapped_column(Double)
    start_time: Mapped[float] = mapped_column(Double)
    duration: Mapped[float] = mapped_column(Double)
    velocity: Mapped[float | None] = mapped_column(Double)
    technique: Mapped[str] = mapped_column(String(20), default="normal")
    confidence_score: Mapped[float] = mapped_column(Double, default=1.0)
    source: Mapped[str] = mapped_column(String(10), default="manual")  # manual | ai
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)


class ExportFile(Base):  # Phase 5
    __tablename__ = "export_files"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uid)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    format: Mapped[str] = mapped_column(String(20))
    storage_path: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
