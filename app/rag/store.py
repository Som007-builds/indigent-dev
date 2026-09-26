from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from .models import Chunk


def _document_scope(document_ids: Sequence[str] | None) -> frozenset[str] | None:
    """Normalize a document scope; an empty scope admits nothing, not everything."""
    if document_ids is None:
        return None
    if isinstance(document_ids, (str, bytes)):
        raise ValueError("document scope must be a sequence of ids")
    return frozenset(str(value) for value in document_ids)


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

    def replace_document(
        self, document_id: str, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]
    ) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunk/vector count mismatch")
        retained = [(chunk, vector) for chunk, vector in self._rows if chunk.document_id != document_id]
        self._rows = retained
        self.upsert(chunks, vectors)

    def search(
        self, vector: Sequence[float], limit: int, *, document_ids: Sequence[str] | None = None
    ) -> list[dict[str, Any]]:
        if limit < 1:
            return []
        allowed = _document_scope(document_ids)
        scored = []
        for chunk, candidate in self._rows:
            if allowed is not None and chunk.document_id not in allowed:
                continue
            if len(candidate) != len(vector):
                continue
            denominator = math.sqrt(sum(item * item for item in candidate)) * math.sqrt(
                sum(item * item for item in vector)
            )
            score = sum(a * b for a, b in zip(candidate, vector, strict=True)) / denominator if denominator else 0.0
            scored.append({"chunk": chunk, "score": score})
        return sorted(scored, key=lambda row: row["score"], reverse=True)[:limit]
