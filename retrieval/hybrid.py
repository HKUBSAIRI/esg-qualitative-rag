from __future__ import annotations
from typing import Any
import numpy as np
def minmax(values: list[float | None]) -> list[float]:
    present = [float(value) for value in values if value is not None]
    if not present:
        return [0.0] * len(values)
    low, high = min(present), max(present)
    if high <= low:
        return [1.0 if value is not None else 0.0 for value in values]
    return [0.0 if value is None else (float(value) - low) / (high - low) for value in values]


def facet_values(text: str, facets: dict[str, tuple[str, ...]]) -> tuple[list[str], float]:
    normalized = " ".join(str(text).casefold().split())
    hits = [name for name, terms in facets.items() if any(term in normalized for term in terms)]
    return hits, len(hits) / len(facets) if facets else 0.0


def build_pool(
    corpus: list[dict[str, Any]],
    bm25_scores: np.ndarray,
    dense_scores: np.ndarray,
    candidate_k: int,
    facets: dict[str, tuple[str, ...]],
) -> list[dict[str, Any]]:
    bm_order = [
        int(i) for i in np.argsort(-bm25_scores, kind="stable") if bm25_scores[int(i)] > 0
    ][:candidate_k]
    dense_order = [int(i) for i in np.argsort(-dense_scores, kind="stable")[:candidate_k]]
    pool: dict[int, dict[str, Any]] = {}
    for channel, order, scores in (
        ("bm25", bm_order, bm25_scores),
        ("dense", dense_order, dense_scores),
    ):
        for rank, index in enumerate(order, 1):
            row = pool.setdefault(
                index,
                {
                    **corpus[index],
                    "bm25_rank": None,
                    "dense_rank": None,
                    "bm25_score": None,
                    "dense_score": None,
                    "source_channels": [],
                },
            )
            row[f"{channel}_rank"] = rank
            row[f"{channel}_score"] = float(scores[index])
            row["source_channels"].append(channel)

    rows = list(pool.values())
    bm_norm = minmax([row.get("bm25_score") for row in rows])
    dense_norm = minmax([row.get("dense_score") for row in rows])
    for row, lexical, semantic in zip(rows, bm_norm, dense_norm):
        bm_rank = int(row["bm25_rank"]) if row.get("bm25_rank") else None
        dense_rank = int(row["dense_rank"]) if row.get("dense_rank") else None
        bm_rank_norm = max(0.0, 1 - (bm_rank - 1) / max(candidate_k - 1, 1)) if bm_rank else 0.0
        dense_rank_norm = max(0.0, 1 - (dense_rank - 1) / max(candidate_k - 1, 1)) if dense_rank else 0.0
        hits, facet_score = facet_values(f"{row.get('section') or ''} {row['text']}", facets)
        row.update(
            {
                "normalized_bm25": lexical,
                "normalized_dense": semantic,
                "normalized_bm25_rank": bm_rank_norm,
                "normalized_dense_rank": dense_rank_norm,
                "facets": hits,
                "facet_score": facet_score,
                "best_channel_rank": min(value for value in (bm_rank, dense_rank) if value is not None),
            }
        )
        row["composite_score"] = (
            0.35 * semantic
            + 0.20 * lexical
            + 0.20 * dense_rank_norm
            + 0.10 * bm_rank_norm
            + 0.15 * facet_score
        )
    return rows


def select_without_reranker(
    pool: list[dict[str, Any]], facets: dict[str, tuple[str, ...]], top_k: int
) -> list[dict[str, Any]]:
    ranked = sorted(
        pool,
        key=lambda row: (-row["composite_score"], row["best_channel_rank"], row["paragraph_id"]),
    )
    protected: dict[str, dict[str, Any]] = {}
    for channel in ("bm25", "dense"):
        choices = sorted(
            (row for row in pool if row.get(f"{channel}_rank")),
            key=lambda row: row[f"{channel}_rank"],
        )[:10]
        for row in choices:
            protected[row["paragraph_id"]] = row
    for facet in facets:
        choices = [row for row in pool if facet in row["facets"]]
        if choices:
            row = max(choices, key=lambda value: (value["composite_score"], -value["best_channel_rank"]))
            protected[row["paragraph_id"]] = row
    selected_ids = set(protected)
    for row in ranked:
        if len(selected_ids) >= top_k:
            break
        selected_ids.add(row["paragraph_id"])
    return [
        {
            **row,
            "rank": rank,
            "rrf_score": row["composite_score"],
            "retrieval_stage": "qwen37_protected_composite_no_reranker",
        }
        for rank, row in enumerate(
            (row for row in ranked if row["paragraph_id"] in selected_ids), 1
        )
    ][:top_k]
