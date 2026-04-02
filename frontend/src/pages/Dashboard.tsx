import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Dashboard as Dash, fetchDashboard, fetchJobs, ingestTwitch, ingestYoutube, JobSummary, uploadRecordingWithProgress } from "../api";

export default function Dashboard() {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [dash, setDash] = useState<Dash | null>(null);
  const [yt, setYt] = useState("");
  const [tw, setTw] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploadPct, setUploadPct] = useState<number | null>(null);

  async function refresh() {
    try {
      const [j, d] = await Promise.all([fetchJobs(), fetchDashboard()]);
      setJobs(j);
      setDash(d);
      setErr(null);
    } catch (e) {
      setErr(String(e));
    }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, []);

  async function onYoutube(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const { job_id } = await ingestYoutube(yt);
      setYt("");
      await refresh();
      window.location.href = `/job/${job_id}`;
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
      const { job_id } = await ingestTwitch(tw);
      setTw("");
      await refresh();
      window.location.href = `/job/${job_id}`;
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
      const { job_id } = await uploadRecordingWithProgress(f, (pct) => {
        setUploadPct(pct);
      });
      await refresh();
      window.location.href = `/job/${job_id}`;
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
          <h2 style={{ marginTop: 0 }}>Dashboard</h2>
          <p>
            <strong>{dash.total_jobs}</strong> jobs · <strong>{dash.failed_jobs}</strong> failed
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
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

      <div className="card">
        <h2 style={{ marginTop: 0 }}>New ingest</h2>
        {err && <p style={{ color: "crimson" }}>{err}</p>}
        <form onSubmit={onYoutube} style={{ marginBottom: 12 }}>
          <label>YouTube VOD URL</label>
          <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
            <input value={yt} onChange={(e) => setYt(e.target.value)} placeholder="https://..." />
            <button type="submit" className={`primary${busy ? " btn-loading" : ""}`} disabled={busy}>
              {busy ? "Starting…" : "Start"}
            </button>
          </div>
        </form>
        <form onSubmit={onTwitch} style={{ marginBottom: 12 }}>
          <label>Twitch VOD URL</label>
          <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
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
            <div style={{ marginTop: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.78rem", color: "#475569" }}>
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
        <h2 style={{ marginTop: 0 }}>Jobs</h2>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Source</th>
              <th>Status</th>
              <th>Duration</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.id}>
                <td style={{ fontFamily: "monospace", fontSize: "0.75rem" }}>{j.id.slice(0, 8)}…</td>
                <td>{j.source_type}</td>
                <td>
                  <span className={j.status === "failed" ? "badge failed" : "badge"}>{j.status}</span>
                </td>
                <td>{j.duration_seconds != null ? `${j.duration_seconds.toFixed(1)}s` : "—"}</td>
                <td>
                  <Link to={`/job/${j.id}`}>Open</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
