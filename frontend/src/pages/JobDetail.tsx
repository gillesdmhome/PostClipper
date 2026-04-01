import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import ClipReviewGrid from "../components/ClipReviewGrid";
import {
  fetchJob,
  generateClips,
  JobDetail as JobDetailT,
  renderDrafts,
  suggestClips,
  transcribe,
} from "../api";

export default function JobDetail() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<JobDetailT | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  async function load() {
    if (!id) return;
    try {
      const j = await fetchJob(id);
      setData(j);
      setErr(null);
    } catch (e) {
      setErr(String(e));
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [id]);

  if (!id) return null;

  async function runGenerateClips() {
    setMsg(null);
    setErr(null);
    try {
      const res = await generateClips(id);
      setMsg(res.message ?? "Queued: transcribe (if needed) → suggest → render");
      await load();
    } catch (e) {
      setErr(String(e));
    }
  }

  async function run(step: "transcribe" | "suggest" | "render") {
    setMsg(null);
    setErr(null);
    try {
      if (step === "transcribe") await transcribe(id);
      if (step === "suggest") await suggestClips(id);
      if (step === "render") await renderDrafts(id);
      setMsg(`Queued: ${step}`);
      await load();
    } catch (e) {
      setErr(String(e));
    }
  }

  if (err && !data) return <p style={{ color: "crimson" }}>{err}</p>;
  if (!data) return <p>Loading…</p>;

  const proxySrc = `/api/jobs/${id}/media/proxy`;

  return (
    <>
      <p>
        <Link to="/">← Dashboard</Link>
      </p>
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Job {data.job.id.slice(0, 8)}…</h2>
        <p>
          <span className={data.job.status === "failed" ? "badge failed" : "badge"}>{data.job.status}</span>
          {data.job.source_url && (
            <>
              {" "}
              <a href={data.job.source_url} target="_blank" rel="noreferrer">
                source link
              </a>
            </>
          )}
        </p>
        {data.job.error_message && <p style={{ color: "crimson" }}>{data.job.error_message}</p>}
        {msg && <p style={{ color: "#15803d" }}>{msg}</p>}
        {err && <p style={{ color: "crimson" }}>{err}</p>}
        <p style={{ color: "#475569", fontSize: "0.95rem", marginTop: 0 }}>
          After ingest finishes, run generation once. Then review each suggested clip below before publishing.
        </p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <button
            type="button"
            className="primary"
            onClick={() => runGenerateClips()}
            disabled={!data.job.mezzanine_path}
            title={!data.job.mezzanine_path ? "Wait for ingest to finish" : "Transcribe → suggest → render"}
            style={{ fontSize: "1rem", padding: "0.5rem 1rem" }}
          >
            Generate suggested clips &amp; drafts
          </button>
        </div>
        <details style={{ marginTop: 12 }}>
          <summary style={{ cursor: "pointer", color: "#64748b" }}>Advanced: run one step at a time</summary>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
            <button type="button" onClick={() => run("transcribe")} disabled={!data.job.mezzanine_path}>
              Transcribe only
            </button>
            <button type="button" onClick={() => run("suggest")}>
              Suggest clips only
            </button>
            <button type="button" onClick={() => run("render")}>
              Render drafts only
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
        <ClipReviewGrid candidates={data.candidates} onRefresh={load} />
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
