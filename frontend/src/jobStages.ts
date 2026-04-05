/** Pipeline order must match backend `JobStatus`. */
export const JOB_STAGE_KEYS = [
  "pending",
  "ingesting",
  "ingested",
  "transcribing",
  "transcribed",
  "suggesting",
  "suggested",
  "rendering",
  "rendered",
] as const;

export const JOB_STAGE_LABELS: Record<string, string> = {
  pending: "Queued",
  ingesting: "Ingest",
  ingested: "Ingested",
  transcribing: "Transcribe",
  transcribed: "Transcribed",
  suggesting: "Suggest",
  suggested: "Suggested",
  rendering: "Render",
  rendered: "Ready",
};

export function jobStageIndex(status: string): number {
  if (status === "failed") return -1;
  const i = JOB_STAGE_KEYS.indexOf(status as (typeof JOB_STAGE_KEYS)[number]);
  return i >= 0 ? i : 0;
}

/** Job detail / review page is useful once the pipeline finished or stopped with an error. */
export function jobIsTerminalForDetail(status: string): boolean {
  return status === "rendered" || status === "failed";
}

export function jobProgressPercent(status: string): number | null {
  if (status === "failed") return null;
  const i = jobStageIndex(status);
  const last = JOB_STAGE_KEYS.length - 1;
  if (last <= 0) return 0;
  return Math.round((i / last) * 100);
}

/** Short copy for dashboard table rows. */
export function jobStatusHintDashboard(status: string): string | null {
  switch (status) {
    case "pending":
    case "ingesting":
      return "Ingesting source… large VODs can take a while.";
    case "transcribing":
      return "Transcribing audio to text…";
    case "suggesting":
      return "Finding interesting moments for clips…";
    case "rendering":
      return "Rendering vertical drafts with captions…";
    case "rendered":
      return "Ready — open the job to review clips.";
    default:
      return null;
  }
}

/** Copy aligned with the job detail page (preview + grid below). */
export function jobStatusHintDetail(status: string): string | null {
  switch (status) {
    case "pending":
    case "ingesting":
      return "Ingesting source… large VODs can take a while before transcription starts.";
    case "transcribing":
      return "Transcribing audio to text. Longer videos will stay here for a bit.";
    case "suggesting":
      return "Finding the most interesting moments for clips…";
    case "rendering":
      return "Rendering vertical drafts with captions.";
    case "rendered":
      return "Drafts ready below – review and publish your favorites.";
    default:
      return null;
  }
}
