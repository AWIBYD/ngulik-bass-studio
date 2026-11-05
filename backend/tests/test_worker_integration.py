"""Full pipeline: API -> Redis queue -> real `rq worker` process -> Demucs -> stems on disk -> API.

Uses Demucs' bundled `demucs_unittest` network (untrained, no download) so it runs offline.
It proves the plumbing works end-to-end; separation QUALITY with pretrained htdemucs is
verified on the VPS (see docs/TEST_CHECKLIST.md, Phase 2).
Run inside the worker environment:  NBS_ENABLE_TEST_MODEL=1 pytest tests/test_worker_integration.py
"""
import json
import os
import subprocess
import sys
import time

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("demucs")

from .conftest import register  # noqa: E402

pytestmark = pytest.mark.skipif(os.environ.get("NBS_ENABLE_TEST_MODEL") != "1",
                                reason="set NBS_ENABLE_TEST_MODEL=1")


@pytest.fixture()
def worker(client, tmp_path):
    from app.jobqueue import redis_conn
    redis_conn().flushdb()
    env = {**os.environ, "STORAGE_DIR": os.environ["STORAGE_DIR"], "WORKER_THREADS": "2"}
    proc = subprocess.Popen([sys.executable, "-m", "rq.cli", "worker", "-u", os.environ["REDIS_URL"], "separation",
                             "--name", f"test-{os.getpid()}"],
                            cwd=os.path.dirname(os.path.dirname(__file__)), env=env,
                            stdout=open(tmp_path / "worker.log", "w"), stderr=subprocess.STDOUT)
    from app.jobqueue import workers_online
    for _ in range(50):
        if workers_online():
            break
        time.sleep(0.2)
    yield proc
    proc.terminate()
    proc.wait(10)
    print((tmp_path / "worker.log").read_text()[-3000:])


def _wait(client, pid, timeout=180):
    t0 = time.time()
    seen = []
    while time.time() - t0 < timeout:
        j = client.get(f"/api/projects/{pid}/jobs").json()[0]
        seen.append((j["status"], j["progress"]))
        if j["status"] in ("completed", "failed"):
            return j, seen
        time.sleep(0.5)
    raise AssertionError(f"job did not finish: {seen[-5:]}")


def test_real_worker_separates_and_serves_stems(client, media, worker):
    register(client)
    pid = client.post("/api/projects", json={"name": "Worker"}).json()["id"]
    assert client.post(f"/api/projects/{pid}/audio",
                       files={"file": ("b.wav", media["bassline.wav"].read_bytes(), "audio/wav")}).status_code == 201
    st = client.get("/api/separation/status").json()
    assert st["workers_online"] >= 1
    r = client.post(f"/api/projects/{pid}/separate", json={"model": "test_unittest"})
    assert r.status_code == 202, r.text
    assert client.post(f"/api/projects/{pid}/separate", json={"model": "test_unittest"}).status_code in (409, 202)
    job, seen = _wait(client, pid)
    assert job["status"] == "completed", job
    assert job["progress"] == 1.0
    assert client.get(f"/api/projects/{pid}").json()["status"] == "completed"

    stems = client.get(f"/api/projects/{pid}/stems").json()
    assert [s["stem_type"] for s in stems] == ["bass", "drums", "vocals", "other", "no_bass"]
    for s in stems:
        assert abs(s["duration_sec"] - 6.0) < 0.05  # same timeline as the original
        play = client.get(s["stream_url"])
        assert play.status_code == 200 and len(play.content) > 1000
        dl = client.get(s["download_url"])
        assert dl.status_code == 200 and dl.content[:4] == b"fLaC"
        w = client.get(s["waveform_url"]).json()
        assert len(w["points"]) == 2000

    # stems are genuinely new audio, not a renamed copy of the original
    orig = client.get(f"/api/projects/{pid}").json()["audio"]
    ostream = client.get(f"/api/projects/{pid}/audio/{orig['id']}/stream").content
    assert all(client.get(s["stream_url"]).content != ostream for s in stems)


def test_cancel_queued_job(client, media):
    """Without a worker running, a queued job can be cancelled cleanly."""
    from app.jobqueue import redis_conn
    redis_conn().flushdb()
    # register a fake worker heartbeat is not possible -> start & stop a worker quickly is overkill;
    # instead enqueue directly through the API helper path
    register(client)
    pid = client.post("/api/projects", json={"name": "Cancel"}).json()["id"]
    client.post(f"/api/projects/{pid}/audio", files={"file": ("b.wav", media["bassline.wav"].read_bytes(), "audio/wav")})
    from app import jobqueue
    import uuid
    from app.db import get_db
    from app.models import AnalysisJob
    gen = get_db(); db = next(gen)
    j = AnalysisJob(project_id=uuid.UUID(pid), job_type="separation", status="queued", model_name="test_unittest")
    db.add(j); db.commit()
    j.rq_job_id = jobqueue.enqueue_separation(str(j.id)); db.commit()
    jid = str(j.id); gen.close()
    r = client.post(f"/api/projects/{pid}/jobs/{jid}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "failed"
    assert jobqueue.rq_status(r.json() and j.rq_job_id) == "canceled"


def test_real_worker_transcribes_bass_to_tab(client, media, worker, tmp_path):
    """Synthetic plucked bass line with a known answer key -> AI tab via the real worker."""
    from .synth import groove, render
    truth = groove(100)
    wav = tmp_path / "groove.wav"
    render(truth, truth[-1][0] + 1.5, wav, noise=0.01, detune_cents=12, bleed=0.15)
    register(client)
    pid = client.post("/api/projects", json={"name": "AI tab", "bpm": 120}).json()["id"]
    assert client.post(f"/api/projects/{pid}/audio", files={"file": ("g.wav", wav.read_bytes(), "audio/wav")}).status_code == 201
    assert client.post(f"/api/projects/{pid}/stems/bass-upload",
                       files={"file": ("bass.wav", wav.read_bytes(), "audio/wav")}).status_code == 201
    # one manual note that must survive "merge"
    tab = client.get(f"/api/projects/{pid}/tab").json()
    client.put(f"/api/projects/{pid}/tab", json={"version": tab["version"], "notes": [
        {"string_number": 4, "fret_number": 0, "start_time": 0.5, "duration": 0.25}]})

    r = client.post(f"/api/projects/{pid}/transcribe", json={"source": "bass_stem", "method": "pyin",
                                                              "mode": "merge", "apply_bpm": True})
    assert r.status_code == 202, r.text
    job, _ = _wait(client, pid, timeout=300)
    assert job["status"] == "completed", job
    res = job["result"]
    assert res["kept_manual"] == 1 and res["bpm_applied"] and 95 <= res["bpm"] <= 105, res

    tab = client.get(f"/api/projects/{pid}/tab").json()
    ai = [n for n in tab["notes"] if n["source"] == "ai"]
    manual = [n for n in tab["notes"] if n["source"] == "manual"]
    assert len(manual) == 1
    # accuracy vs answer key (pitch exact, onset within 50 ms); the manual note covers truth[0]
    hit = sum(any(abs(n["start_time"] - s) <= 0.05 and n["pitch_midi"] == m for n in tab["notes"]) for s, _, m in truth)
    assert hit / len(truth) >= 0.9, f"only {hit}/{len(truth)} notes correct"
    for n in ai:  # every AI note is playable on this tuning and carries a confidence
        assert 1 <= n["string_number"] <= 4 and 0 <= n["fret_number"] <= 24
        assert 0 <= n["confidence_score"] <= 1
    proj = client.get(f"/api/projects/{pid}").json()
    assert 95 <= proj["bpm"] <= 105 and tab["measures"][0]["bpm"] == proj["bpm"]

    # replace mode drops the manual note
    r = client.post(f"/api/projects/{pid}/transcribe", json={"source": "auto", "mode": "replace", "apply_bpm": False})
    job, _ = _wait(client, pid, timeout=300)
    assert job["status"] == "completed" and job["result"]["kept_manual"] == 0
    assert all(n["source"] == "ai" for n in client.get(f"/api/projects/{pid}/tab").json()["notes"])
