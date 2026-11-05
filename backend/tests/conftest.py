import os
import subprocess
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://ngulik:ngulik@localhost:5432/ngulik_test")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-1234")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("RATE_LIMIT_AUTH", "1000/minute")
os.environ.setdefault("RATE_LIMIT_UPLOAD", "1000/minute")
os.environ.setdefault("MAX_UPLOAD_MB", "5")
os.environ.setdefault("MAX_DURATION_SEC", "60")


@pytest.fixture(scope="session")
def media(tmp_path_factory) -> dict[str, Path]:
    """Generated, rights-free test audio (synthetic bass-range tones)."""
    d = tmp_path_factory.mktemp("media")
    ff = ["ffmpeg", "-v", "error", "-y"]

    def run(args):
        subprocess.run(ff + args, check=True)

    # A1 (55 Hz) then D2 (73.42 Hz) then E1 (41.2 Hz) -> a tiny bass line, 6 s
    run(["-f", "lavfi", "-i", "sine=f=55:d=2", "-f", "lavfi", "-i", "sine=f=73.42:d=2",
         "-f", "lavfi", "-i", "sine=f=41.2:d=2", "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1",
         "-ar", "44100", str(d / "bassline.wav")])
    run(["-i", str(d / "bassline.wav"), "-b:a", "128k", str(d / "bassline.mp3")])
    run(["-i", str(d / "bassline.wav"), str(d / "bassline.flac")])
    run(["-i", str(d / "bassline.wav"), "-c:a", "aac", str(d / "bassline.m4a")])
    run(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "3", str(d / "silent.wav")])
    run(["-f", "lavfi", "-i", "sine=f=55:d=70:sample_rate=8000", str(d / "too_long.wav")])
    run(["-f", "lavfi", "-i", "testsrc=d=2", "-f", "lavfi", "-i", "sine=f=55:d=2", "-shortest",
         "-c:v", "mpeg4", "-c:a", "aac", str(d / "video.m4a")])
    good = (d / "bassline.wav").read_bytes()
    (d / "corrupt.wav").write_bytes(good[:44] + os.urandom(len(good) // 2))
    (d / "truncated.flac").write_bytes((d / "bassline.flac").read_bytes()[:3000])
    (d / "empty.wav").write_bytes(b"")
    (d / "fake.mp3").write_bytes(b"<?php system($_GET['x']); ?>" * 100)
    return {p.stem + p.suffix: p for p in d.iterdir()}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    from app.config import get_settings
    get_settings.cache_clear()
    from fastapi.testclient import TestClient

    from app import db as dbmod
    from app.main import app
    from app.db import Base

    eng = dbmod.get_engine()
    from app import models  # noqa
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    with TestClient(app, headers={"x-nbs-request": "1"}) as c:
        yield c


def register(c, email="bassist@example.com", pw="supersecret1"):
    r = c.post("/api/auth/register", json={"email": email, "password": pw, "display_name": "Bassist"})
    assert r.status_code == 201, r.text
    return r
