"""
Semantic clip ranking with sentence-transformers (cosine vs full-transcript anchor).
Install: pip install -r requirements-ml.txt  and  SUGGEST_ENGINE=embeddings
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional, Tuple

import numpy as np

from app.config import settings
from app.services.suggest import (
    candidate_windows_from_segments,
    finalize_scored_candidates,
)

_log = logging.getLogger(__name__)

# ~25k chars keeps encode time reasonable; model truncates internally anyway.
_MAX_DOC_CHARS = 24_000

_st_model = None
_st_key: tuple[str, str] | None = None


def _get_sentence_transformer(model_name: str):
    global _st_model, _st_key
    import torch
    from sentence_transformers import SentenceTransformer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    key = (model_name, device)
    if _st_model is not None and _st_key == key:
        return _st_model
    _log.info("Loading sentence-transformers model %s on %s", model_name, device)
    _st_model = SentenceTransformer(model_name, device=device)
    _st_key = key
    return _st_model


def suggest_clips_embeddings(
    segments: list[dict[str, Any]],
    *,
    target_min: float = 15.0,
    target_max: float = 55.0,
    max_candidates: int = 12,
    exclude_ranges: Optional[List[Tuple[float, float]]] = None,
) -> list[dict[str, Any]]:
    from app.services.suggest import suggest_clips_from_segments

    if not segments:
        return []

    merged, windows = candidate_windows_from_segments(
        segments, target_min=target_min, target_max=target_max
    )
    if not windows:
        return suggest_clips_from_segments(
            segments,
            target_min=target_min,
            target_max=target_max,
            max_candidates=max_candidates,
            exclude_ranges=exclude_ranges,
        )

    model_name = (settings.sentence_transformer_model or "all-MiniLM-L6-v2").strip()
    model = _get_sentence_transformer(model_name)

    doc_text = " ".join(str(s.get("text", "")) for s in segments).strip()
    doc_text = doc_text[:_MAX_DOC_CHARS] or "video"

    window_texts = [w["text"].strip() or "…" for w in windows]
    # One batch: [document, window_0, window_1, ...]
    all_texts = [doc_text] + window_texts
    emb = model.encode(
        all_texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    doc_vec = emb[0].astype(np.float32, copy=False)
    win_vecs = emb[1:].astype(np.float32, copy=False)
    sims = np.dot(win_vecs, doc_vec)

    scored: list[dict[str, Any]] = []
    for w, sim in zip(windows, sims.tolist()):
        text = w["text"]
        dur = max(0.1, w["end"] - w["start"])
        prefix = text[: min(120, len(text))]
        title_words = text.split()[:8]
        suggested_title = " ".join(title_words).strip()[:80] or "Clip"
        scored.append(
            {
                "start_sec": float(w["start"]),
                "end_sec": float(w["end"]),
                "score": round(float(sim), 6),
                "hook_text": prefix[:200],
                "suggested_title": suggested_title,
                "suggested_hashtags": "#shorts #clip",
            }
        )

    return finalize_scored_candidates(
        scored,
        merged=merged,
        target_min=target_min,
        target_max=target_max,
        max_candidates=max_candidates,
        exclude_ranges=exclude_ranges,
    )
