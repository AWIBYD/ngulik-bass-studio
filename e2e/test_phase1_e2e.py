"""Phase 1 end-to-end test in a real Chrome: upload WAV -> edit tab -> synchronized playback.

Usage:  python e2e/test_phase1_e2e.py http://localhost:3000 [chrome-path]
Requires: pip install playwright==1.52.0 ; ffmpeg on PATH. Uses synthetic, rights-free audio.
"""
import json
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000"
CHROME = sys.argv[2] if len(sys.argv) > 2 else None
SHOTS = Path(__file__).parent / "screenshots"
SHOTS.mkdir(exist_ok=True)
PADL, TOP, LANE, PPS = 44, 34, 30, 140  # must match TabView defaults
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = ""):
    results.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""), flush=True)


def make_song(path: Path):
    # 12 s, 120 BPM bass-range line: A1 A1 D2 E2 per beat, repeated.
    freqs = [55.0, 55.0, 73.42, 82.41] * 6
    inputs, labels = [], []
    for i, f in enumerate(freqs):
        inputs += ["-f", "lavfi", "-i", f"sine=f={f}:d=0.5:sample_rate=44100"]
        labels.append(f"[{i}]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex",
                    f"{''.join(labels)}concat=n={len(freqs)}:v=0:a=1,volume=4", "-ac", "2", str(path)], check=True)


def sample(page):
    return page.evaluate("""() => {
      const t = window.__nbs; const g = document.querySelector('[data-testid=playhead]');
      const m = /translate\\(([-\\d.]+)/.exec(g.getAttribute('transform') || '');
      const active = [...document.querySelectorAll('.tab-note[data-active="1"]')].map(e => +e.dataset.start);
      return { t: t.time(), media: t.el.currentTime, playing: t.playing, rate: t.el.playbackRate,
               head: m ? +m[1] : null, active, lat: t.latencySec, wall: performance.now() / 1000 };
    }""")


def main():
    tmp = Path(tempfile.mkdtemp())
    song = tmp / "e2e-bassline.wav"
    make_song(song)
    email = f"e2e-{uuid.uuid4().hex[:8]}@example.com"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME, args=["--autoplay-policy=no-user-gesture-required"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("pageerror", lambda e: print("PAGE ERROR:", e))

        # --- auth ---
        page.goto(f"{BASE}/register")
        page.fill("#name", "E2E Bassist")
        page.fill("#email", email)
        page.fill("#pw", "supersecret1")
        page.click("button:has-text('Daftar')")
        page.wait_for_url(f"{BASE}/")
        page.evaluate("localStorage.setItem('nbs-debug','1')")
        expect(page.locator("text=Halo, E2E Bassist")).to_be_visible(timeout=10000)
        check("Register + dashboard", True)

        # --- TEST 1: upload WAV ---
        page.goto(f"{BASE}/projects/new")
        page.set_input_files("input[type=file]", str(song))
        expect(page.locator("text=Menganalisis file…")).to_have_count(0, timeout=15000)
        check("Local preview shows duration", page.locator("text=0:12.0").count() > 0)
        page.fill("#pname", "E2E Groove")
        page.fill("#bpm", "120")
        page.click("button:has-text('Buat proyek & upload')")
        page.wait_for_url("**/projects/*-*", timeout=30000)
        page.wait_for_selector("[data-testid=tab-svg]")
        page.wait_for_function("() => !!window.__nbs && window.__nbs.duration > 11")
        check("TEST 1 upload WAV -> project ready", page.locator("text=Siap").count() > 0)

        # --- editor: add notes on beats (A string = 3, D string = 2) ---
        svg = page.locator("[data-testid=tab-svg]")
        plan = [(0.0, 3, None), (0.5, 3, None), (1.0, 2, None), (1.5, 2, "2"), (2.0, 3, None), (3.0, 2, None)]
        for t, s, fret in plan:
            svg.click(position={"x": PADL + t * PPS + 2, "y": TOP + (s - 0.5) * LANE + 12})
            if fret:
                page.keyboard.press(fret)
        n = page.locator(".tab-note").count()
        check("Add notes via click", n == len(plan), f"{n} notes")
        # undo / redo via keyboard
        page.keyboard.press("Delete")
        page.keyboard.press("Control+z")
        check("Delete + undo restores note", page.locator(".tab-note").count() == len(plan))
        page.click("button:has-text('Simpan tab')")
        expect(page.locator("text=Tab tersimpan.")).to_be_visible(timeout=10000)
        page.reload()
        page.wait_for_selector(".tab-note")
        page.wait_for_function("() => !!window.__nbs && window.__nbs.duration > 11")
        tab = page.evaluate("fetch(location.pathname.replace('/projects/','/api/projects/') + '/tab').then(r=>r.json())")
        pitches = [x["pitch"] for x in tab["notes"]]
        check("TEST 11 tab saved & reloaded", len(tab["notes"]) == len(plan) and pitches[3] == "E2", f"pitches={pitches}")

        # --- TEST 6/7/8: synchronized play ---
        page.click("button[aria-label=Play]")
        page.wait_for_function("() => window.__nbs.playing && window.__nbs.el.currentTime > 0.2", timeout=10000)
        samples = []
        t_end = time.time() + 3.0
        while time.time() < t_end:
            samples.append(sample(page))
            time.sleep(0.05)
        moving = samples[-1]["media"] - samples[0]["media"]
        check("TEST 6 audio is playing (media clock advances)", moving > 2.5, f"advanced {moving:.2f}s in 3s")
        head_err = [abs(s["head"] - (PADL + s["t"] * PPS)) for s in samples if s["head"] is not None]
        check("TEST 7 playhead follows clock", max(head_err) < 3 * PPS / 60 + 2, f"max {max(head_err):.1f}px")
        drift = [abs((s["t"] + s["lat"]) - s["media"]) for s in samples]
        check("TEST 7 clock vs audio element", statistics.median(drift) < 0.05 and max(drift) < 0.12,
              f"median {statistics.median(drift)*1000:.1f}ms max {max(drift)*1000:.1f}ms (latency {samples[0]['lat']*1000:.0f}ms)")
        starts = sorted(x["start_time"] for x in tab["notes"])
        durs = {x["start_time"]: x["duration"] for x in tab["notes"]}
        hl_ok = hl_total = 0
        for s in samples:
            expected = {st for st in starts if st <= s["t"] < st + durs[st]}
            if any(abs(s["t"] - st) < 0.04 or abs(s["t"] - (st + durs[st])) < 0.04 for st in starts):
                continue  # skip frame-boundary samples
            hl_total += 1
            hl_ok += set(s["active"]) == expected
        check("TEST 8 active fret highlight matches time", hl_total > 10 and hl_ok / hl_total > 0.95, f"{hl_ok}/{hl_total} samples")
        page.screenshot(path=str(SHOTS / "studio-playing-desktop.png"))

        # --- TEST 9: pause / resume / seek / loop ---
        page.click("button[aria-label=Pause]")
        time.sleep(0.2)
        a = sample(page); time.sleep(0.6); b = sample(page)
        check("TEST 9 pause freezes playhead", abs(a["t"] - b["t"]) < 0.005 and abs(a["head"] - b["head"]) < 0.5)
        page.click("button[aria-label=Play]")
        page.wait_for_function("() => window.__nbs.playing")
        time.sleep(0.5)
        c = sample(page)
        check("TEST 9 resume continues from pause point", b["t"] < c["t"] < b["t"] + 0.9, f"{b['t']:.2f} -> {c['t']:.2f}")
        wf = page.locator("[role=slider][aria-label='Posisi lagu']")
        box = wf.bounding_box()
        page.mouse.click(box["x"] + box["width"] * 0.75, box["y"] + box["height"] / 2)
        time.sleep(0.4)
        d = sample(page)
        check("TEST 9 seek via waveform", 9.0 < d["t"] < 9.9 and abs(d["head"] - (PADL + d["t"] * PPS)) < 6, f"t={d['t']:.2f}")
        page.evaluate("window.__nbs.seek(2.2)")
        page.click("button:has-text('Loop bar ini')")  # bar 2 = 2.0 .. 4.0 s
        loop = page.evaluate("({...window.__nbs.loop})")
        ts = []
        t_end = time.time() + 4.5
        while time.time() < t_end:
            ts.append(sample(page)["t"]); time.sleep(0.03)
        wrapped = any(ts[i + 1] < ts[i] - 1 for i in range(len(ts) - 1))
        check("TEST 9 loop bar wraps & stays in range",
              loop["enabled"] and wrapped and min(ts) > 1.9 and max(ts) < 4.08,
              f"loop={loop['a']:.2f}-{loop['b']:.2f} range={min(ts):.2f}-{max(ts):.2f} wrapped={wrapped}")
        post = sample(page)
        hd = abs(post["head"] - (PADL + post["t"] * PPS))
        check("TEST 9 still in sync after loop", hd < 6 and abs(post["t"] + post["lat"] - post["media"]) < 0.12, f"{hd:.1f}px")
        page.click("button:has-text('Loop ON')")

        # --- TEST 10: playback speed ---
        page.select_option("select[aria-label=Kecepatan]", "0.5")
        page.evaluate("window.__nbs.seek(1)")
        time.sleep(0.4)
        e = sample(page); time.sleep(2.0); f = sample(page)
        ratio = (f["t"] - e["t"]) / (f["wall"] - e["wall"])
        check("TEST 10 speed 50% (pitch-preserving element)", f["rate"] == 0.5 and 0.42 < ratio < 0.58, f"song/wall={ratio:.3f}")
        pp = page.evaluate("window.__nbs.el.preservesPitch")
        check("TEST 10 preservesPitch enabled", pp is True)
        page.select_option("select[aria-label=Kecepatan]", "1")
        page.click("button[aria-label=Pause]")

        # --- mobile layout screenshot ---
        m = browser.new_context(viewport={"width": 393, "height": 852}, device_scale_factor=2, is_mobile=True, has_touch=True,
                                storage_state=ctx.storage_state())
        mp = m.new_page()
        mp.goto(page.url)
        mp.wait_for_selector(".tab-note")
        mp.screenshot(path=str(SHOTS / "studio-mobile.png"), full_page=True)
        mp.goto(f"{BASE}/")
        mp.wait_for_selector("text=Riwayat proyek")
        mp.screenshot(path=str(SHOTS / "dashboard-mobile.png"))
        page.goto(f"{BASE}/")
        page.wait_for_selector("text=Riwayat proyek")
        page.screenshot(path=str(SHOTS / "dashboard-desktop.png"))
        browser.close()

    failed = [r for r in results if not r[1]]
    (Path(__file__).parent / "last_run.json").write_text(json.dumps(results, indent=2))
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
