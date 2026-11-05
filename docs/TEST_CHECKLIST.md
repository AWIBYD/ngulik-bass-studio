# Checklist uji manual — Phase 1

Gunakan audio milik sendiri / yang kamu punya hak pakainya. Uji di **Chrome Android** dan **Chrome/Firefox desktop**.

## Upload
- [ ] WAV, MP3, FLAC, M4A masing-masing berhasil; durasi & ukuran tampil; waveform & preview muncul sebelum upload.
- [ ] File .exe/.txt yang di-rename .mp3 ditolak dengan pesan jelas.
- [ ] File > batas MB ditolak di browser **dan** (jika dipaksa) di server.
- [ ] File terpotong/rusak ditolak; proyek tetap "Belum ada audio".
- [ ] Progress upload bergerak, lalu "Memvalidasi di server…".

## Player sinkron (dengar + lihat)
- [ ] Tulis nada di setiap ketukan bar 1–4 sesuai lagu. Saat Play, highlight jatuh tepat saat nada terdengar.
- [ ] Biarkan main ≥ 3 menit: tidak ada drift yang terasa di akhir lagu.
- [ ] Pause → Play: lanjut dari titik yang sama.
- [ ] Seek di waveform saat main & saat berhenti: playhead langsung pindah, tetap sinkron.
- [ ] Loop bar ini / Set A–B: berulang tanpa geser; Loop OFF berhenti mengulang.
- [ ] Speed 50%, 75%, 100%: pitch tetap sama, tab ikut melambat.
- [ ] Ganti tab browser ~30 detik lalu kembali: playhead langsung di posisi yang benar.
- [ ] Headset Bluetooth: bila visual terasa lebih cepat dari suara, atur Sync offset (mis. +150 ms).
- [ ] Mode Tab, Tab + Fretboard, Fretboard: semua bergerak bersama.

## Editor
- [ ] Ketuk senar → nada baru; angka keyboard ubah fret (2 digit untuk 10–24).
- [ ] ←/→ geser timing, ↑/↓ pindah senar, Del hapus, Ctrl+Z / Ctrl+Y.
- [ ] "Posisi lain untuk nada ini" memindah ke senar lain dengan pitch sama.
- [ ] Simpan → reload halaman → semua nada kembali.
- [ ] Buka proyek yang sama di 2 tab, simpan di keduanya → yang kedua mendapat pesan konflik (tidak menimpa diam-diam).
- [ ] Ubah tuning 4 → 5 senar di Pengaturan lagu: pitch nada dihitung ulang.

## Keamanan
- [ ] Logout → buka URL proyek → diarahkan ke login.
- [ ] Akun B tidak bisa membuka URL proyek/audio akun A (404).
- [ ] 11× login salah dalam 1 menit → diblokir sementara (429).
