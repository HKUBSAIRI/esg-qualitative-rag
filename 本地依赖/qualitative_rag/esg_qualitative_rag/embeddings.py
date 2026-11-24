from __future__ import annotations

import hashlib
import http.client
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np


DEFAULT_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"


@dataclass
class Usage:
    api_calls: int = 0
    input_tokens: int = 0
    latency_seconds: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "api_calls": self.api_calls,
            "input_tokens": self.input_tokens,
            "total_tokens": self.input_tokens,
            "latency_seconds": round(self.latency_seconds, 3),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
        }


class DashScopeClient:
    def __init__(self, api_key: str | None = None, timeout: float = 120.0) -> None:
        self.api_key = str(api_key or os.getenv("DASHSCOPE_API_KEY") or "").strip()
        self.timeout = timeout

    def post(self, url: str, payload: dict[str, Any], usage: Usage) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError(
                "embedding cache miss and DASHSCOPE_API_KEY is not configured; "
                "copy .env.example or use the published complete cache"
            )
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        last_error: Exception | None = None
        for attempt in range(5):
            request = urllib.request.Request(
                url,
                data=encoded,
                method="POST",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                },
            )
            started = time.perf_counter()
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    result = json.loads(response.read().decode("utf-8"))
                usage.api_calls += 1
                usage.latency_seconds += time.perf_counter() - started
                return result
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")[:2000]
                last_error = RuntimeError(f"DashScope HTTP {exc.code}: {body}")
                if exc.code not in {429, 500, 502, 503, 504}:
                    break
            except (
                urllib.error.URLError,
                TimeoutError,
                http.client.IncompleteRead,
                ConnectionError,
                OSError,
                json.JSONDecodeError,
            ) as exc:
                last_error = exc
            time.sleep(2**attempt)
        raise RuntimeError(f"DashScope request failed after 5 attempts: {last_error}")


@dataclass
class DashScopeEmbedder:
    cache_dir: Path
    model_name: str = "qwen3.7-text-embedding"
    dimension: int = 1024
    batch_size: int = 10
    api_key: str | None = None
    api_base: str | None = None
    timeout: float = 120.0
    usage: Usage = field(default_factory=Usage)
    _client: DashScopeClient | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.api_base = str(self.api_base or os.getenv("DASHSCOPE_API_BASE") or DEFAULT_API_BASE).rstrip("/")
        self.cache_dir = Path(self.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def client(self) -> DashScopeClient:
        if self._client is None:
            self._client = DashScopeClient(self.api_key, self.timeout)
        return self._client

    @property
    def cache_path(self) -> Path:
        return self.cache_dir / f"{self.model_name.replace('/', '--')}_{self.dimension}.sqlite3"

    def _cache_key(self, text: str) -> str:
        return hashlib.sha256(f"{self.model_name}\0{self.dimension}\0{text}".encode()).hexdigest()

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        values = list(texts)
        if not values:
            return np.empty((0, self.dimension), dtype=np.float32)
        vectors: list[np.ndarray | None] = [None] * len(values)
        keys = [self._cache_key(text) for text in values]
        batch_size = max(1, min(int(self.batch_size), 20))
        with closing(sqlite3.connect(self.cache_path)) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS embeddings (cache_key TEXT PRIMARY KEY, "
                "vector BLOB NOT NULL, dimension INTEGER NOT NULL)"
            )
            for start in range(0, len(values), batch_size):
                indices = list(range(start, min(start + batch_size, len(values))))
                marks = ",".join("?" for _ in indices)
                cached = {
                    row[0]: np.frombuffer(row[1], dtype=np.float32).copy()
                    for row in connection.execute(
                        f"SELECT cache_key,vector FROM embeddings WHERE cache_key IN ({marks})",
                        [keys[index] for index in indices],
                    )
                }
                missing: list[int] = []
                for index in indices:
                    vector = cached.get(keys[index])
                    if vector is not None and vector.shape == (self.dimension,):
                        vectors[index] = vector
                        self.usage.cache_hits += 1
                    else:
                        missing.append(index)
                if not missing:
                    continue
                batch = [values[index] for index in missing]
                result = self.client.post(
                    f"{self.api_base}/embeddings",
                    {
                        "model": self.model_name,
                        "input": batch,
                        "dimensions": self.dimension,
                        "encoding_format": "float",
                    },
                    self.usage,
                )
                rows = sorted(result.get("data") or [], key=lambda item: int(item["index"]))
                if len(rows) != len(batch):
                    raise RuntimeError("DashScope returned an unexpected embedding row count")
                for local_index, item in enumerate(rows):
                    source_index = missing[local_index]
                    vector = np.asarray(item["embedding"], dtype=np.float32)
                    if vector.shape != (self.dimension,):
                        raise RuntimeError(f"unexpected embedding shape: {vector.shape}")
                    norm = float(np.linalg.norm(vector))
                    if norm > 0:
                        vector /= norm
                    vectors[source_index] = vector
                    connection.execute(
                        "INSERT OR REPLACE INTO embeddings(cache_key,vector,dimension) VALUES(?,?,?)",
                        (keys[source_index], vector.tobytes(), self.dimension),
                    )
                connection.commit()
                self.usage.cache_misses += len(missing)
                api_usage = result.get("usage") or {}
                self.usage.input_tokens += int(api_usage.get("total_tokens") or api_usage.get("prompt_tokens") or 0)
        if any(vector is None for vector in vectors):
            raise RuntimeError("embedding cache left unresolved vectors")
        return np.stack(vectors).astype(np.float32, copy=False)

