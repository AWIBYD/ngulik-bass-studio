"""Phase 3 E2E in Chrome: bass stem -> 'Buat tab otomatis' -> AI tab loaded, accurate, reviewable, synced.

Uses a synthetic plucked bass line with an exact answer key (rights-free).
Usage: python e2e/test_phase3_e2e.py http://localhost:3000 [chrome]
"""
import sys
import tempfile
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from playwright.sync_api import expect, sync_playwright  # noqa: E402

from tests.synth import groove, render  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000"
CHROME = sys.argv[2] if len(sys.argv) > 2 else None
SHOTS = Path(__file__).parent / "screenshots"
PADL, PPS = 44, 140
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""), flush=True)


def main():
    truth = groove(100)
    wav = Path(tempfile.mkdtemp()) / "groove-bass.wav"
    render(truth, truth[-1][0] + 1.5, wav, noise=0.01, detune_cents=12, bleed=0.15)
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=CHROME, args=["--autoplay-policy=no-user-gesture-required"])
        ctx = b.new_context(viewport={"width": 1440, "height": 1000})
        page = ctx.new_page()
        page.on("pageerror", lambda e: print("PAGE ERROR:", e))
        page.goto(f"{BASE}/register")
        page.fill("#name", "P3"); page.fill("#email", f"p3-{uuid.uuid4().hex[:6]}@example.com"); page.fill("#pw", "supersecret1")
        page.click("button:has-text('Daftar')"); page.wait_for_url(f"{BASE}/")
        page.evaluate("localStorage.setItem('nbs-debug','1')")
        page.goto(f"{BASE}/projects/new")
        page.set_input_files("input[type=file]", str(wav))
        expect(page.locator("text=Menganalisis file…")).to_have_count(0, timeout=15000)
        page.fill("#pname", "P3 Groove"); page.fill("#bpm", "120")
        page.click("button:has-text('Buat proyek & upload')")
        page.wait_for_url("**/projects/*-*", timeout=30000)
        page.wait_for_function("() => !!window.__nbs && window.__nbs.duration > 10")
        # fallback path: user's own bass stem
        with page.expect_file_chooser() as fc:
            page.click("button:has-text('Upload bass stem sendiri')")
        fc.value.set_files(str(wav))
        expect(page.locator("text=upload sendiri")).to_be_visible(timeout=30000)
        check("Bass stem uploaded (fallback)", True)

        page.click("button:has-text('Buat tab otomatis')")
        expect(page.locator("text=Tab otomatis dimuat")).to_be_visible(timeout=300000)
        tab = page.evaluate("fetch(location.pathname.replace('/projects/','/api/projects/') + '/tab').then(r=>r.json())")
        notes = tab["notes"]
        hit = sum(any(abs(n["start_time"] - s) <= 0.05 and n["pitch_midi"] == m for n in notes) for s, _, m in truth)
        check("TEST 4 detection produced timestamped notes", len(notes) > 0 and all("start_time" in n for n in notes), f"{len(notes)} notes")
        check("TEST 5 AI tab accuracy vs answer key", hit / len(truth) >= 0.9, f"{hit}/{len(truth)} exact pitch, onset ±50 ms")
        proj = page.evaluate("fetch(location.pathname.replace('/projects/','/api/projects/')).then(r=>r.json())")
        check("BPM detected & applied", 95 <= proj["bpm"] <= 105, f"{proj['bpm']} (true 100)")
        shown = page.locator(".tab-note").count()
        check("AI notes rendered in tab", shown == len(notes), f"{shown}")
        review = page.locator("button:has-text('perlu dicek')")
        if review.count():
            review.click()
            sel = page.locator('.tab-note[data-selected="1"]').count()
            check("'Perlu dicek' jumps to & selects a flagged note", sel == 1)
        else:
            check("No flagged notes (nothing to review)", True)
        page.screenshot(path=str(SHOTS / "p3-ai-tab.png"))
        # play AI tab: highlight sync
        page.evaluate("window.__nbs.seek(0.4)")
        page.click("button[aria-label=Play]")
        page.wait_for_function("() => window.__nbs.playing && window.__nbs.el.currentTime > 0.6")
        ok = tot = 0
        for _ in range(60):
            st = page.evaluate("""() => ({ t: window.__nbs.time(),
              act: [...document.querySelectorAll('.tab-note[data-active="1"]')].map(e => +e.dataset.start) })""")
            exp = {n["start_time"] for n in notes if n["start_time"] <= st["t"] < n["start_time"] + n["duration"]}
            edge = any(abs(st["t"] - n["start_time"]) < 0.04 or abs(st["t"] - n["start_time"] - n["duration"]) < 0.04 for n in notes)
            if not edge:
                tot += 1
                ok += set(st["act"]) == exp
            time.sleep(0.05)
        check("TEST 6-8 AI tab highlights in sync with audio", tot > 20 and ok / tot > 0.95, f"{ok}/{tot}")
        page.click("button[aria-label=Pause]")
        b.close()
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
