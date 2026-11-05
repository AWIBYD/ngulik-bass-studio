# Arsitektur

```
Browser (Next.js app, Web Audio)
   │ HTTPS
 Caddy ── /api/* ──► FastAPI (backend) ──► PostgreSQL
   │                    │
   └── /* ──► Next.js    └── /data/storage (audio privat, per user/proyek)
                         └── FFmpeg (validasi, decode, normalisasi, waveform)
Phase 2: + Redis + worker (Celery/RQ) untuk Demucs. Phase 3: + librosa/pYIN/CREPE di worker.
```

## Satu timeline (prinsip utama)
Semua waktu disimpan dalam **detik (double precision)** pada timeline audio: `tab_notes.start_time/duration`, `tab_measures.start_time`, `projects.offset_sec`. Bar/beat dihitung dari BPM + birama + offset, sehingga audio, tab, dan fretboard membaca angka yang sama.

## Sinkronisasi player
`frontend/src/lib/clock.ts` + `transport.ts`
- Audio diputar oleh `HTMLAudioElement` (`preservesPitch` → speed 50–100% tanpa ubah pitch) yang dirutekan ke Web Audio (`MediaElementSource → Gain → destination`).
- Posisi = `anchorMedia + (audioClock − anchorAudio) × rate`, dengan `audioClock` dari `AudioContext.getOutputTimestamp()`. Tidak ada `setInterval`.
- Re-anchor saat play, pause, seek, rate change, loop, dan saat selisih dengan `audio.currentTime` > 80 ms (stall/buffering). Saat buffering clock dibekukan.
- Kompensasi latensi output (`baseLatency + outputLatency`) + offset manual (headset Bluetooth).
- Satu `requestAnimationFrame` loop membagikan `(t, nada aktif)` ke semua view; playhead & highlight diubah langsung di DOM (tanpa re-render React per frame). Nada aktif dicari dengan binary search.
- Audio disajikan sebagai AAC/M4A 44.1 kHz `+faststart` dengan HTTP Range → seek presisi & ringan untuk Android.

## Keamanan
Argon2 password hash · JWT di cookie httpOnly/Secure/SameSite=Lax · header `x-nbs-request` wajib pada POST/PUT/PATCH/DELETE (CSRF) · rate limit login/registrasi/upload · validasi ekstensi + ffprobe format/codec + decode penuh · nama file di disk = UUID (nama asli tidak dipakai di path) · cek kepemilikan setiap endpoint (404 untuk proyek orang lain) · semua credential lewat env · HSTS & security headers di Caddy · container non-root.

## Skema database
`users, user_settings, projects, audio_files, audio_stems, analysis_jobs, detected_notes, tab_tracks, tab_measures, tab_notes, export_files` — lihat `backend/app/models.py`. `detected_notes` (hasil AI mentah) dipisah dari `tab_notes` (yang bisa diedit), sehingga koreksi manual tidak hilang saat analisis diulang. `tab_notes` menyimpan `pitch, pitch_midi, frequency, string_number, fret_number, start_time, duration, velocity, technique, confidence_score, source, needs_review`.

## Rencana fase berikut
- **Phase 2**: worker Docker terpisah + Redis queue, Demucs `htdemucs` / `htdemucs_ft` (pilihan model), stem bass/drums/vocals/other, preview & download per stem, status queued/processing/completed/failed + progress, alternatif upload bass stem sendiri. Migrasi Alembic.
- **Phase 3**: pYIN (default, ringan CPU) dan CREPE tiny (opsional), onset, BPM, mapping senar/fret dengan biaya perpindahan tangan, confidence + flag `needs_review`.
- **Phase 4**: score + tab, practice (metronome, count-in, auto pause, section).
- **Phase 5**: PDF, PNG, MIDI, MusicXML (diuji impor di MuseScore), production test.
