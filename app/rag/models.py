from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Document:
    document_id: str
    source_path: str
    source_hash: str
    text: str
    mime: str = "text/plain"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    source_hash: str
    text: str
    page: int | None = None
    section: str | None = None
    source_reference: str | None = None
    start_char: int = 0
    end_char: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceItem:
    document_id: str
    chunk_id: str
    source_hash: str
    text: str
    page: int | None = None
    section: str | None = None
    source_reference: str | None = None
    retrieval_score: float | None = None
    reranking_score: float | None = None


@dataclass(frozen=True)
class RetrievalResult:
    query: str
    items: list[EvidenceItem] = field(default_factory=list)


@dataclass(frozen=True)
class ClaimProvenance:
    claim_id: str
    claim: str
    evidence_chunk_ids: tuple[str, ...] = ()
    verification_id: str | None = None
    artifact_id: str | None = None


@dataclass(frozen=True)
class VerificationProvenance:
    verification_id: str
    claim_id: str
    passed: bool
    confidence: float | None = None
    detail: str | None = None


@dataclass(frozen=True)
class ArtifactProvenance:
    artifact_id: str
    claim_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceProvenance:
    document_id: str
    chunk_id: str
    source_hash: str
    claim_id: str | None = None
    verification_id: str | None = None
    artifact_id: str | None = None
