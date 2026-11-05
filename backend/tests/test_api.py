import pytest

from app.services.music import midi_to_freq, note_to_midi, string_open_midi, validate_tuning

from .conftest import register


# ---------- music theory ----------
def test_note_math():
    assert note_to_midi("E1") == 28 and note_to_midi("B0") == 23 and note_to_midi("C3") == 48
    assert note_to_midi("Bb1") == note_to_midi("A#1")
    assert abs(midi_to_freq(33) - 55.0) < 1e-9
    t = ["E1", "A1", "D2", "G2"]
    assert string_open_midi(t, 1) == note_to_midi("G2")  # string 1 = highest
    assert string_open_midi(t, 4) == note_to_midi("E1")
    with pytest.raises(ValueError):
        validate_tuning(["E1", "A1", "D2"])
    with pytest.raises(ValueError):
        note_to_midi("H2")


# ---------- auth / security ----------
def test_auth_flow(client):
    assert client.get("/api/auth/me").status_code == 401
    register(client)
    assert client.get("/api/auth/me").json()["email"] == "bassist@example.com"
    assert client.post("/api/auth/register", json={"email": "bassist@example.com", "password": "xxxxxxxx1",
                                                     "display_name": "x"}).status_code == 409
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": "bassist@example.com", "password": "wrongpass"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "bassist@example.com", "password": "supersecret1"}).status_code == 200


def test_csrf_header_required(client):
    r = client.post("/api/auth/register", headers={"x-nbs-request": ""},
                    json={"email": "a@example.com", "password": "supersecret1", "display_name": "A"})
    assert r.status_code == 403


def test_password_is_hashed(client):
    register(client)
    from sqlalchemy import select

    from app.db import get_db
    from app.models import User
    gen = get_db()
    db = next(gen)
    u = db.scalar(select(User))
    gen.close()
    assert u.password_hash.startswith("$argon2") and "supersecret1" not in u.password_hash


def test_ownership_isolation(client, media):
    register(client, "a@example.com")
    pid = client.post("/api/projects", json={"name": "Song A"}).json()["id"]
    up = client.post(f"/api/projects/{pid}/audio", files={"file": ("a.wav", media["bassline.wav"].read_bytes(), "audio/wav")})
    aid = up.json()["audio"]["id"]
    client.post("/api/auth/logout")
    register(client, "b@example.com")
    assert client.get(f"/api/projects/{pid}").status_code == 404
    assert client.get(f"/api/projects/{pid}/tab").status_code == 404
    assert client.get(f"/api/projects/{pid}/audio/{aid}/stream").status_code == 404
    assert client.delete(f"/api/projects/{pid}").status_code == 404
    assert client.get("/api/projects").json() == []


# ---------- upload validation (TEST 1) ----------
@pytest.mark.parametrize("name", ["bassline.wav", "bassline.mp3", "bassline.flac", "bassline.m4a"])
def test_upload_valid_formats(client, media, name):
    register(client)
    pid = client.post("/api/projects", json={"name": "Groove"}).json()["id"]
    r = client.post(f"/api/projects/{pid}/audio", files={"file": (name, media[name].read_bytes(), "audio/x")})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "ready"
    assert abs(body["audio"]["duration_sec"] - 6.0) < 0.15
    aid = body["audio"]["id"]
    s = client.get(f"/api/projects/{pid}/audio/{aid}/stream")
    assert s.status_code == 200 and s.headers["content-type"] == "audio/mp4" and len(s.content) > 1000
    # Range support is required for seeking in the browser
    rng = client.get(f"/api/projects/{pid}/audio/{aid}/stream", headers={"Range": "bytes=0-99"})
    assert rng.status_code == 206 and len(rng.content) == 100
    w = client.get(f"/api/projects/{pid}/audio/{aid}/waveform").json()
    assert len(w["points"]) == 2000 and 0.1 < max(w["points"]) < 0.25  # lavfi sine amplitude = 1/8 (+ lossy codec overshoot)


@pytest.mark.parametrize("name,code", [
    ("empty.wav", 400), ("corrupt.wav", 422), ("truncated.flac", 422), ("silent.wav", 422),
    ("too_long.wav", 422), ("fake.mp3", 422), ("video.m4a", 422),
])
def test_upload_rejects_bad_files(client, media, name, code):
    register(client)
    pid = client.post("/api/projects", json={"name": "Bad"}).json()["id"]
    r = client.post(f"/api/projects/{pid}/audio", files={"file": (name, media[name].read_bytes(), "audio/wav")})
    assert r.status_code == code, (name, r.text)
    assert client.get(f"/api/projects/{pid}").json()["audio"] is None


def test_upload_rejects_extension_and_size(client):
    register(client)
    pid = client.post("/api/projects", json={"name": "X"}).json()["id"]
    assert client.post(f"/api/projects/{pid}/audio", files={"file": ("x.exe", b"MZ" * 100, "audio/wav")}).status_code == 415
    big = b"\0" * (5 * 1024 * 1024 + 10)
    assert client.post(f"/api/projects/{pid}/audio", files={"file": ("x.wav", big, "audio/wav")}).status_code == 413


# ---------- tab editor persistence (TEST 11 backend) ----------
def test_tab_save_and_versioning(client):
    register(client)
    pid = client.post("/api/projects", json={"name": "Tab", "bpm": 100}).json()["id"]
    tab = client.get(f"/api/projects/{pid}/tab").json()
    assert tab["version"] == 0 and tab["notes"] == [] and tab["measures"][0]["duration"] == pytest.approx(2.4)
    notes = [
        {"string_number": 3, "fret_number": 0, "start_time": 0.0, "duration": 0.5},
        {"string_number": 2, "fret_number": 2, "start_time": 0.6, "duration": 0.5, "technique": "slide_up"},
    ]
    r = client.put(f"/api/projects/{pid}/tab", json={"version": 0, "notes": notes})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["version"] == 1
    assert [n["pitch"] for n in out["notes"]] == ["A1", "E2"]
    assert out["notes"][0]["frequency"] == pytest.approx(55.0)
    # stale version is rejected (no silent overwrite)
    assert client.put(f"/api/projects/{pid}/tab", json={"version": 0, "notes": []}).status_code == 409
    # string beyond tuning rejected
    bad = [{"string_number": 5, "fret_number": 0, "start_time": 0, "duration": 1}]
    assert client.put(f"/api/projects/{pid}/tab", json={"version": 1, "notes": bad}).status_code == 422
    # switch to 5-string: pitches recomputed from the new tuning
    p = client.patch(f"/api/projects/{pid}", json={"tuning": ["B0", "E1", "A1", "D2", "G2"]}).json()
    assert p["tuning"][0] == "B0"
    t2 = client.get(f"/api/projects/{pid}/tab").json()
    assert t2["notes"][0]["pitch"] == "A1"  # string 3 on 5-string is still A
    # shrinking back would orphan nothing here -> allowed; delete project removes everything
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert client.get(f"/api/projects/{pid}").status_code == 404


def test_dashboard_and_settings(client):
    register(client)
    client.post("/api/projects", json={"name": "One"})
    d = client.get("/api/dashboard").json()
    assert d["total_projects"] == 1 and d["recent"][0]["name"] == "One"
    s = client.get("/api/settings").json()
    s["default_playback_rate"] = 0.75
    assert client.put("/api/settings", json=s).json()["default_playback_rate"] == 0.75


# ---------- Phase 2: extraction API (no torch needed) ----------
def _project_with_audio(client, media, name="bassline.wav"):
    pid = client.post("/api/projects", json={"name": "Stem"}).json()["id"]
    r = client.post(f"/api/projects/{pid}/audio", files={"file": (name, media[name].read_bytes(), "audio/wav")})
    assert r.status_code == 201, r.text
    return pid


def test_separation_status_and_no_worker(client, media):
    register(client)
    st = client.get("/api/separation/status").json()
    assert st["redis_online"] is True
    assert {m["key"] for m in st["models"]} >= {"htdemucs", "htdemucs_ft_bass", "htdemucs_ft"}
    pid = client.post("/api/projects", json={"name": "No audio"}).json()["id"]
    assert client.post(f"/api/projects/{pid}/separate", json={"model": "htdemucs"}).status_code == 409
    pid = _project_with_audio(client, media)
    assert client.post(f"/api/projects/{pid}/separate", json={"model": "nope"}).status_code == 422
    if st["workers_online"] == 0:  # honest refusal instead of a job that never runs
        r = client.post(f"/api/projects/{pid}/separate", json={"model": "htdemucs"})
        assert r.status_code == 503 and "Worker" in r.json()["detail"]


def test_dead_job_is_reconciled(client, media):
    register(client)
    pid = _project_with_audio(client, media)
    from app.db import get_db
    from app.models import AnalysisJob
    gen = get_db(); db = next(gen)
    import uuid as _uuid
    db.add(AnalysisJob(project_id=_uuid.UUID(pid), job_type="separation", status="processing",
                       model_name="htdemucs", rq_job_id="does-not-exist"))
    from app.models import Project
    db.get(Project, _uuid.UUID(pid)).status = "processing"
    db.commit(); gen.close()
    jobs = client.get(f"/api/projects/{pid}/jobs").json()
    assert jobs[0]["status"] == "failed" and "Worker berhenti" in jobs[0]["error"]
    assert client.get(f"/api/projects/{pid}").json()["status"] == "failed"


def test_user_bass_upload_fallback(client, media):
    register(client)
    pid = _project_with_audio(client, media)
    r = client.post(f"/api/projects/{pid}/stems/bass-upload",
                    files={"file": ("my-bass.flac", media["bassline.flac"].read_bytes(), "audio/flac")})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["warning"] is None and body["stem"]["origin"] == "user_upload"
    stems = client.get(f"/api/projects/{pid}/stems").json()
    assert [s["stem_type"] for s in stems] == ["bass"]
    s = stems[0]
    assert client.get(s["stream_url"], headers={"Range": "bytes=0-9"}).status_code == 206
    dl = client.get(s["download_url"])
    assert dl.status_code == 200 and "Bass" in dl.headers["content-disposition"]
    # replacing keeps one bass stem; bad file rejected
    assert client.post(f"/api/projects/{pid}/stems/bass-upload",
                       files={"file": ("x.wav", media["corrupt.wav"].read_bytes(), "audio/wav")}).status_code == 422
    assert client.delete(f"/api/projects/{pid}/stems/{s['id']}").status_code == 204
    assert client.get(f"/api/projects/{pid}/stems").json() == []


def test_stems_are_private(client, media):
    register(client, "a@example.com")
    pid = _project_with_audio(client, media)
    sid = client.post(f"/api/projects/{pid}/stems/bass-upload",
                      files={"file": ("b.wav", media["bassline.wav"].read_bytes(), "audio/wav")}).json()["stem"]["id"]
    client.post("/api/auth/logout")
    register(client, "b@example.com")
    for path in ("stream", "download", "waveform"):
        assert client.get(f"/api/projects/{pid}/stems/{sid}/{path}").status_code == 404
    assert client.post(f"/api/projects/{pid}/separate", json={"model": "htdemucs"}).status_code == 404
    assert client.get(f"/api/projects/{pid}/jobs").status_code == 404


def test_migration_upgrades_existing_phase1_database(tmp_path):
    """A DB created by Phase 1 (create_all, no alembic_version) is stamped then upgraded, keeping data."""
    from alembic import command
    from sqlalchemy import create_engine, inspect, text

    from app.migrate import _config, run
    url = "postgresql+psycopg://ngulik:ngulik@localhost:5432/ngulik_mig"
    import os
    os.environ["DATABASE_URL"] = url
    from app import db as dbmod
    from app.config import get_settings
    get_settings.cache_clear()
    old_engine = dbmod._engine
    dbmod._engine = None
    try:
        eng = create_engine(url)
        with eng.begin() as c:
            c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO ngulik;"))
        cfg = _config()
        command.upgrade(cfg, "0001")
        with eng.begin() as c:
            c.execute(text("DROP TABLE alembic_version"))
            c.execute(text("INSERT INTO users (id,email,display_name,password_hash,created_at) "
                           "VALUES ('00000000-0000-0000-0000-000000000001','old@example.com','Old','x',now())"))
        run()
        cols = {c["name"] for c in inspect(eng).get_columns("audio_stems")}
        assert {"playback_path", "job_id"} <= cols
        with eng.connect() as c:
            assert c.execute(text("SELECT email FROM users")).scalar() == "old@example.com"
            assert c.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0002"
        eng.dispose()
    finally:
        dbmod._engine = old_engine
        os.environ["DATABASE_URL"] = "postgresql+psycopg://ngulik:ngulik@localhost:5432/ngulik_test"
        get_settings.cache_clear()
