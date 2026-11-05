import Link from "next/link";

export default function Extractor() {
  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div>
        <p className="text-xs font-semibold tracking-[0.2em] text-volt">BASS EXTRACTOR</p>
        <h1 className="mt-1 text-2xl font-bold">Pemisahan bass (stem separation)</h1>
      </div>
      <div className="card space-y-3">
        <span className="chip bg-warn/15 text-warn">Belum aktif · Phase 2</span>
        <p className="text-ink-300">
          Modul ini akan memisahkan lagu menjadi stem <b>bass, drums, vocals, other</b> memakai model Demucs yang benar-benar
          berjalan di worker terpisah (job queue: queued → processing → completed/failed). Fitur ini sengaja belum ditampilkan
          sebagai tombol sampai lolos acceptance test.
        </p>
        <p className="text-sm text-ink-400">
          Sementara itu kamu sudah bisa upload lagu, menulis tab manual, dan latihan dengan player sinkron.
        </p>
        <Link href="/projects/new" className="btn-primary">Buat proyek</Link>
      </div>
    </div>
  );
}
