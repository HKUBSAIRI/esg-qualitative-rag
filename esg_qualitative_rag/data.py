from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from .core import canonical_text, clean_text


def split_ids(value: Any) -> list[str]:
    return [item.strip() for item in str(value or "").split(";") if item.strip()]


def load_ground_truth(
    ground_truth_dir: Path, metric_ids: set[int]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    queries: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    workbooks = sorted(ground_truth_dir.glob("gt_53_*_新版格式.xlsx"))
    if not workbooks:
        raise ValueError(f"no GT workbooks found under {ground_truth_dir}")
    for path in workbooks:
        document_id = path.stem.split("gt_53_", 1)[1].split("_新版格式", 1)[0]
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            rows = workbook["GroundTruth"].iter_rows(values_only=True)
            header = next(rows)
            columns = {str(value or "").strip(): index for index, value in enumerate(header)}
            metric_id: int | None = None
            current: dict[str, Any] | None = None
            for values in rows:
                values = tuple(values) + (None,) * (len(header) - len(values))
                raw_metric = values[columns["指标序号"]]
                if raw_metric not in (None, ""):
                    metric_id = int(float(raw_metric))
                    if metric_id in metric_ids:
                        current = {
                            "document_id": document_id,
                            "metric_id": metric_id,
                            "metric_name": str(values[columns["指标名称"]] or "").strip(),
                            "definition": str(values[columns["指标定义"]] or "").strip(),
                            "scoring_method": str(values[columns["评分方法"]] or "").strip(),
                            "all_gt_ids": set(),
                            "paragraph_gt_ids": set(),
                            "structured_gt_ids": set(),
                        }
                        queries.append(current)
                    else:
                        current = None
                if metric_id not in metric_ids or current is None:
                    continue
                ids = set(split_ids(values[columns["chunk_id"]]))
                if not ids:
                    continue
                current["all_gt_ids"].update(ids)
                current["paragraph_gt_ids"].update(value for value in ids if value.startswith("P"))
                current["structured_gt_ids"].update(value for value in ids if not value.startswith("P"))
                groups.append(
                    {
                        "document_id": document_id,
                        "metric_id": metric_id,
                        "ids": ids,
                        "has_paragraph": any(value.startswith("P") for value in ids),
                    }
                )
        finally:
            workbook.close()
    return queries, groups


def load_metric_cards(path: Path) -> dict[int, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {int(item["idx"]): item for item in payload["metrics"]}


def unit_ids(chunk: dict[str, Any]) -> set[str]:
    values = {
        str(value)
        for value in (chunk.get("chunk_id"), chunk.get("paragraph_id"), chunk.get("retrieval_unit_id"))
        if value
    }
    values.update(str(value) for value in chunk.get("duplicate_chunk_ids", []) if value)
    return values


def chunk_section(chunk: dict[str, Any]) -> str:
    value = chunk.get("section_path") or chunk.get("section") or chunk.get("title") or []
    if isinstance(value, str):
        return clean_text(value)
    return " > ".join(clean_text(part) for part in value if clean_text(part))


def build_retrieval_text(chunk: dict[str, Any]) -> str:
    section = chunk_section(chunk) or "(unknown section)"
    return f"[Section]\n{section}\n\n[Content]\n{clean_text(chunk.get('text'))}"


def load_corpus(path: Path) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    by_text: dict[str, int] = {}
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            chunk = json.loads(line)
            text = clean_text(chunk.get("text"))
            key = canonical_text(text)
            if not key:
                continue
            if key in by_text:
                chunks[by_text[key]]["duplicate_chunk_ids"].append(chunk.get("chunk_id"))
                continue
            chunk["text"] = text
            chunk["duplicate_chunk_ids"] = []
            chunk["_line_number"] = line_number
            by_text[key] = len(chunks)
            chunks.append(chunk)
    if not chunks:
        raise ValueError(f"no non-empty chunks in {path}")
    return [
        {
            "paragraph_id": str(chunk["chunk_id"]),
            "alias_source_ids": sorted(unit_ids(chunk)),
            "section": chunk_section(chunk),
            "pages": list(chunk.get("pages") or chunk.get("pdf_pages") or []),
            "text": str(chunk.get("text") or ""),
            "retrieval_text": build_retrieval_text(chunk),
        }
        for chunk in chunks
    ]


def build_query(item: dict[str, Any], card: dict[str, Any]) -> str:
    parts = [
        item["metric_name"],
        item["metric_name"],
        item["definition"],
        item["scoring_method"],
        " ".join(card.get("anchor_terms_zh") or []),
        " ".join(card.get("anchor_terms_en") or []),
        " ".join(card.get("evidence_questions") or []),
    ]
    return " ".join(value for value in parts if value).strip()


def build_instruction(item: dict[str, Any], card: dict[str, Any]) -> str:
    questions = " ".join(card.get("evidence_questions") or [])
    exclusions = str(card.get("exclude_and_disambiguation") or "")
    return (
        "Assess whether the passage provides concrete evidence for the ESG indicator "
        f"'{item['metric_name']}'. Prefer explicit, auditable disclosure that answers: "
        f"{questions} Exclude or down-rank: {exclusions} Preserve relevant tables, notes, "
        "units, limitations, policies, targets, methods and coverage details."
    )

