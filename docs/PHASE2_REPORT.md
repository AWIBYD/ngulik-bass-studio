# Laporan PHASE 2 — Bass Extraction
Tanggal: 6 November 2026 · Versi: 0.2.0-phase2

## Yang dibangun
- **Job queue**: Redis + RQ. Status `queued → processing → completed / failed`, progress 0–100% dari callback Demucs, tahap yang bisa dibaca ("Memuat model…", "Menyimpan stem"), tombol batal.
- **Worker terpisah** (`backend/Dockerfile.worker`): Demucs 4.1.0 + PyTorch 2.6.0 CPU-only, 1 job sekaligus, dibatasi `3 GB RAM / 1.5 CPU` agar n8n tetap lancar. Crash/OOM tidak menggantung: job ditandai gagal dengan pesan jelas.
- **3 pilihan model**: HTDemucs (cepat, 4 stem) · HTDemucs-FT Bass (hanya model spesialis bass → bass paling bersih tanpa 4× waktu) · HTDemucs-FT (terbaik, ±4× lebih lama). Perkiraan waktu dihitung dari job sungguhan di server kamu.
- **Output**: stem bass, drums, vocals, other + **backing track tanpa bass** (untuk latihan). Masing-masing FLAC (download) + AAC (player) + waveform.
- **Player**: pilih sumber "Lagu asli / Bass / Drums / Vocal / Lainnya / Tanpa bass" — posisi, kecepatan, loop, volume ikut pindah, tab tetap sinkron.
- **Fallback**: upload bass stem sendiri (validasi sama ketatnya + peringatan bila durasi beda).
- **Migrasi database (Alembic)**: database Phase 1 di VPS otomatis di-*stamp* lalu di-upgrade; data lama tetap. Installer mem-backup database sebelum update (10 backup terakhir disimpan).

## Hasil uji
| Uji | Hasil |
|---|---|
| API (pytest, Postgres + Redis nyata) | **24/24 lulus** (termasuk privasi stem, job mati terdeteksi, fallback upload, upgrade DB Phase 1 → 0002 dengan data tetap) |
| Worker nyata (Redis → `rq worker` → Demucs → stem) | **2/2 lulus** — 5 stem, durasi sama dengan lagu asli, FLAC valid, stem ≠ salinan lagu asli, batal job |
| Pemilihan model spesialis bass (HTDemucs-FT Bass) | lulus — hanya 1 dari 4 model dijalankan |
| E2E Chrome Phase 2 | **9/9 lulus** — ekstrak dari UI, 5 stem, download, ganti sumber saat main tanpa lompat (playhead ±2 px) |
| Regresi Phase 1 (frontend unit) | 14/14 lulus |

## Jujur soal keterbatasan
1. **Kualitas pemisahan belum diuji di sini.** Workspace saya tidak bisa mengunduh bobot model (HuggingFace diblokir), jadi tes otomatis memakai `demucs_unittest` (jaringan Demucs asli tapi belum dilatih) — itu membuktikan seluruh jalur kerja, bukan kualitas suara. **TEST 2 & 3 dengan HTDemucs asli harus dicek di VPS** (checklist Phase 2).
2. **Waktu proses di CPU** belum terukur. Perkiraan kasar: HTDemucs ±1–2× durasi lagu di 1,5 CPU; HTDemucs-FT ±4–8×. Angka nyata akan tampil otomatis setelah job pertama.
3. **VPS tanpa swap.** Kalau RAM penuh, worker yang dihentikan (bukan n8n) dan job ditandai gagal. Disarankan tambah swap 4 GB (perintah di DEPLOYMENT.md).
4. Image worker ±1,5 GB; build pertama ±10–20 menit.

## Belum (fase berikutnya)
Phase 3: deteksi pitch (pYIN/CREPE) dari bass stem → tab otomatis dengan confidence.
