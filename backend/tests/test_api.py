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
