import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import ClipReviewGrid from "../components/ClipReviewGrid";
import JobStatusProgress from "../components/JobStatusProgress";
import { generateClips, renderDrafts, suggestClips, transcribe } from "../api";
import { useJobDetail, refreshJobDetail } from "../state/jobsStore";

export default function JobDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, loading, error, refresh } = useJobDetail(id);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<"generate" | "transcribe" | "suggest" | "render" | null>(null);

  if (!id) return null;

  async function runGenerateClips() {
    setMsg(null);
    setErr(null);
    setBusyAction("generate");
    try {
      const res = await generateClips(id);
      setMsg(res.message ?? "Queued: transcribe (if needed) → suggest → render");
      await refresh({ force: true });
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusyAction(null);
    }
  }

  async function run(step: "transcribe" | "suggest" | "render") {
    setMsg(null);
    setErr(null);
    setBusyAction(step);
    try {
      if (step === "transcribe") await transcribe(id);
      if (step === "suggest") await suggestClips(id);
      if (step === "render") await renderDrafts(id);
      setMsg(`Queued: ${step}`);
      await refresh({ force: true });
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusyAction(null);
    }
  }

  if ((err || error) && !data) return <p style={{ color: "crimson" }}>{err ?? error}</p>;
  if (!data) {
    return (
      <div className="card">
        <p style={{ margin: 0, color: "#64748b" }}>{loading ? "Loading job details…" : "Job not found."}</p>
      </div>
    );
  }

  const proxySrc = `/api/jobs/${id}/media/proxy`;

  const status = data.job.status;

  return (
    <>
      <p>
        <Link to="/">← Dashboard</Link>
      </p>
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Job {data.job.id.slice(0, 8)}…</h2>
        <p>
          <span className={status === "failed" ? "badge failed" : "badge"}>{status}</span>
          {data.job.source_url && (
            <>
              {" "}
              <a href={data.job.source_url} target="_blank" rel="noreferrer">
                source link
              </a>
            </>
          )}
        </p>
        <JobStatusProgress status={status} variant="full" />
        {data.job.error_message && <p style={{ color: "crimson" }}>{data.job.error_message}</p>}
        {msg && <p style={{ color: "#15803d" }}>{msg}</p>}
        {err && <p style={{ color: "crimson" }}>{err}</p>}
        <p style={{ color: "#475569", fontSize: "0.95rem", marginTop: 0 }}>
          After ingest finishes, run generation once. Then review each suggested clip below before publishing.
        </p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <button
            type="button"
            className={`primary${busyAction === "generate" ? " btn-loading" : ""}`}
            onClick={() => runGenerateClips()}
            disabled={!data.job.mezzanine_path || !!busyAction}
            title={!data.job.mezzanine_path ? "Wait for ingest to finish" : "Transcribe → suggest → render"}
            style={{ fontSize: "1rem", padding: "0.5rem 1rem" }}
          >
            {busyAction === "generate" ? "Starting clip generation…" : "Generate suggested clips & drafts"}
          </button>
        </div>
        <details style={{ marginTop: 12 }}>
          <summary style={{ cursor: "pointer", color: "#64748b" }}>Advanced: run one step at a time</summary>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
            <button
              type="button"
              onClick={() => run("transcribe")}
              disabled={!data.job.mezzanine_path || !!busyAction}
              className={busyAction === "transcribe" ? "btn-loading" : undefined}
            >
              {busyAction === "transcribe" ? "Queuing…" : "Transcribe only"}
            </button>
            <button
              type="button"
              onClick={() => run("suggest")}
              disabled={!!busyAction}
              className={busyAction === "suggest" ? "btn-loading" : undefined}
            >
              {busyAction === "suggest" ? "Queuing…" : "Suggest clips only"}
            </button>
            <button
              type="button"
              onClick={() => run("render")}
              disabled={!!busyAction}
              className={busyAction === "render" ? "btn-loading" : undefined}
            >
              {busyAction === "render" ? "Queuing…" : "Render drafts only"}
            </button>
          </div>
        </details>
      </div>

      {data.job.proxy_path && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Full source preview (proxy)</h3>
          <video src={proxySrc} controls style={{ width: "100%", maxHeight: 360, background: "#000" }} />
        </div>
      )}

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Suggested clips</h3>
        <ClipReviewGrid candidates={data.candidates} onRefresh={() => (id ? refreshJobDetail(id, { force: true }) : undefined)} />
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Logs</h3>
        <div className="logs">
          {[...data.logs].reverse().map((l) => (
            <div key={l.id} className={l.level === "error" ? "log-line error" : "log-line"}>
              [{l.created_at}] {l.message}
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
