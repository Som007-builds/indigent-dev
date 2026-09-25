from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from .models import Chunk


class InMemoryVectorStore:
    """Deterministic local test store implementing the Qdrant-facing contract."""

    def __init__(self) -> None:
        self._rows: list[tuple[Chunk, list[float]]] = []

    def upsert(self, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunk/vector count mismatch")
        by_id = {chunk.chunk_id: (chunk, list(vector)) for chunk, vector in self._rows}
        for chunk, vector in zip(chunks, vectors, strict=True):
            by_id[chunk.chunk_id] = (chunk, list(vector))
        self._rows = list(by_id.values())

    def search(self, vector: Sequence[float], limit: int) -> list[dict[str, Any]]:
        if limit < 1:
            return []
        scored = []
        for chunk, candidate in self._rows:
            if len(candidate) != len(vector):
                continue
            denominator = math.sqrt(sum(item * item for item in candidate)) * math.sqrt(
                sum(item * item for item in vector)
            )
            score = sum(a * b for a, b in zip(candidate, vector, strict=True)) / denominator if denominator else 0.0
            scored.append({"chunk": chunk, "score": score})
        return sorted(scored, key=lambda row: row["score"], reverse=True)[:limit]
