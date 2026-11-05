"""Phase 2 E2E in Chrome: extract stems through the UI with a real worker, then play stems in sync.

The local run uses the offline `demucs_unittest` network (NBS_ENABLE_TEST_MODEL=1 on backend+worker);
on the VPS run the same flow manually with real HTDemucs (docs/TEST_CHECKLIST.md).
Usage: python e2e/test_phase2_e2e.py http://localhost:3000 [chrome] [model-key]
"""
import json
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000"
CHROME = sys.argv[2] if len(sys.argv) > 2 else None
MODEL = sys.argv[3] if len(sys.argv) > 3 else "test_unittest"
SHOTS = Path(__file__).parent / "screenshots"
SHOTS.mkdir(exist_ok=True)
PADL, PPS = 44, 140
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""), flush=True)


def sample(page):
    return page.evaluate("""() => { const t = window.__nbs; const g = document.querySelector('[data-testid=playhead]');
      const m = /translate\\(([-\\d.]+)/.exec(g.getAttribute('transform') || '');
      return { t: t.time(), media: t.el.currentTime, playing: t.playing, head: m ? +m[1] : null, src: t.el.src, lat: t.latencySec }; }""")


def main():
    tmp = Path(tempfile.mkdtemp())
    song = tmp / "song.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=55:d=10", "-f", "lavfi", "-i",
                    "sine=f=880:d=10", "-filter_complex", "amix=inputs=2,volume=3", "-ac", "2", str(song)], check=True)
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=CHROME, args=["--autoplay-policy=no-user-gesture-required"])
        ctx = b.new_context(viewport={"width": 1440, "height": 1000})
        page = ctx.new_page()
        page.on("pageerror", lambda e: print("PAGE ERROR:", e))
        page.goto(f"{BASE}/register")
        page.fill("#name", "P2"); page.fill("#email", f"p2-{uuid.uuid4().hex[:6]}@example.com"); page.fill("#pw", "supersecret1")
        page.click("button:has-text('Daftar')"); page.wait_for_url(f"{BASE}/")
        page.evaluate("localStorage.setItem('nbs-debug','1')")

        page.goto(f"{BASE}/extractor")
        expect(page.locator("text=online").first).to_be_visible(timeout=10000)
        check("Extractor page shows worker online", True)

        page.goto(f"{BASE}/projects/new")
        page.set_input_files("input[type=file]", str(song))
        expect(page.locator("text=Menganalisis file…")).to_have_count(0, timeout=15000)
        page.fill("#pname", "P2 Song")
        page.click("button:has-text('Buat proyek & upload')")
        page.wait_for_url("**/projects/*-*", timeout=30000)
        page.wait_for_function("() => !!window.__nbs && window.__nbs.duration > 9")

        page.select_option("#sep-model", MODEL)
        page.click("button:has-text('Ekstrak bass')")
        expect(page.locator("button:has-text('Batalkan')").or_(page.locator("audio[controls]")).first).to_be_visible(timeout=10000)
        check("Job queued from UI (progress bar shown)", True)
        page.screenshot(path=str(SHOTS / "p2-extracting.png"))
        expect(page.locator("audio[controls]").first).to_be_visible(timeout=600000)
        n = page.locator("audio[controls]").count()
        check("TEST 2 stems produced by a model that actually ran", n >= 2, f"{n} stems listed")
        stems = page.evaluate("fetch(location.pathname.replace('/projects/','/api/projects/') + '/stems').then(r=>r.json())")
        types = [s["stem_type"] for s in stems]
        check("Bass stem present", "bass" in types, str(types))
        dl = page.evaluate(f"fetch('{stems[0]['download_url']}').then(async r=>[r.status,(await r.arrayBuffer()).byteLength])")
        check("Stem download works", dl[0] == 200 and dl[1] > 10000, f"{dl[1]} bytes")

        # --- TEST 3: play the bass stem; switch sources while playing keeps position & sync ---
        page.click("button[aria-label=Play]")
        page.wait_for_function("() => window.__nbs.playing && window.__nbs.el.currentTime > 0.3")
        time.sleep(1.5)
        before = sample(page)
        page.click("button:has-text('Bass')")
        page.wait_for_function("() => window.__nbs && window.__nbs.el.src.includes('/stems/') && window.__nbs.playing", timeout=15000)
        time.sleep(1.0)
        after = sample(page)
        check("TEST 3 bass stem plays (audible source = stem)", "/stems/" in after["src"] and after["playing"])
        check("Source switch keeps song position", before["t"] < after["t"] < before["t"] + 2.5,
              f"{before['t']:.2f}s -> {after['t']:.2f}s")
        samples = []
        for _ in range(30):
            samples.append(sample(page)); time.sleep(0.05)
        head_err = max(abs(s["head"] - (PADL + s["t"] * PPS)) for s in samples)
        drift = max(abs(s["t"] + s["lat"] - s["media"]) for s in samples)
        check("Playhead in sync while playing stem", head_err < 6 and drift < 0.12, f"{head_err:.1f}px, {drift*1000:.0f}ms")
        page.click("button:has-text('Tanpa bass')")
        page.wait_for_function("() => window.__nbs && window.__nbs.playing", timeout=15000)
        check("Backing track (tanpa bass) plays", True)
        page.click("button[aria-label=Pause]")
        page.screenshot(path=str(SHOTS / "p2-stems.png"), full_page=True)
        m = b.new_context(viewport={"width": 393, "height": 852}, device_scale_factor=2, is_mobile=True, storage_state=ctx.storage_state())
        mp = m.new_page(); mp.goto(page.url); mp.wait_for_selector("h2:has-text('Bass Extractor')")
        mp.locator("h2:has-text('Bass Extractor')").scroll_into_view_if_needed()
        mp.screenshot(path=str(SHOTS / "p2-mobile-extractor.png"))
        b.close()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
