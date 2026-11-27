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

