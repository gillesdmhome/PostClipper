import { useMemo, useState } from "react";
import type { ClipCandidate } from "../api";
import {
  acceptCandidate,
  publishCandidate,
  rejectCandidate,
  suggestAlternative,
} from "../api";

type Filter = "all" | "pending" | "accepted" | "rejected";

function statusBadge(status: string) {
  const s = status || "pending";
  if (s === "accepted") {
    return <span className="badge" style={{ background: "#bbf7d0", color: "#14532d" }}>Accepted</span>;
  }
  if (s === "rejected") {
    return <span className="badge" style={{ background: "#fecaca", color: "#991b1b" }}>Rejected</span>;
  }
  return <span className="badge" style={{ background: "#e0e7ff", color: "#3730a3" }}>Pending review</span>;
}

export default function ClipReviewGrid({
  candidates,
  onRefresh,
}: {
  candidates: ClipCandidate[];
  onRefresh: () => void;
}) {
  const [filter, setFilter] = useState<Filter>("pending");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const sorted = useMemo(() => {
    const rank = (s: string) => (s === "pending" ? 0 : s === "accepted" ? 1 : 2);
    return [...candidates].sort((a, b) => {
      const rs = (c: ClipCandidate) => c.review_status || "pending";
      const d = rank(rs(a)) - rank(rs(b));
      if (d !== 0) return d;
      return (b.score ?? 0) - (a.score ?? 0);
    });
  }, [candidates]);

  const filtered = useMemo(() => {
    if (filter === "all") return sorted;
    return sorted.filter((c) => (c.review_status || "pending") === filter);
  }, [sorted, filter]);

  async function onAccept(id: string) {
    setErr(null);
    setBusy(id);
    try {
      await acceptCandidate(id);
      onRefresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(null);
    }
  }

  async function onReject(id: string) {
    setErr(null);
    setBusy(id);
    try {
      await rejectCandidate(id);
      onRefresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(null);
    }
  }

  async function onSuggestAnother(id: string) {
    setErr(null);
    setBusy(id);
    try {
      await suggestAlternative(id);
      onRefresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(null);
    }
  }

  if (candidates.length === 0) {
    return (
      <p style={{ color: "#64748b" }}>
        No candidates yet — use &quot;Generate suggested clips &amp; drafts&quot; after ingest completes.
      </p>
    );
  }

  return (
    <div>
      <p style={{ color: "#475569", marginTop: 0, fontSize: "0.95rem" }}>
        Preview each draft, then <strong>Accept</strong> to keep it for publishing, <strong>Reject</strong> to dismiss, or{" "}
        <strong>Suggest another clip</strong> to replace it with a different time range (auto-rendered).
      </p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginBottom: 16 }}>
        <span style={{ fontWeight: 600 }}>Show:</span>
        {(["all", "pending", "accepted", "rejected"] as const).map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setFilter(f)}
            className={filter === f ? "primary" : undefined}
            style={filter === f ? {} : { opacity: 0.85 }}
          >
            {f === "all" ? "All" : f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>
      {err && <p style={{ color: "crimson", marginBottom: 8 }}>{err}</p>}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
          gap: "1rem",
        }}
      >
        {filtered.map((c) => {
          const rs = c.review_status || "pending";
          const draftSrc = c.draft_video_path != null ? `/api/candidates/${c.id}/media/draft` : null;
          const isBusy = busy === c.id;

          return (
            <div
              key={c.id}
              className="card"
              style={{
                margin: 0,
                display: "flex",
                flexDirection: "column",
                opacity: rs === "rejected" ? 0.75 : 1,
                border:
                  rs === "accepted"
                    ? "2px solid #22c55e"
                    : rs === "rejected"
                      ? "1px solid #fecaca"
                      : "1px solid #e2e8f0",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                <div style={{ fontSize: "0.8rem", fontFamily: "monospace", color: "#64748b" }}>
                  {c.start_sec.toFixed(1)}s – {c.end_sec.toFixed(1)}s
                </div>
                {statusBadge(rs)}
              </div>

              <div
                style={{
                  aspectRatio: "9/16",
                  maxHeight: 320,
                  background: "#0f172a",
                  borderRadius: 8,
                  overflow: "hidden",
                  marginTop: 8,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                {draftSrc ? (
                  <video
                    src={draftSrc}
                    controls
                    playsInline
                    style={{ width: "100%", height: "100%", objectFit: "contain" }}
                  />
                ) : (
                  <span style={{ color: "#94a3b8", fontSize: "0.85rem" }}>Rendering…</span>
                )}
              </div>

              <div style={{ marginTop: 10, flex: 1 }}>
                <strong style={{ fontSize: "0.95rem", display: "block" }}>{c.suggested_title || "Untitled clip"}</strong>
                <p style={{ fontSize: "0.85rem", color: "#475569", margin: "6px 0 0" }}>{c.hook_text || "—"}</p>
                <div style={{ fontSize: "0.75rem", color: "#94a3b8" }}>Score: {c.score?.toFixed(2) ?? "—"}</div>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 12 }}>
                {rs === "pending" && (
                  <>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      <button
                        type="button"
                        className={`primary${isBusy ? " btn-loading" : ""}`}
                        disabled={isBusy}
                        onClick={() => onAccept(c.id)}
                        style={{ flex: 1, minWidth: 100 }}
                      >
                        {isBusy ? "Saving…" : "Accept"}
                      </button>
                      <button
                        type="button"
                        disabled={isBusy}
                        onClick={() => onReject(c.id)}
                        style={{ flex: 1, minWidth: 100 }}
                        className={isBusy ? "btn-loading" : undefined}
                      >
                        {isBusy ? "Updating…" : "Reject"}
                      </button>
                    </div>
                    <button
                      type="button"
                      disabled={isBusy}
                      onClick={() => onSuggestAnother(c.id)}
                      title="Rejects this window and adds a different non-overlapping clip"
                      className={isBusy ? "btn-loading" : undefined}
                    >
                      {isBusy ? "Searching…" : "Suggest another clip"}
                    </button>
                  </>
                )}
                {rs === "accepted" && (
                  <p style={{ fontSize: "0.85rem", color: "#15803d", margin: 0 }}>
                    Accepted — use publish actions below.
                  </p>
                )}
                {rs === "rejected" && (
                  <p style={{ fontSize: "0.85rem", color: "#64748b", margin: 0 }}>
                    Dismissed. New alternatives appear as pending cards when you use &quot;Suggest another&quot;.
                  </p>
                )}
              </div>

              {rs === "accepted" && (
                <PublishBlock c={c} busy={isBusy} onDone={onRefresh} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function PublishBlock({
  c,
  busy,
  onDone,
}: {
  c: ClipCandidate;
  busy: boolean;
  onDone: () => void;
}) {
  const [pubBusy, setPubBusy] = useState(false);

  async function pub(platform: "youtube_shorts" | "tiktok" | "instagram_reels") {
    setPubBusy(true);
    try {
      await publishCandidate(c.id, platform, c.suggested_title ?? undefined, c.hook_text ?? undefined);
      onDone();
    } finally {
      setPubBusy(false);
    }
  }

  return (
    <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid #e2e8f0" }}>
      <span style={{ fontSize: "0.8rem", fontWeight: 600, display: "block", marginBottom: 6 }}>Publish</span>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <button type="button" className="primary" disabled={busy || pubBusy} onClick={() => pub("youtube_shorts")}>
          YouTube Shorts
        </button>
        <button type="button" disabled={busy || pubBusy} onClick={() => pub("tiktok")}>
          TikTok (export)
        </button>
        <button type="button" disabled={busy || pubBusy} onClick={() => pub("instagram_reels")}>
          IG Reels (export)
        </button>
      </div>
      {c.publish_jobs?.map((pj) => (
        <div key={pj.id} style={{ fontSize: "0.75rem", marginTop: 6 }}>
          {pj.platform}: <strong>{pj.status}</strong>
          {pj.external_id ? ` (${pj.external_id})` : ""}
          {pj.status === "export_ready" && (
            <div>
              <a href={`/api/publish-jobs/${pj.id}/download`} download>
                Download ZIP
              </a>
            </div>
          )}
          {pj.error_message && <div style={{ color: "crimson" }}>{pj.error_message}</div>}
        </div>
      ))}
    </div>
  );
}
