# NGULIK BASS STUDIO

**FEEL THE GROOVE. READ THE NOTES.**

Studio web untuk pemain bass: upload lagu → (Phase 2) ekstrak bass → (Phase 3) transkripsi otomatis → edit tab → putar lagu dengan tab, playhead & fretboard yang sinkron → latihan → (Phase 5) export.

> Status: **PHASE 1 & 2 selesai** (lihat `docs/PHASE1_REPORT.md`, `docs/PHASE2_REPORT.md`). AI tabulator (Phase 3) dan export (Phase 5) **belum** aktif.

## Fitur Phase 1
- Akun (register/login), password Argon2, sesi cookie httpOnly, proteksi CSRF, rate limiting.
- Dashboard: total proyek, proyek terakhir, job yang diproses, tab terakhir, riwayat.
- Upload audio MP3/WAV/FLAC/M4A: drag & drop, file browser, preview lokal (durasi, ukuran, waveform, player), progress upload. Validasi server: ekstensi, ukuran, format/codec asli via ffprobe, decode penuh (file rusak/terpotong), file kosong, audio hening, durasi maksimum, tolak file video.
- Project management: buat, buka, edit (nama, BPM, birama, offset bar 1, tuning), hapus, unduh audio asli.
- Tuning 4/5/6 senar + custom (mis. Drop D, Eb).
- Editor tab manual: tambah/hapus nada, geser timing, ubah durasi/fret/senar/teknik (hammer-on, pull-off, slide, ghost, slap, pop, mute, bend, vibrato), pilih posisi alternatif untuk nada yang sama, snap 1/16, undo/redo, simpan dengan proteksi konflik versi.
- Player sinkron: play/pause/stop, bar sebelumnya/berikutnya, seek (waveform), loop A-B, loop 1 bar, volume, speed 50–100% (pitch-preserving), playhead, highlight nada aktif, auto-scroll, zoom, fretboard real-time, sync offset untuk headset Bluetooth.

## Fitur Phase 2
- Ekstraksi bass dengan Demucs (CPU) di worker terpisah + antrean Redis, progress real-time, batal.
- 3 model: HTDemucs, HTDemucs-FT Bass, HTDemucs-FT. Output bass/drums/vocals/other + backing track tanpa bass (FLAC + AAC).
- Player bisa ganti sumber (asli/bass/tanpa bass/…) tanpa kehilangan posisi & sinkron.
- Fallback upload bass stem sendiri. Migrasi DB Alembic + backup otomatis saat update.

## Struktur
```
backend/    FastAPI + SQLAlchemy + FFmpeg (app/, tests/, Dockerfile, requirements.txt)
frontend/   Next.js 15 + TypeScript + Tailwind (src/app, src/components, src/lib)
deploy/     Caddyfile (HTTPS otomatis)
e2e/        Test end-to-end di Chrome (Playwright)
docs/       ARCHITECTURE.md, TEST_CHECKLIST.md, PHASE1_REPORT.md
docker-compose.yml, .env.example, DEPLOYMENT.md
```

## Jalankan untuk development
Prasyarat: Python 3.12+, Node 22, FFmpeg, PostgreSQL 16.
```bash
# backend
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
export DATABASE_URL=postgresql+psycopg://ngulik:ngulik@localhost:5432/ngulik
export JWT_SECRET=$(openssl rand -hex 32) COOKIE_SECURE=false STORAGE_DIR=./storage
.venv/bin/uvicorn app.main:app --reload --port 8000

# frontend (terminal lain)
cd frontend && npm ci && BACKEND_URL=http://localhost:8000 npm run dev
# buka http://localhost:3000
```

## Test
```bash
cd backend && .venv/bin/python -m pytest -q          # 19 test API/validasi/keamanan (butuh DB ngulik_test)
cd frontend && npm test                               # 14 test clock sinkron + editor
python e2e/test_phase1_e2e.py http://localhost:3000   # 17 cek E2E di Chrome
```
Checklist manual (audio sungguhan, Android, headset): `docs/TEST_CHECKLIST.md`.

## Production
Lihat **DEPLOYMENT.md** (VPS + Docker Compose + domain + HTTPS).

## Versi (dipin)
Python 3.12 · FastAPI 0.115.12 · SQLAlchemy 2.0.40 · psycopg 3.2.9 · numpy 2.2.5 · Node 22.16 · Next.js 15.5.29 · React 19.1.10 · Tailwind 3.4.19 · PostgreSQL 16.9 · Caddy 2.10.0. Detail lengkap: `backend/requirements.txt`, `frontend/package.json` + `package-lock.json`.
