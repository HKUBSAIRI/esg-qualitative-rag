from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np


SPACE_RE = re.compile(r"\s+")
EN_TOKEN_RE = re.compile(r"[a-z]+(?:[-'][a-z]+)*|\d+(?:\.\d+)?", re.I)
CJK_RUN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")


def clean_text(value: Any) -> str:
    return SPACE_RE.sub(" ", str(value or "")).strip()


def canonical_text(value: str) -> str:
    return re.sub(r"[^a-z0-9\u3400-\u4dbf\u4e00-\u9fff]+", "", value.lower())


def tokenize(value: str) -> list[str]:
    """Tokenize mixed Chinese/English text exactly as in the frozen experiment."""
    value = value.lower()
    tokens = EN_TOKEN_RE.findall(value)
    for run in CJK_RUN_RE.findall(value):
        if len(run) == 1:
            tokens.append(run)
        tokens.extend(run[i : i + 2] for i in range(max(0, len(run) - 1)))
        tokens.extend(run[i : i + 3] for i in range(max(0, len(run) - 2)))
    return tokens


@dataclass
class BM25:
    documents: list[list[str]]
    k1: float = 1.5
    b: float = 0.75

    def __post_init__(self) -> None:
        self.lengths = np.asarray([len(doc) for doc in self.documents], dtype=np.float32)
        self.avgdl = float(self.lengths.mean()) or 1.0
        self.term_frequencies = [Counter(doc) for doc in self.documents]
        document_frequency: Counter[str] = Counter()
        for doc in self.documents:
            document_frequency.update(set(doc))
        n_docs = len(self.documents)
        self.idf = {
            term: math.log(1.0 + (n_docs - freq + 0.5) / (freq + 0.5))
            for term, freq in document_frequency.items()
        }

    def scores(self, query_tokens: Iterable[str]) -> np.ndarray:
        scores = np.zeros(len(self.documents), dtype=np.float32)
        for term, query_frequency in Counter(query_tokens).items():
            idf = self.idf.get(term)
            if idf is None:
                continue
            for index, frequencies in enumerate(self.term_frequencies):
                frequency = frequencies.get(term, 0)
                if not frequency:
                    continue
                denominator = frequency + self.k1 * (
                    1.0 - self.b + self.b * self.lengths[index] / self.avgdl
                )
                scores[index] += (
                    query_frequency * idf * frequency * (self.k1 + 1.0) / denominator
                )
        return scores


def minmax(values: list[float | None]) -> list[float]:
    present = [float(value) for value in values if value is not None]
    if not present:
        return [0.0] * len(values)
    low, high = min(present), max(present)
    if high <= low:
        return [1.0 if value is not None else 0.0 for value in values]
    return [0.0 if value is None else (float(value) - low) / (high - low) for value in values]


GHG_FACETS = {
    "standard": ("ghg protocol", "greenhouse gas protocol", "iso 14064", "hkex", "核算标准", "温室气体议定书"),
    "boundary": ("organizational boundary", "operational control", "reporting boundary", "reporting scope", "组织边界", "运营控制", "报告范围"),
    "scope_source": ("scope 1", "scope 2", "scope 3", "direct emission", "indirect emission", "fuel combustion", "purchased electricity", "范围一", "范围二", "范围三"),
    "method_factor": ("emission factor", "global warming potential", "gwp", "calculation method", "methodology", "排放因子", "全球变暖潜能", "计算方法"),
    "assurance": ("limited assurance", "reasonable assurance", "independent assurance", "external verification", "third-party verification", "有限保证", "第三方鉴证", "外部审核"),
}


def metric_facets(metric_id: int, card: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    if metric_id == 1:
        return GHG_FACETS
    terms = [
        str(value).casefold()
        for value in list(card.get("anchor_terms_en") or []) + list(card.get("anchor_terms_zh") or [])
        if str(value).strip()
    ]
    count = min(5, len(terms))
    if not count:
        return {}
    size = math.ceil(len(terms) / count)
    return {
        f"anchor_{index + 1}": tuple(terms[index * size : (index + 1) * size])
        for index in range(count)
        if terms[index * size : (index + 1) * size]
    }


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

