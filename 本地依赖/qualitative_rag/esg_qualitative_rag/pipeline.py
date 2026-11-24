from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from .core import BM25, build_pool, metric_facets, select_without_reranker, tokenize
from .data import (
    build_instruction,
    build_query,
    load_corpus,
    load_ground_truth,
    load_metric_cards,
)
from .embeddings import DashScopeEmbedder
from .evaluation import detailed_metrics, evaluate, write_csv


def run_benchmark(
    *,
    corpus_dir: Path,
    ground_truth_dir: Path,
    metrics_path: Path,
    output_dir: Path,
    embedding_cache: Path,
    metric_ids: set[int],
    candidate_k: int = 150,
    top_k: int = 50,
    ks: list[int] | None = None,
) -> dict[str, Any]:
    """Run the frozen BM25 + dense + protected-composite retrieval pipeline."""
    ks = sorted(value for value in set(ks or [10, 25, 50]) if 0 < value <= top_k)
    output_dir.mkdir(parents=True, exist_ok=True)
    results_dir = output_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    queries, groups = load_ground_truth(ground_truth_dir, metric_ids)
    cards = load_metric_cards(metrics_path)
    representative = {item["metric_id"]: item for item in queries}
    query_texts = {
        metric_id: build_query(representative[metric_id], cards[metric_id])
        for metric_id in sorted(metric_ids)
    }
    embedder = DashScopeEmbedder(cache_dir=embedding_cache)
    query_matrix = embedder.encode([query_texts[index] for index in sorted(metric_ids)])
    query_vectors = {
        index: vector for index, vector in zip(sorted(metric_ids), query_matrix)
    }

    rankings: dict[tuple[str, int], list[dict[str, Any]]] = {}
    by_document: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in queries:
        by_document[item["document_id"]].append(item)
    started = time.perf_counter()
    for document_index, document_id in enumerate(sorted(by_document), 1):
        corpus_path = corpus_dir / document_id / "retrieval_chunks.jsonl"
        corpus = load_corpus(corpus_path)
        bm25 = BM25([tokenize(row["retrieval_text"]) for row in corpus])
        document_vectors = embedder.encode([row["retrieval_text"] for row in corpus])
        for item in sorted(by_document[document_id], key=lambda value: value["metric_id"]):
            metric_id = item["metric_id"]
            result_path = results_dir / f"{document_id}__m{metric_id:02d}.json"
            if result_path.exists():
                saved = json.loads(result_path.read_text(encoding="utf-8"))
                rankings[(document_id, metric_id)] = saved["results"]
                continue
            card = cards[metric_id]
            query = query_texts[metric_id]
            facets = metric_facets(metric_id, card)
            pool = build_pool(
                corpus,
                bm25.scores(tokenize(query)),
                document_vectors @ query_vectors[metric_id],
                candidate_k,
                facets,
            )
            results = select_without_reranker(pool, facets, top_k)
            rankings[(document_id, metric_id)] = results
            result_path.write_text(
                json.dumps(
                    {
                        "document_id": document_id,
                        "metric_id": metric_id,
                        "metric_name": item["metric_name"],
                        "query": query,
                        "instruction": build_instruction(item, card),
                        "candidate_pool_size": len(pool),
                        "reranker_usage": None,
                        "results": results,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        print(f"[{document_index:02d}/{len(by_document)}] {document_id}: corpus={len(corpus)}", flush=True)

    metrics = evaluate(queries, groups, rankings, ks)
    per_query, per_metric = detailed_metrics(queries, groups, rankings, ks)
    manifest = {
        "benchmark": "ESG qualitative hybrid retrieval on frozen corpus and GT",
        "metric_ids": sorted(metric_ids),
        "documents": len(by_document),
        "query_count": len(queries),
        "candidate_k": candidate_k,
        "final_top_k": top_k,
        "embedding_model": "qwen3.7-text-embedding",
        "reranker_model": None,
        "selection": "feature composite + BM25/Dense/facet channel protection",
        "retrieval_corpus": "retrieval_chunks.jsonl (P/L/T frozen chunk contract)",
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "embedding_usage": embedder.usage.as_dict(),
        "metrics_by_k": metrics,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_csv(output_dir / "per_query.csv", per_query)
    write_csv(output_dir / "per_metric.csv", per_metric)
    return manifest


def load_saved_rankings(results_dir: Path) -> dict[tuple[str, int], list[dict[str, Any]]]:
    rankings: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for path in sorted(results_dir.glob("*__m*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        rankings[(str(payload["document_id"]), int(payload["metric_id"]))] = payload["results"]
    return rankings


def verify_published_results(
    *, ground_truth_dir: Path, results_dir: Path, metric_ids: set[int]
) -> list[dict[str, Any]]:
    queries, groups = load_ground_truth(ground_truth_dir, metric_ids)
    rankings = load_saved_rankings(results_dir)
    expected = {(item["document_id"], item["metric_id"]) for item in queries}
    missing = sorted(expected - set(rankings))
    if missing:
        raise ValueError(f"published results are incomplete; missing {len(missing)} tasks")
    return evaluate(queries, groups, rankings, [10, 25, 50])

