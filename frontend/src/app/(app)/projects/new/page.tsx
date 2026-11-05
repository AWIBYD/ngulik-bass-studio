"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AudioDrop, type Picked } from "@/components/AudioDrop";
import { TuningPicker } from "@/components/TuningPicker";
import { api, json, uploadAudio, type Project, type UserSettings } from "@/lib/api";

export default function NewProject() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [tuning, setTuning] = useState(["E1", "A1", "D2", "G2"]);
  const [bpm, setBpm] = useState(120);
  const [sig, setSig] = useState("4/4");
  const [picked, setPicked] = useState<Picked | null>(null);
  const [stage, setStage] = useState<"idle" | "creating" | "uploading" | "validating">("idle");
  const [pct, setPct] = useState(0);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { api<UserSettings>("/settings").then((s) => setTuning(s.default_tuning)).catch(() => {}); }, []);
  useEffect(() => {
    if (picked && !name) setName(picked.file.name.replace(/\.[^.]+$/, "").slice(0, 120));
  }, [picked]); // eslint-disable-line react-hooks/exhaustive-deps

  const blocked = stage !== "idle" || !name.trim() || (picked !== null && (!!picked.error || !!picked.analyzing));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    const [num, den] = sig.split("/").map(Number);
    let project: Project | null = null;
    try {
      setStage("creating");
      project = await api<Project>("/projects", { method: "POST", body: json({ name: name.trim(), tuning, bpm, time_sig_num: num, time_sig_den: den }) });
      if (picked) {
        setStage("uploading");
        await uploadAudio(project.id, picked.file, (p) => { setPct(p); if (p >= 100) setStage("validating"); });
      }
      router.push(`/projects/${project.id}`);
    } catch (e) {
      setStage("idle");
      setErr(project ? `Proyek dibuat, tapi audio ditolak: ${(e as Error).message}` : (e as Error).message);
      if (project) setTimeout(() => router.push(`/projects/${project!.id}`), 2500);
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto max-w-2xl space-y-5">
      <div>
        <p className="text-xs font-semibold tracking-[0.2em] text-volt">NEW PROJECT</p>
        <h1 className="mt-1 text-2xl font-bold">Proyek baru</h1>
      </div>
      <div className="card space-y-4">
        <AudioDrop value={picked} onChange={setPicked} />
        <p className="text-xs text-ink-400">Audio bersifat privat — hanya akun kamu yang bisa memutar & mengunduhnya. Gunakan lagu yang kamu punya hak untuk dipakai.</p>
      </div>
      <div className="card grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <label className="label" htmlFor="pname">Nama proyek</label>
          <input id="pname" className="input" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} required />
        </div>
        <div className="sm:col-span-2">
          <label className="label">Tuning</label>
          <TuningPicker value={tuning} onChange={setTuning} />
        </div>
        <div>
          <label className="label" htmlFor="bpm">BPM</label>
          <input id="bpm" type="number" min={20} max={320} step={0.1} className="input" value={bpm} onChange={(e) => setBpm(Number(e.target.value))} />
        </div>
        <div>
          <label className="label" htmlFor="sig">Time signature</label>
          <select id="sig" className="input" value={sig} onChange={(e) => setSig(e.target.value)}>
            {["4/4", "3/4", "6/8", "2/4", "5/4", "7/8", "12/8"].map((s) => <option key={s}>{s}</option>)}
          </select>
        </div>
        <p className="text-xs text-ink-400 sm:col-span-2">BPM & bar bisa diubah kapan saja di studio. Deteksi BPM otomatis hadir di Phase 3.</p>
      </div>
      {err && <p className="text-sm text-bad">{err}</p>}
      {stage !== "idle" && (
        <div className="card space-y-2">
          <div className="flex justify-between text-sm">
            <span>{stage === "creating" ? "Membuat proyek…" : stage === "uploading" ? "Mengunggah…" : "Memvalidasi & menyiapkan audio di server…"}</span>
            {stage === "uploading" && <span>{pct}%</span>}
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-ink-700">
            <div className={`h-full bg-volt transition-all ${stage === "validating" ? "animate-pulse" : ""}`} style={{ width: `${stage === "creating" ? 5 : stage === "validating" ? 100 : pct}%` }} />
          </div>
        </div>
      )}
      <button className="btn-primary w-full" disabled={blocked}>{picked ? "Buat proyek & upload" : "Buat proyek tanpa audio"}</button>
    </form>
  );
}
