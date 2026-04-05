import {
  JOB_STAGE_KEYS,
  JOB_STAGE_LABELS,
  jobProgressPercent,
  jobStatusHintDashboard,
  jobStatusHintDetail,
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
  const hint = variant === "compact" ? jobStatusHintDashboard(status) : jobStatusHintDetail(status);

  if (variant === "compact") {
    if (status === "failed") {
      return (
        <div>
          <span style={{ fontSize: "0.72rem", color: "#b91c1c" }}>Failed</span>
        </div>
      );
    }
    return (
      <div style={{ minWidth: 140 }}>
        {pct !== null && (
          <>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", color: "#475569", marginBottom: 2 }}>
              <span>{JOB_STAGE_LABELS[status] ?? status}</span>
              <span>{pct}%</span>
            </div>
            <div className="progress-bar" style={{ marginTop: 0 }}>
              <div className="progress-bar-fill" style={{ width: `${pct}%` }} />
            </div>
          </>
        )}
        {hint && (
          <p style={{ margin: "4px 0 0", fontSize: "0.68rem", color: "#64748b", lineHeight: 1.35 }}>{hint}</p>
        )}
      </div>
    );
  }

  return (
    <div style={{ margin: "0.25rem 0 0.75rem", fontSize: "0.8rem", color: "#475569" }}>
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
        {DISPLAY_STAGES.map((s, idx) => {
          const isActive = status === s.key || (status === "pending" && s.key === "ingesting");
          const isDone =
            status === "failed"
              ? false
              : DISPLAY_STAGES.findIndex((st) => st.key === status) >= idx && !["failed"].includes(status);
          return (
            <div
              key={s.key}
              className={
                isActive ? "stage-pill stage-pill-active" : isDone ? "stage-pill stage-pill-done" : "stage-pill"
              }
            >
              {s.label}
            </div>
          );
        })}
      </div>
      {hint && <p style={{ margin: "0.5rem 0 0" }}>{hint}</p>}
    </div>
  );
}
