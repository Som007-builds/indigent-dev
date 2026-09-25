from __future__ import annotations

from pathlib import Path

from .chunking import source_sha256
from .models import Document


class PlainTextExtractor:
    """Local deterministic extractor for text-like documents.

    PDF/Office/OCR adapters remain interfaces until their dedicated ML/document
    phase; this extractor refuses unsupported formats rather than guessing.
    """

    supported_mimes = frozenset({"text/plain", "text/markdown", "text/csv", "application/json"})

    def extract(self, path: Path, mime: str) -> Document:
        if mime not in self.supported_mimes:
            raise ValueError("unsupported document type for plain-text extraction")
        return Document(
            document_id=path.stem,
            source_path=str(path),
            source_hash=source_sha256(path),
            text=path.read_text(encoding="utf-8"),
            mime=mime,
        )
