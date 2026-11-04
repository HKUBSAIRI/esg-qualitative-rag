import json

from esg_qualitative_rag.data import load_corpus


def test_load_corpus_deduplicates_and_preserves_alias(tmp_path):
    path = tmp_path / "retrieval_chunks.jsonl"
    rows = [
        {"chunk_id": "P1", "text": "same text", "pages": [1]},
        {"chunk_id": "P2", "text": "same  text", "pages": [2]},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    loaded = load_corpus(path)
    assert len(loaded) == 1
    assert loaded[0]["alias_source_ids"] == ["P1", "P2"]
