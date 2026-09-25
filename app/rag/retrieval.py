from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from .interfaces import Embedder, Reranker, VectorStore
from .models import EvidenceItem, RetrievalResult


class LexicalReranker:
    def score(self, query: str, item: EvidenceItem) -> float:
        terms = {term.lower() for term in query.split() if term}
        words = {term.lower() for term in item.text.split()}
        return len(terms & words) / len(terms) if terms else 0.0


class Retriever:
    def __init__(self, embedder: Embedder, store: VectorStore, reranker: Reranker | None = None) -> None:
        self.embedder = embedder
        self.store = store
        self.reranker = reranker

    def retrieve(self, query: str, *, limit: int = 5) -> RetrievalResult:
        if not isinstance(query, str) or not query.strip() or limit < 1:
            return RetrievalResult(query=query if isinstance(query, str) else "")
        vectors = self.embedder.embed([query])
        if len(vectors) != 1:
            raise ValueError("embedding interface returned an invalid result")
        rows = self.store.search(vectors[0], limit)
        items: list[EvidenceItem] = []
        for row in rows:
            item = self._item(row)
            reranking_score = self.reranker.score(query, item) if self.reranker else None
            items.append(
                EvidenceItem(
                    **{**item.__dict__, "reranking_score": reranking_score}
                )
            )
        if self.reranker:
            items.sort(key=lambda item: item.reranking_score or 0.0, reverse=True)
        return RetrievalResult(query=query, items=items)

    def _item(self, row: dict[str, Any]) -> EvidenceItem:
        if not isinstance(row, dict):
            raise ValueError("malformed retrieval result")
        raw_chunk = row.get("chunk")
        if is_dataclass(raw_chunk) and not isinstance(raw_chunk, type):
            chunk = asdict(raw_chunk)  # type: ignore[arg-type]
        elif isinstance(raw_chunk, dict):
            chunk = raw_chunk
        else:
            raise ValueError("malformed retrieval result")
        required = ("document_id", "chunk_id", "source_hash", "text")
        if any(not isinstance(chunk.get(field), str) for field in required):
            raise ValueError("malformed retrieval result metadata")
        score = row.get("score")
        if score is not None and not isinstance(score, (int, float)):
            raise ValueError("malformed retrieval score")
        return EvidenceItem(
            document_id=chunk["document_id"],
            chunk_id=chunk["chunk_id"],
            source_hash=chunk["source_hash"],
            text=chunk["text"],
            page=chunk.get("page"),
            section=chunk.get("section"),
            source_reference=chunk.get("source_reference"),
            retrieval_score=float(score) if score is not None else None,
        )
