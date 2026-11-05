"""Runtime configuration. Every secret/credential comes from environment variables."""
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "NGULIK BASS STUDIO"
    environment: str = Field("development", alias="APP_ENV")

    database_url: str = Field(..., alias="DATABASE_URL")
    jwt_secret: str = Field(..., alias="JWT_SECRET", min_length=32)
    jwt_expire_hours: int = Field(72, alias="JWT_EXPIRE_HOURS")
    cookie_secure: bool = Field(True, alias="COOKIE_SECURE")
    allow_registration: bool = Field(True, alias="ALLOW_REGISTRATION")

    storage_dir: Path = Field(Path("/data/storage"), alias="STORAGE_DIR")
    max_upload_mb: int = Field(50, alias="MAX_UPLOAD_MB")
    max_duration_sec: int = Field(900, alias="MAX_DURATION_SEC")
    allowed_formats: str = Field("mp3,wav,flac,m4a", alias="ALLOWED_FORMATS")

    rate_limit_auth: str = Field("10/minute", alias="RATE_LIMIT_AUTH")
    rate_limit_upload: str = Field("20/hour", alias="RATE_LIMIT_UPLOAD")

    redis_url: str = Field("redis://localhost:6379/0", alias="REDIS_URL")
    separation_job_timeout: int = Field(4 * 3600, alias="SEPARATION_JOB_TIMEOUT")
    rate_limit_separation: str = Field("10/hour", alias="RATE_LIMIT_SEPARATION")

    ffmpeg_bin: str = Field("ffmpeg", alias="FFMPEG_BIN")
    ffprobe_bin: str = Field("ffprobe", alias="FFPROBE_BIN")

    @property
    def allowed_ext(self) -> set[str]:
        return {e.strip().lower().lstrip(".") for e in self.allowed_formats.split(",") if e.strip()}

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
