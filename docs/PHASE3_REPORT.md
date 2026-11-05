# Laporan PHASE 3 — AI Tabulator
Tanggal: 6 November 2026 · Versi: 0.3.0-phase3 · Branch: `phase3` (belum digabung ke `main` sampai Phase 2 lolos di VPS)

## Cara kerja
1. **Sumber**: bass stem (hasil Bass Extractor / upload sendiri) — atau lagu asli bila belum ada stem (kurang akurat).
2. **Deteksi nada**: pYIN (librosa, default) atau CREPE (torchcrepe, model *full*). Rentang otomatis mengikuti tuning (mis. 5 senar mulai B0).
3. **Onset (serangan petikan)**: dari lonjakan energi log — menangkap nada berulang yang sama (E-E-E-E) yang dilewatkan detektor standar.
4. **Segmentasi nada**: semitone stabil, celah pendek dijembatani, nada < 45 ms dibuang.
5. **Koreksi oktaf** otomatis (cek energi fundamental di spektrum).
6. **Confidence** tiap nada: konsistensi deteksi, stabilitas pitch, kejelasan harmonik (pembeda nada asli vs bocoran drum/noise).
7. **Ditandai "perlu dicek" (kuning)**: confidence rendah, nada di atas range bass umum (bocoran vokal/gitar), nada tidak harmonis, oktaf dikoreksi, nada di luar jangkauan bass (dipindah oktaf), dead note.
8. **Senar & fret**: algoritma Viterbi memilih posisi dengan perpindahan tangan paling sedikit (box 4 fret, open string, nada berulang di posisi sama, jeda panjang = boleh pindah posisi). Semua tuning.
9. **BPM & awal bar** dari lagu asli (drum lebih jelas), opsional diterapkan.
10. **Teknik** (ditebak, selalu dicek): hammer-on / pull-off (transisi legato tanpa petikan baru), slide (ada glide pitch), vibrato, dead note (petikan tanpa nada). **Slap/pop/bend tidak dideteksi** — isi manual di editor.

Mode **gabung** mempertahankan nada yang kamu tulis manual; mode **ganti** menimpa semua. Hasil mentah AI disimpan terpisah (`detected_notes`).

## Akurasi terukur (bassline sintetis 37 nada dengan kunci jawaban; pitch harus tepat, onset ±50 ms)
| Kondisi audio | pYIN F1 | CREPE F1 |
|---|---|---|
| Bersih | **1.00** | 0.97 |
| Realistis (noise, detune ±12 cent, bocoran drum+vokal) | **0.95** | 0.95 |
| Berat (noise keras, bocoran besar) | 0.82 | 0.85 |

- Onset rata-rata meleset **12–13 ms**. BPM terdeteksi 99,4 (asli 100).
- Selama pengembangan: F1 awal 0,74 → 1,00 setelah perbaikan onset, energy gate, dan koreksi oktaf.
- CREPE *tiny* diuji dan **dibuang** (F1 0,15 untuk bass).
- Kecepatan (2 thread CPU): pYIN ±0,4× durasi lagu; CREPE ±3,3× durasi lagu.

## Hasil uji
- API: **33 lulus** (termasuk 7 tes fingering: scale satu posisi, nada berulang tidak pindah, low B di 4 senar ditandai, drop D, riff tinggi).
- Worker nyata (Redis → rq → librosa): **3/3** — tab AI ≥ 90% benar pada audio realistis, BPM diterapkan, mode gabung mempertahankan nada manual, mode ganti menimpa.
- E2E Chrome: **7/7** — bass stem → "Buat tab otomatis" → 36/37 nada benar, tombol "perlu dicek" melompat ke nada kuning, highlight sinkron 44/44.

## Jujur soal keterbatasan
1. Angka akurasi di atas dari **audio sintetis**. Rekaman bass asli (apalagi hasil Demucs dari mix padat) biasanya lebih sulit → harapkan lebih banyak nada kuning. Uji dengan lagu kamu di VPS.
2. Teknik hanya ditebak; slap/pop/bend tidak terdeteksi.
3. Time signature tidak dideteksi (default 4/4, bisa diubah di Pengaturan lagu).
4. Akord/double-stop: engine monofonik (1 nada sekaligus).
