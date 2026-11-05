// Thin client for the FastAPI backend. Same-origin, cookie session, CSRF header on every call.
export type Audio = {
  id: string; kind: string; original_filename: string; format: string; codec: string;
  size_bytes: number; duration_sec: number; sample_rate: number; channels: number; created_at: string;
};
export type Project = {
  id: string; name: string; tuning: string[]; bpm: number; time_sig_num: number; time_sig_den: number;
  offset_sec: number; status: string; created_at: string; updated_at: string; audio: Audio | null; note_count: number;
};
export type Technique =
  | "normal" | "hammer_on" | "pull_off" | "slide_up" | "slide_down" | "ghost" | "slap" | "pop" | "mute" | "bend" | "vibrato";
export type Note = {
  id: string; string_number: number; fret_number: number; start_time: number; duration: number;
  technique: Technique; confidence_score: number; source: "manual" | "ai"; needs_review: boolean;
  velocity?: number | null; pitch?: string; pitch_midi?: number; frequency?: number;
};
export type Measure = { index: number; start_time: number; duration: number; bpm: number; time_sig_num: number; time_sig_den: number };
export type Tab = { version: number; tuning: string[]; notes: Note[]; measures: Measure[] };
export type User = { id: string; email: string; display_name: string };
export type UserSettings = { default_tuning: string[]; default_playback_rate: number; auto_scroll: boolean };

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

function detail(body: unknown, fallback: string): string {
  const d = (body as { detail?: unknown })?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d) && d[0]?.msg) return String(d[0].msg);
  return fallback;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("x-nbs-request", "1");
  if (init.body && !(init.body instanceof FormData)) headers.set("content-type", "application/json");
  const res = await fetch(`/api${path}`, { ...init, headers, credentials: "same-origin", cache: "no-store" });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, detail(body, `HTTP ${res.status}`));
  return body as T;
}

export const json = (data: unknown) => JSON.stringify(data);

/** Upload with real progress events (fetch has no upload progress). */
export function uploadAudio(projectId: string, file: File, onProgress: (pct: number) => void): Promise<Project> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/projects/${projectId}/audio`);
    xhr.setRequestHeader("x-nbs-request", "1");
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100));
    xhr.onload = () => {
      let body: unknown = null;
      try { body = JSON.parse(xhr.responseText); } catch { /* non-json */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as Project);
      else reject(new ApiError(xhr.status, detail(body, `Upload gagal (HTTP ${xhr.status})`)));
    };
    xhr.onerror = () => reject(new ApiError(0, "Koneksi terputus saat upload."));
    const fd = new FormData();
    fd.append("file", file);
    xhr.send(fd);
  });
}

export const streamUrl = (p: Project) => (p.audio ? `/api/projects/${p.id}/audio/${p.audio.id}/stream` : null);

// ---------- Phase 2: extraction ----------
export type Stem = {
  id: string; stem_type: "bass" | "drums" | "vocals" | "other" | "no_bass"; label: string; origin: "separated" | "user_upload";
  model: string | null; format: string | null; size_bytes: number | null; duration_sec: number | null; created_at: string;
  stream_url: string; download_url: string; waveform_url: string;
};
export type Job = {
  id: string; type: string; status: "queued" | "processing" | "completed" | "failed"; progress: number; stage: string | null;
  model: string | null; error: string | null; created_at: string; started_at: string | null; finished_at: string | null;
};
export type SepModel = { key: string; label: string; description: string; stems: string[]; relative_cost: number; measured_ratio: number | null };
export type SepStatus = { redis_online: boolean; workers_online: number; queue_length: number; default_model: string; models: SepModel[] };

export function uploadBassStem(projectId: string, file: File, onProgress: (pct: number) => void): Promise<{ stem: Stem; warning: string | null }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/projects/${projectId}/stems/bass-upload`);
    xhr.setRequestHeader("x-nbs-request", "1");
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100));
    xhr.onload = () => {
      let body: unknown = null;
      try { body = JSON.parse(xhr.responseText); } catch { /* */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as { stem: Stem; warning: string | null });
      else reject(new ApiError(xhr.status, detail(body, `Upload gagal (HTTP ${xhr.status})`)));
    };
    xhr.onerror = () => reject(new ApiError(0, "Koneksi terputus saat upload."));
    const fd = new FormData();
    fd.append("file", file);
    xhr.send(fd);
  });
}
