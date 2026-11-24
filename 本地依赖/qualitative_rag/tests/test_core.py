import numpy as np

from esg_qualitative_rag.core import BM25, build_pool, select_without_reranker, tokenize


def corpus():
    return [
        {"paragraph_id": "P1", "text": "遵循 GHG Protocol 核算 Scope 1 和 Scope 2", "section": "排放", "alias_source_ids": ["P1"]},
        {"paragraph_id": "P2", "text": "公司设定节水目标", "section": "水资源", "alias_source_ids": ["P2"]},
        {"paragraph_id": "P3", "text": "披露排放因子与计算方法", "section": "方法", "alias_source_ids": ["P3"]},
    ]


def test_mixed_tokenizer_generates_chinese_ngrams():
    values = tokenize("温室气体 GHG Protocol")
    assert "温室" in values
    assert "ghg" in values
    assert "protocol" in values


def test_bm25_prefers_matching_document():
    model = BM25([tokenize(row["text"]) for row in corpus()])
    scores = model.scores(tokenize("温室气体核算"))
    assert int(np.argmax(scores)) == 0


def test_protected_selection_has_no_reranker_fields():
    rows = corpus()
    bm25 = np.asarray([3.0, 0.0, 1.0], dtype=np.float32)
    dense = np.asarray([0.9, 0.1, 0.7], dtype=np.float32)
    pool = build_pool(rows, bm25, dense, 3, {"standard": ("ghg protocol",)})
    selected = select_without_reranker(pool, {"standard": ("ghg protocol",)}, 2)
    assert len(selected) == 2
    assert selected[0]["retrieval_stage"].endswith("no_reranker")
    assert all("reranker_score" not in row for row in selected)
