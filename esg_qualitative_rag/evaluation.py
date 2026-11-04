from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any


def evaluate(
    queries: list[dict[str, Any]],
    groups: list[dict[str, Any]],
    rankings: dict[tuple[str, int], list[dict[str, Any]]],
    ks: list[int],
) -> list[dict[str, Any]]:
    eligible = [item for item in queries if item["all_gt_ids"]]
    output: list[dict[str, Any]] = []
    for k in ks:
        component_total = component_hit = paragraph_total = paragraph_hit = 0
        structured_total = structured_hit = query_hit = query_all = 0
        retrieved_by_key: dict[tuple[str, int], set[str]] = {}
        for item in eligible:
            key = (item["document_id"], item["metric_id"])
            retrieved = {alias for row in rankings[key][:k] for alias in row["alias_source_ids"]}
            retrieved_by_key[key] = retrieved
            gold = item["all_gt_ids"]
            matched = gold & retrieved
            component_total += len(gold)
            component_hit += len(matched)
            paragraph_total += len(item["paragraph_gt_ids"])
            paragraph_hit += len(item["paragraph_gt_ids"] & retrieved)
            structured_total += len(item["structured_gt_ids"])
            structured_hit += len(item["structured_gt_ids"] & retrieved)
            query_hit += bool(matched)
            query_all += matched == gold
        selected_groups = [
            group
            for group in groups
            if (group["document_id"], group["metric_id"]) in retrieved_by_key
        ]
        evidence_hits = sum(
            bool(group["ids"] & retrieved_by_key[(group["document_id"], group["metric_id"])])
            for group in selected_groups
        )
        output.append(
            {
                "top_k": k,
                "eligible_queries": len(eligible),
                "component_recall": component_hit / component_total if component_total else 0.0,
                "paragraph_component_recall": paragraph_hit / paragraph_total if paragraph_total else 0.0,
                "structured_component_recall": structured_hit / structured_total if structured_total else 0.0,
                "evidence_row_recall": evidence_hits / len(selected_groups) if selected_groups else 0.0,
                "query_hit_rate": query_hit / len(eligible) if eligible else 0.0,
                "query_hit_all_rate": query_all / len(eligible) if eligible else 0.0,
                "component_hits": component_hit,
                "component_total": component_total,
                "evidence_hits": evidence_hits,
                "evidence_total": len(selected_groups),
            }
        )
    return output


def detailed_metrics(
    queries: list[dict[str, Any]],
    groups: list[dict[str, Any]],
    rankings: dict[tuple[str, int], list[dict[str, Any]]],
    ks: list[int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups_by_key: dict[tuple[str, int], list[set[str]]] = defaultdict(list)
    for group in groups:
        groups_by_key[(group["document_id"], group["metric_id"])].append(group["ids"])
    per_query: list[dict[str, Any]] = []
    for item in queries:
        key = (item["document_id"], item["metric_id"])
        row: dict[str, Any] = {
            "document_id": item["document_id"],
            "metric_id": item["metric_id"],
            "metric_name": item["metric_name"],
            "gt_components": len(item["all_gt_ids"]),
            "gt_evidence_rows": len(groups_by_key.get(key, [])),
        }
        for k in ks:
            retrieved = {alias for result in rankings[key][:k] for alias in result["alias_source_ids"]}
            matched = item["all_gt_ids"] & retrieved
            evidence = groups_by_key.get(key, [])
            row[f"component_recall_at_{k}"] = len(matched) / len(item["all_gt_ids"]) if item["all_gt_ids"] else ""
            row[f"evidence_recall_at_{k}"] = sum(bool(ids_ & retrieved) for ids_ in evidence) / len(evidence) if evidence else ""
            row[f"hit_at_{k}"] = int(bool(matched)) if item["all_gt_ids"] else ""
        per_query.append(row)

    per_metric: list[dict[str, Any]] = []
    for metric_id in sorted({item["metric_id"] for item in queries}):
        items = [item for item in queries if item["metric_id"] == metric_id]
        row = {
            "metric_id": metric_id,
            "metric_name": items[0]["metric_name"],
            "documents": len(items),
            "eligible_documents": sum(bool(item["all_gt_ids"]) for item in items),
            "gt_components": sum(len(item["all_gt_ids"]) for item in items),
            "gt_evidence_rows": sum(len(groups_by_key.get((item["document_id"], metric_id), [])) for item in items),
        }
        for k in ks:
            component_hits = evidence_hits = query_hits = 0
            for item in items:
                key = (item["document_id"], metric_id)
                retrieved = {alias for result in rankings[key][:k] for alias in result["alias_source_ids"]}
                component_hits += len(item["all_gt_ids"] & retrieved)
                evidence_hits += sum(bool(ids_ & retrieved) for ids_ in groups_by_key.get(key, []))
                query_hits += bool(item["all_gt_ids"] & retrieved)
            row[f"component_recall_at_{k}"] = component_hits / row["gt_components"] if row["gt_components"] else ""
            row[f"evidence_recall_at_{k}"] = evidence_hits / row["gt_evidence_rows"] if row["gt_evidence_rows"] else ""
            row[f"query_hit_rate_at_{k}"] = query_hits / row["eligible_documents"] if row["eligible_documents"] else ""
        per_metric.append(row)
    return per_query, per_metric


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

