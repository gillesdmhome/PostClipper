import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import JobStatusProgress from "../components/JobStatusProgress";
import { generateClips, ingestTwitch, ingestYoutube, uploadRecordingWithProgress } from "../api";
import type { JobSummary } from "../api";
import { jobIsTerminalForDetail } from "../jobStages";
import { optimisticUpsertJob, useJobsDashboard } from "../state/jobsStore";

function optimisticJobFromIngest(
  jobId: string,
  status: string,
  fields: { source_type: string; source_url?: string | null; original_filename?: string | null }
): JobSummary {
  return {
    id: jobId,
    status,
    source_type: fields.source_type,
    source_url: fields.source_url ?? null,
    original_filename: fields.original_filename ?? null,
    mezzanine_path: null,
    proxy_path: null,
    duration_seconds: null,
    error_message: null,
    created_at: new Date().toISOString(),
  };
}

export default function Dashboard() {
  const { jobs, dashboard: dash, loading, error, refresh } = useJobsDashboard();
  const [yt, setYt] = useState("");
  const [tw, setTw] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [generatingJobId, setGeneratingJobId] = useState<string | null>(null);

  const hasActiveJobs = jobs.some((j) => !jobIsTerminalForDetail(j.status));

  useEffect(() => {
    if (!hasActiveJobs) return;
    const id = window.setInterval(() => {
      void refresh({ force: true, silent: true });
    }, 3000);
    return () => window.clearInterval(id);
  }, [hasActiveJobs, refresh]);

  async function onGenerateClips(jobId: string) {
    setGeneratingJobId(jobId);
    setErr(null);
    try {
      await generateClips(jobId);
      void refresh({ force: true, silent: true });
    } catch (e) {
      setErr(String(e));
    } finally {
      setGeneratingJobId(null);
    }
  }

  async function onYoutube(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const { job_id, status } = await ingestYoutube(yt);
      optimisticUpsertJob(
        optimisticJobFromIngest(job_id, status ?? "pending", { source_type: "youtube", source_url: yt })
      );
      setYt("");
      void refresh({ force: true, silent: true });
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onTwitch(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const { job_id, status } = await ingestTwitch(tw);
      optimisticUpsertJob(
        optimisticJobFromIngest(job_id, status ?? "pending", { source_type: "twitch", source_url: tw })
      );
      setTw("");
      void refresh({ force: true, silent: true });
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setBusy(true);
    setUploadPct(0);
    try {
      const { job_id, status } = await uploadRecordingWithProgress(f, (pct) => {
        setUploadPct(pct);
      });
      optimisticUpsertJob(
        optimisticJobFromIngest(job_id, status ?? "pending", { source_type: "upload", original_filename: f.name })
      );
      void refresh({ force: true, silent: true });
    } catch (err) {
      setErr(String(err));
    } finally {
      setBusy(false);
      setUploadPct(null);
      e.target.value = "";
    }
  }

  return (
    <>
      {dash && (
        <div className="card">
          <h2>Dashboard</h2>
          <p>
            <strong>{dash.total_jobs}</strong> jobs · <strong>{dash.failed_jobs}</strong> failed
          </p>
          <div className="flex-gap-sm" style={{ marginTop: 8 }}>
            {Object.entries(dash.by_status).map(([k, v]) => (
              <span
                key={k}
                className={
                  k === "failed"
                    ? "badge status-badge status-failed"
                    : k === "rendered"
                      ? "badge status-badge status-done"
                      : "badge status-badge"
                }
              >
                {k}: {v}
              </span>
            ))}
          </div>
        </div>
      )}
      {!dash && (
        <div className="card">
          <h2>Dashboard</h2>
          <p className="text-muted text-small">
            {loading ? "Loading jobs summary…" : "No jobs yet — start a new ingest below."}
          </p>
        </div>
      )}

      <div className="card">
        <h2>New ingest</h2>
        {(err || error) && <p className="text-error">{err ?? error}</p>}
        <form onSubmit={onYoutube} className="form-stack">
          <label>YouTube VOD URL</label>
          <div className="form-inline">
            <input value={yt} onChange={(e) => setYt(e.target.value)} placeholder="https://..." />
            <button type="submit" className={`primary${busy ? " btn-loading" : ""}`} disabled={busy}>
              {busy ? "Starting…" : "Start"}
            </button>
          </div>
        </form>
        <form onSubmit={onTwitch} className="form-stack">
          <label>Twitch VOD URL</label>
          <div className="form-inline">
            <input value={tw} onChange={(e) => setTw(e.target.value)} placeholder="https://..." />
            <button type="submit" className={`primary${busy ? " btn-loading" : ""}`} disabled={busy}>
              {busy ? "Starting…" : "Start"}
            </button>
          </div>
        </form>
        <div>
          <label>Zoom / podcast file</label>
          <input type="file" accept="video/*,audio/*" onChange={onFileChange} disabled={busy} style={{ marginTop: 4 }} />
          {uploadPct !== null && (
            <div className="mt-sm">
              <div className="progress-row text-xs text-muted">
                <span>Uploading file…</span>
                <span>{uploadPct}%</span>
              </div>
              <div className="progress-bar">
                <div className="progress-bar-fill" style={{ width: `${uploadPct}%` }} />
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <h2>Jobs</h2>
        <p className="text-muted text-small" style={{ marginTop: "0.35rem", marginBottom: "0.75rem" }}>
          In-progress jobs stay here with live status. Open the job page once clips are <strong>ready</strong> or the run{" "}
          <strong>failed</strong> (to review errors and logs).
        </p>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Source</th>
              <th>Status</th>
              <th>Progress</th>
              <th>Duration</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {loading && jobs.length === 0 && (
              <tr>
                <td colSpan={6} className="text-muted" style={{ padding: "0.75rem" }}>
                  Loading jobs…
                </td>
              </tr>
            )}
            {!loading && jobs.length === 0 && (
              <tr>
                <td colSpan={6} className="text-muted" style={{ padding: "0.75rem" }}>
                  No jobs yet — start a new ingest above.
                </td>
              </tr>
            )}
            {jobs.map((j) => (
              <tr key={j.id}>
                <td className="mono text-xs">{j.id.slice(0, 8)}…</td>
                <td>{j.source_type}</td>
                <td>
                  <span className={j.status === "failed" ? "badge failed" : "badge"}>{j.status}</span>
                </td>
                <td>
                  <JobStatusProgress status={j.status} variant="compact" />
                </td>
                <td>{j.duration_seconds != null ? `${j.duration_seconds.toFixed(1)}s` : "—"}</td>
                <td>
                  <div className="table-actions">
                    <Link to={`/job/${j.id}`} className="link-as-button">
                      Open job
                    </Link>
                    {!jobIsTerminalForDetail(j.status) && j.mezzanine_path ? (
                      <button
                        type="button"
                        className={`primary${generatingJobId === j.id ? " btn-loading" : ""}`}
                        disabled={generatingJobId !== null}
                        onClick={() => onGenerateClips(j.id)}
                      >
                        {generatingJobId === j.id ? "Starting…" : "Generate clips"}
                      </button>
                    ) : null}
                    {!jobIsTerminalForDetail(j.status) && !j.mezzanine_path ? (
                      <span className="text-faint text-xs">Generate after ingest</span>
                    ) : null}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
