import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .services.music import validate_tuning

Technique = Literal[
    "normal", "hammer_on", "pull_off", "slide_up", "slide_down", "ghost", "slap", "pop", "mute", "bend", "vibrato"
]


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    display_name: str


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    tuning: list[str] = Field(default_factory=lambda: ["E1", "A1", "D2", "G2"])
    bpm: float = Field(120.0, ge=20, le=320)
    time_sig_num: int = Field(4, ge=1, le=16)
    time_sig_den: Literal[2, 4, 8, 16] = 4
    offset_sec: float = Field(0.0, ge=0, le=600)

    @field_validator("tuning")
    @classmethod
    def _tuning(cls, v: list[str]) -> list[str]:
        return validate_tuning(v)


class ProjectPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    tuning: list[str] | None = None
    bpm: float | None = Field(None, ge=20, le=320)
    time_sig_num: int | None = Field(None, ge=1, le=16)
    time_sig_den: Literal[2, 4, 8, 16] | None = None
    offset_sec: float | None = Field(None, ge=0, le=600)

    @field_validator("tuning")
    @classmethod
    def _tuning(cls, v: list[str] | None) -> list[str] | None:
        return validate_tuning(v) if v is not None else v


class AudioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: str
    original_filename: str
    format: str
    codec: str
    size_bytes: int
    duration_sec: float
    sample_rate: int
    channels: int
    created_at: datetime


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    tuning: list[str]
    bpm: float
    time_sig_num: int
    time_sig_den: int
    offset_sec: float
    status: str
    created_at: datetime
    updated_at: datetime
    audio: AudioOut | None = None
    note_count: int = 0


class NoteIn(BaseModel):
    id: uuid.UUID | None = None
    string_number: int = Field(ge=1, le=6)
    fret_number: int = Field(ge=0, le=24)
    start_time: float = Field(ge=0, le=7200)
    duration: float = Field(gt=0, le=60)
    velocity: float | None = Field(None, ge=0, le=1)
    technique: Technique = "normal"
    confidence_score: float = Field(1.0, ge=0, le=1)
    source: Literal["manual", "ai"] = "manual"
    needs_review: bool = False


class NoteOut(NoteIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    pitch: str
    pitch_midi: int
    frequency: float


class MeasureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    index: int
    start_time: float
    duration: float
    bpm: float
    time_sig_num: int
    time_sig_den: int


class TabIn(BaseModel):
    version: int
    notes: list[NoteIn] = Field(max_length=20000)


class TabOut(BaseModel):
    version: int
    tuning: list[str]
    notes: list[NoteOut]
    measures: list[MeasureOut]


class SettingsIO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    default_tuning: list[str]
    default_playback_rate: float = Field(ge=0.5, le=1.0)
    auto_scroll: bool

    @field_validator("default_tuning")
    @classmethod
    def _tuning(cls, v: list[str]) -> list[str]:
        return validate_tuning(v)
