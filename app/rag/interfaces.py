from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from .models import Chunk, Document, EvidenceItem


class TextExtractor(Protocol):
    def extract(self, path: Path, mime: str) -> Document: ...


class OcrExtractor(Protocol):
    def extract(self, path: Path, mime: str) -> Document: ...


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class VectorStore(Protocol):
    def upsert(self, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None: ...

    def search(
        self, vector: Sequence[float], limit: int, *, document_ids: Sequence[str] | None = None
    ) -> list[dict[str, Any]]:
        """Search the index.

        ``document_ids`` restricts hits to the supplied documents. ``None`` means the
        whole index and is only safe for explicitly shared corpora; callers that serve
        per-task evidence must always pass the task's own document ids.
        """
        ...


class ReplaceableDocumentVectorStore(VectorStore, Protocol):
    def replace_document(
        self, document_id: str, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]
    ) -> None: ...


class Reranker(Protocol):
    def score(self, query: str, item: EvidenceItem) -> float: ...


class DocumentIngestor(Protocol):
    def ingest(self, path: Path, document_id: str, mime: str) -> list[Chunk]: ...
