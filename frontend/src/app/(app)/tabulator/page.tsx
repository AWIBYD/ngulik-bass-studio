import Link from "next/link";

export default function Tabulator() {
  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div>
        <p className="text-xs font-semibold tracking-[0.2em] text-volt">TABULATOR</p>
        <h1 className="mt-1 text-2xl font-bold">Bass tab editor</h1>
      </div>
      <div className="card space-y-3">
        <span className="chip bg-volt/15 text-volt">Editor manual aktif</span>
        <p className="text-ink-300">Editor tab manual + player sinkron ada di halaman setiap proyek.</p>
        <span className="chip bg-warn/15 text-warn">Transkripsi otomatis · Phase 3</span>
        <p className="text-sm text-ink-400">
          Deteksi pitch (pYIN/CREPE), onset, dan mapping senar/fret otomatis akan mengisi tab dengan confidence score;
          nada ber-confidence rendah ditandai kuning untuk dikoreksi manual.
        </p>
        <Link href="/projects" className="btn-primary">Pilih proyek</Link>
      </div>
    </div>
  );
}
