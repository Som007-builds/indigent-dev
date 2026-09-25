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

    def search(self, vector: Sequence[float], limit: int) -> list[dict[str, Any]]: ...


class Reranker(Protocol):
    def score(self, query: str, item: EvidenceItem) -> float: ...


class DocumentIngestor(Protocol):
    def ingest(self, path: Path, document_id: str, mime: str) -> list[Chunk]: ...
