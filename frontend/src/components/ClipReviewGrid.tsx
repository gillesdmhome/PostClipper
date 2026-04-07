import { useMemo, useState } from "react";
import type { ClipCandidate } from "../api";
import {
  acceptCandidate,
  patchCandidate,
  publishCandidate,
  regenerateCaption,
  rejectCandidate,
  suggestAlternative,
} from "../api";

type Filter = "all" | "pending" | "accepted" | "rejected";

function platformBadge(platform?: string | null) {
  const p = (platform || "").trim();
  if (!p) return null;
  const label =
    p === "youtube_shorts"
      ? "Shorts"
      : p === "instagram_reels"
        ? "Reels"
        : p === "tiktok"
          ? "TikTok"
          : p === "x"
            ? "X"
            : p;
  return <span className="badge">{label}</span>;
}

function statusBadge(status: string) {
  const s = status || "pending";
  if (s === "accepted") {
    return <span className="badge badge-review-accepted">Accepted</span>;
  }
  if (s === "rejected") {
    return <span className="badge badge-review-rejected">Rejected</span>;
  }
  return <span className="badge badge-review-pending">Pending review</span>;
}

export default function ClipReviewGrid({
  candidates,
  onRefresh,
}: {
  candidates: ClipCandidate[];
  onRefresh: () => void;
}) {
  const [filter, setFilter] = useState<Filter>("pending");
  const [platformFilter, setPlatformFilter] = useState<string>("all");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [edits, setEdits] = useState<
    Record<
      string,
      {
        suggested_title?: string;
        hook_text?: string;
        suggested_hashtags?: string;
        suggested_description?: string;
      }
    >
  >({});

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
    const byStatus = filter === "all" ? sorted : sorted.filter((c) => (c.review_status || "pending") === filter);
    if (platformFilter === "all") return byStatus;
    return byStatus.filter((c) => (c.platform || "") === platformFilter);
  }, [sorted, filter, platformFilter]);

  const platformOptions = useMemo(() => {
    const set = new Set<string>();
    for (const c of candidates) {
      if (c.platform) set.add(c.platform);
    }
    return ["all", ...Array.from(set).sort()];
  }, [candidates]);

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

  async function onSaveEdits(id: string) {
    const e = edits[id];
    if (!e) return;
    setErr(null);
    setBusy(id);
    try {
      await patchCandidate(id, {
        suggested_title: e.suggested_title,
        hook_text: e.hook_text,
        suggested_hashtags: e.suggested_hashtags,
        suggested_description: e.suggested_description,
      });
      onRefresh();
    } catch (e2) {
      setErr(String(e2));
    } finally {
      setBusy(null);
    }
  }

  async function onRegenerateCaption(id: string) {
    setErr(null);
    setBusy(id);
    try {
      await regenerateCaption(id);
      onRefresh();
    } catch (e2) {
      setErr(String(e2));
    } finally {
      setBusy(null);
    }
  }

  if (candidates.length === 0) {
    return (
      <p className="text-muted text-small">
        No candidates yet — use &quot;Generate suggested clips &amp; drafts&quot; after ingest completes.
      </p>
    );
  }

  return (
    <div>
      <p className="text-muted text-small" style={{ marginTop: 0, marginBottom: "0.75rem" }}>
        Preview each draft, then <strong>Accept</strong> to keep it for publishing, <strong>Reject</strong> to dismiss, or{" "}
        <strong>Suggest another clip</strong> to replace it with a different time range (auto-rendered).
      </p>
      <div className="filter-row">
        <span className="filter-row-label">Show</span>
        {(["all", "pending", "accepted", "rejected"] as const).map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setFilter(f)}
            className={filter === f ? "primary" : undefined}
          >
            {f === "all" ? "All" : f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>
      <div className="filter-row">
        <span className="filter-row-label">Platform</span>
        <select value={platformFilter} onChange={(e) => setPlatformFilter(e.target.value)}>
          {platformOptions.map((p) => (
            <option key={p} value={p}>
              {p === "all" ? "All" : p}
            </option>
          ))}
        </select>
      </div>
      {err && <p className="text-error" style={{ marginBottom: 8 }}>{err}</p>}

      <div className="clip-grid">
        {filtered.map((c) => {
          const rs = c.review_status || "pending";
          const draftSrc = c.draft_video_path != null ? `/api/candidates/${c.id}/media/draft` : null;
          const isBusy = busy === c.id;
          const e = edits[c.id] || {};
          const title = e.suggested_title ?? c.suggested_title ?? "";
          const hook = e.hook_text ?? c.hook_text ?? "";
          const tags = e.suggested_hashtags ?? c.suggested_hashtags ?? "";
          const desc = e.suggested_description ?? c.suggested_description ?? "";

          const cardMod =
            rs === "accepted" ? " clip-card--accepted" : rs === "rejected" ? " clip-card--rejected" : "";

          return (
            <div key={c.id} className={`card clip-card${cardMod}`}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                <div className="mono text-xs text-muted">
                  {c.start_sec.toFixed(1)}s – {c.end_sec.toFixed(1)}s
                </div>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  {platformBadge(c.platform)}
                  {statusBadge(rs)}
                </div>
              </div>

              <div className="clip-thumb">
                {draftSrc ? (
                  <video
                    src={draftSrc}
                    controls
                    playsInline
                    style={{ width: "100%", height: "100%", objectFit: "contain" }}
                  />
                ) : (
                  <span className="text-faint text-small">Rendering…</span>
                )}
              </div>

              <div className="mt-sm" style={{ flex: 1 }}>
                <label className="text-xs text-muted" style={{ display: "block", marginTop: 6 }}>
                  Title
                </label>
                <input
                  value={title}
                  onChange={(ev) =>
                    setEdits((prev) => ({ ...prev, [c.id]: { ...prev[c.id], suggested_title: ev.target.value } }))
                  }
                />
                <label className="text-xs text-muted" style={{ display: "block", marginTop: 8 }}>
                  Letterbox caption
                </label>
                <textarea
                  rows={3}
                  value={hook}
                  onChange={(ev) =>
                    setEdits((prev) => ({ ...prev, [c.id]: { ...prev[c.id], hook_text: ev.target.value } }))
                  }
                />
                <label className="text-xs text-muted" style={{ display: "block", marginTop: 8 }}>
                  Hashtags
                </label>
                <input
                  value={tags}
                  onChange={(ev) =>
                    setEdits((prev) => ({ ...prev, [c.id]: { ...prev[c.id], suggested_hashtags: ev.target.value } }))
                  }
                />
                <label className="text-xs text-muted" style={{ display: "block", marginTop: 8 }}>
                  Description
                </label>
                <textarea
                  rows={2}
                  value={desc}
                  onChange={(ev) =>
                    setEdits((prev) => ({ ...prev, [c.id]: { ...prev[c.id], suggested_description: ev.target.value } }))
                  }
                />
                <div className="text-xs text-faint">Score: {c.score?.toFixed(2) ?? "—"}</div>
              </div>

              <div className="flex-actions-col">
                <div className="flex-gap-sm">
                  <button type="button" disabled={isBusy} className={isBusy ? "btn-loading" : undefined} onClick={() => onSaveEdits(c.id)}>
                    {isBusy ? "Saving…" : "Save edits"}
                  </button>
                  <button
                    type="button"
                    disabled={isBusy}
                    className={isBusy ? "btn-loading" : undefined}
                    onClick={() => onRegenerateCaption(c.id)}
                    title="Regenerates caption text and re-renders the draft"
                  >
                    {isBusy ? "Queuing…" : "Regenerate caption"}
                  </button>
                </div>
                {rs === "pending" && (
                  <>
                    <div className="flex-gap-sm">
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
                  <p className="text-success text-small mb-zero">Accepted — use publish actions below.</p>
                )}
                {rs === "rejected" && (
                  <p className="text-muted text-small mb-zero">
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
    <div className="publish-block">
      <span className="publish-block-title">Publish</span>
      <div className="publish-stack">
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
        <div key={pj.id} className="text-xs text-muted mt-sm">
          {pj.platform}: <strong>{pj.status}</strong>
          {pj.external_id ? ` (${pj.external_id})` : ""}
          {pj.status === "export_ready" && (
            <div>
              <a href={`/api/publish-jobs/${pj.id}/download`} download>
                Download ZIP
              </a>
            </div>
          )}
          {pj.error_message && <div className="text-error">{pj.error_message}</div>}
        </div>
      ))}
    </div>
  );
}
