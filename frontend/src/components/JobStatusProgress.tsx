import {
  JOB_STAGE_KEYS,
  JOB_STAGE_LABELS,
  jobProgressPercent,
  jobStatusHintDashboard,
  jobStatusHintDetail,
  jobStatusIsActivelyRunning,
} from "../jobStages";

type Props = {
  status: string;
  variant: "full" | "compact";
};

const DISPLAY_STAGES = JOB_STAGE_KEYS.filter((k) => k !== "pending").map((key) => ({
  key,
  label: JOB_STAGE_LABELS[key] ?? key,
}));

export default function JobStatusProgress({ status, variant }: Props) {
  const pct = jobProgressPercent(status);
  const busy = jobStatusIsActivelyRunning(status);
  const hint = variant === "compact" ? jobStatusHintDashboard(status) : jobStatusHintDetail(status);

  if (variant === "compact") {
    if (status === "failed") {
      return (
        <div>
          <span className="progress-label-failed">Failed</span>
        </div>
      );
    }
    return (
      <div style={{ minWidth: 140 }}>
        {pct !== null && (
          <>
            <div
              className="progress-row text-xs text-muted"
              style={{ marginBottom: 2 }}
            >
              <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                {busy && <span className="progress-busy-dot" aria-hidden />}
                <span>{JOB_STAGE_LABELS[status] ?? status}</span>
              </span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                {busy && <span className="progress-busy-label">Working</span>}
                <span>{pct}%</span>
              </span>
            </div>
            <div
              className={`progress-bar${busy ? " progress-bar--busy" : ""}`}
              style={{ marginTop: 0 }}
              aria-busy={busy}
            >
              <div className={`progress-bar-fill${busy ? " progress-bar-fill--busy" : ""}`} style={{ width: `${pct}%` }} />
            </div>
          </>
        )}
        {hint && <p className="hint-tiny">{hint}</p>}
      </div>
    );
  }

  return (
    <div className="job-progress-block">
      <div className="pill-row">
        {DISPLAY_STAGES.map((s, idx) => {
          const isActive = status === s.key || (status === "pending" && s.key === "ingesting");
          const isDone =
            status === "failed"
              ? false
              : DISPLAY_STAGES.findIndex((st) => st.key === status) >= idx && !["failed"].includes(status);
          const pillBusy = isActive && busy;
          return (
            <div
              key={s.key}
              className={
                isActive
                  ? `stage-pill stage-pill-active${pillBusy ? " stage-pill-active--busy" : ""}`
                  : isDone
                    ? "stage-pill stage-pill-done"
                    : "stage-pill"
              }
            >
              {pillBusy && <span className="stage-pill-spinner" aria-hidden />}
              {s.label}
            </div>
          );
        })}
      </div>
      {pct !== null && (
        <div className="mt-sm">
          <div className="progress-row text-small text-muted" style={{ marginBottom: 4 }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              {busy && <span className="progress-busy-dot" aria-hidden />}
              <span>Pipeline</span>
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              {busy && <span className="progress-busy-label">In progress</span>}
              <span>{pct}%</span>
            </span>
          </div>
          <div className={`progress-bar progress-bar--detail${busy ? " progress-bar--busy" : ""}`} aria-busy={busy}>
            <div className={`progress-bar-fill${busy ? " progress-bar-fill--busy" : ""}`} style={{ width: `${pct}%` }} />
          </div>
        </div>
      )}
      {hint && <p className="mt-sm mb-zero">{hint}</p>}
    </div>
  );
}
