const BASE = "";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || r.statusText);
  }
  return r.json() as Promise<T>;
}

export type JobSummary = {
  id: string;
  source_type: string;
  source_url: string | null;
  original_filename: string | null;
  status: string;
  mezzanine_path?: string | null;
  proxy_path?: string | null;
  duration_seconds: number | null;
  error_message: string | null;
  created_at: string;
};

export type PublishJobOut = {
  id: string;
  platform: string;
  status: string;
  external_id: string | null;
  export_bundle_path: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type ClipCandidate = {
  id: string;
  start_sec: number;
  end_sec: number;
  score: number | null;
  hook_text: string | null;
  suggested_title: string | null;
  suggested_hashtags: string | null;
  draft_video_path: string | null;
  approved: number;
  review_status?: string;
  publish_jobs: PublishJobOut[];
};

export type JobDetail = {
  job: JobSummary;
  transcript: {
    id: string;
    full_text: string | null;
    segments: { id: string; start_sec: number; end_sec: number; text: string }[];
  } | null;
  candidates: ClipCandidate[];
  logs: { id: string; level: string; message: string; created_at: string }[];
};

export type Dashboard = {
  total_jobs: number;
  failed_jobs: number;
  by_status: Record<string, number>;
  recent_jobs: Record<string, unknown>[];
};

export const ingestYoutube = (url: string) =>
  api<{ job_id: string }>("/api/ingest/youtube", {
    method: "POST",
    body: JSON.stringify({ url }),
  });

export const ingestTwitch = (url: string) =>
  api<{ job_id: string }>("/api/ingest/twitch", {
    method: "POST",
    body: JSON.stringify({ url }),
  });

export const fetchJobs = () => api<JobSummary[]>("/api/jobs");

export const fetchJob = (id: string) => api<JobDetail>(`/api/jobs/${id}`);

export const fetchDashboard = () => api<Dashboard>("/api/jobs/dashboard");

/** Main workflow: transcribe (if needed) → suggest → render — one click after ingest. */
export const generateClips = (jobId: string) =>
  api<{ ok: boolean; message?: string }>(`/api/jobs/${jobId}/generate-clips`, {
    method: "POST",
    body: "{}",
  });

export const transcribe = (jobId: string) =>
  api<{ ok: boolean }>(`/api/jobs/${jobId}/transcribe`, { method: "POST", body: "{}" });

export const suggestClips = (jobId: string) =>
  api<{ ok: boolean }>(`/api/jobs/${jobId}/suggest-clips`, { method: "POST", body: "{}" });

export const renderDrafts = (jobId: string) =>
  api<{ ok: boolean }>(`/api/jobs/${jobId}/render`, { method: "POST", body: "{}" });

export const patchCandidate = (
  id: string,
  body: Partial<{
    start_sec: number;
    end_sec: number;
    hook_text: string;
    suggested_title: string;
    approved: number;
    review_status: "pending" | "accepted" | "rejected";
  }>
) =>
  api<{ ok: boolean }>(`/api/candidates/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });

export const acceptCandidate = (id: string) =>
  api<{ ok: boolean; review_status?: string }>(`/api/candidates/${id}/accept`, { method: "POST", body: "{}" });

export const rejectCandidate = (id: string) =>
  api<{ ok: boolean; review_status?: string }>(`/api/candidates/${id}/reject`, { method: "POST", body: "{}" });

export const suggestAlternative = (id: string) =>
  api<{ ok: boolean; message?: string }>(`/api/candidates/${id}/suggest-alternative`, {
    method: "POST",
    body: "{}",
  });

export async function uploadRecordingWithProgress(
  file: File,
  onProgress?: (percent: number, loaded: number, total: number) => void
): Promise<{ job_id: string }> {
  const fd = new FormData();
  fd.append("file", file);

  return new Promise<{ job_id: string }>((resolve, reject) => {
    const xhr = new XMLHttpRequest();

    xhr.open("POST", "/api/ingest/upload");

    xhr.upload.onprogress = (evt) => {
      if (!onProgress || !evt.lengthComputable) return;
      const percent = Math.round((evt.loaded / evt.total) * 100);
      onProgress(percent, evt.loaded, evt.total);
    };

    xhr.onerror = () => {
      reject(new Error("Network error while uploading file"));
    };

    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        const msg = xhr.responseText || `Upload failed with status ${xhr.status}`;
        reject(new Error(msg));
        return;
      }
      try {
        const json = JSON.parse(xhr.responseText) as { job_id: string };
        resolve(json);
      } catch (e) {
        reject(new Error("Upload succeeded but response was not valid JSON"));
      }
    };

    xhr.send(fd);
  });
}

export function uploadRecording(file: File): Promise<{ job_id: string }> {
  return uploadRecordingWithProgress(file);
}

export const publishCandidate = (
  id: string,
  platform: "youtube_shorts" | "tiktok" | "instagram_reels",
  title?: string,
  description?: string
) =>
  api<{ ok: boolean }>(`/api/candidates/${id}/publish`, {
    method: "POST",
    body: JSON.stringify({ platform, title, description }),
  });
