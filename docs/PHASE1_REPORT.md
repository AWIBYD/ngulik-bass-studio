# Laporan PHASE 1 — NGULIK BASS STUDIO
Tanggal: 5 November 2026 · Versi: 0.1.0-phase1

## 1. Audit environment (workspace build)
| Item | Hasil |
|---|---|
| OS / CPU / RAM | Linux x86_64, 2 vCPU, 7,8 GB RAM, **tanpa GPU** |
| Tools | Python 3.13, Node 22, FFmpeg 6.1, PostgreSQL 16, Redis 7, Docker 29, Chrome 153 |
| Jaringan | PyPI & npm bisa diakses. **Docker Hub dan server model Demucs (dl.fbaipublicfiles.com) diblokir** di workspace ini |
| Konsekuensi | Image Docker **belum bisa di-build/diuji di sini**. Kode diuji langsung (Postgres + uvicorn + Next standalone + Chrome). Di VPS kamu tidak ada blokir ini |

## 2. Hasil pengujian otomatis
- **Backend (pytest, PostgreSQL nyata): 19/19 lulus** — auth, hash Argon2, CSRF, isolasi kepemilikan, upload 4 format + Range streaming + waveform, penolakan 9 jenis file buruk (kosong, rusak, terpotong, hening, terlalu panjang, palsu, video, ekstensi salah, terlalu besar), simpan tab + konflik versi + ganti tuning, dashboard & settings.
- **Frontend (vitest): 14/14 lulus** — clock sinkron (lag browser 750 ms, pause/resume, seek, rate, koreksi drift, jitter), pencarian nada aktif, undo/redo, posisi alternatif, snap grid.
- **E2E di Chrome sungguhan: 17/17 lulus** — WAV di-upload, nada ditulis, disimpan, di-reload, lalu diputar:
  - playhead vs clock: maks ±2,4 px
  - clock vs posisi audio element: 17–39 ms (setelah kompensasi latensi 42 ms)
  - highlight nada aktif: 42/42 sampel benar
  - pause, resume, seek, loop bar (tetap di dalam 2,00–4,00 dtk) lulus; speed 50% = tepat 0,500× dengan preservesPitch
- Rate limit dicek manual: login ke-11 dalam 1 menit → 429.

## 3. Acceptance test — status
| Test | Status |
|---|---|
| 1 Upload WAV | ✅ otomatis |
| 2 Bass stem dari model sungguhan | ⏳ Phase 2 |
| 3 Bass stem bisa diputar | ⏳ Phase 2 |
| 4 Deteksi nada → timestamp | ⏳ Phase 3 |
| 5 Nada → bass tab | ✅ manual (otomatis = Phase 3) |
| 6 Audio + tab diputar bersamaan | ✅ otomatis (headless) · perlu dicek dengan telinga |
| 7 Playhead mengikuti audio | ✅ otomatis |
| 8 Highlight fret aktif | ✅ otomatis (tab + fretboard) |
| 9 Pause/resume/seek/loop tetap sinkron | ✅ otomatis |
| 10 Speed bisa diubah | ✅ otomatis |
| 11 Edit & simpan tab | ✅ otomatis |
| 12 Export PDF/MIDI | ⏳ Phase 5 |
| 13 Jalan di VPS lewat domain HTTPS | ⏳ butuh VPS kamu |

## 4. Masalah / keterbatasan yang belum selesai
1. **Docker belum di-build di sini** (Docker Hub diblokir). `docker compose config` valid; build pertama harus dilakukan di VPS — saya siapkan perbaikan jika ada error.
2. **Sinkron "dengar"**: test headless memakai output audio virtual. Sinkron terhadap suara nyata (speaker HP, headset Bluetooth) harus dicek manual (`TEST_CHECKLIST.md`). Tersedia setting *Sync offset*.
3. **Loop** dicek per frame (~16 ms): ada kemungkinan sisa ekor ≤ 1 frame sebelum kembali ke titik A. Akan diperhalus di Phase 4.
4. Skema DB dibuat dengan `create_all`. **Alembic** akan dipasang di awal Phase 2 sebelum ada data penting.
5. Rate limiter in-memory → backend 1 worker. Pindah ke Redis di Phase 2.
6. Score + Tab mode, metronome, count-in, auto pause → Phase 4 (belum ditampilkan sebagai tombol).
7. Preview waveform lokal men-decode seluruh file di browser; untuk file besar di HP lama bisa lambat (tidak memblokir upload; server tetap memvalidasi).

## 5. Yang dibutuhkan untuk PHASE 2
- Spesifikasi VPS: vCPU, RAM, disk, OS. Demucs di CPU butuh ≥ 4 GB RAM; di bawah itu saya rekomendasikan mode "upload bass stem sendiri" saja.
- Konfirmasi model: `htdemucs` (lebih cepat) atau `htdemucs_ft` (bass lebih bersih, ~4× lebih lambat di CPU) — rencana: keduanya tersedia sebagai pilihan.
- Hasil deploy Phase 1 di VPS (TEST 13) sebelum Phase 2 dimulai.
