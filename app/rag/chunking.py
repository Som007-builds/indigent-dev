from __future__ import annotations

import hashlib
from pathlib import Path

from .models import Chunk, Document


def source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def chunk_document(
    document: Document,
    *,
    max_chars: int = 1000,
    overlap_chars: int = 100,
) -> list[Chunk]:
    if max_chars <= 0 or overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap must be non-negative and smaller than max_chars")
    text = document.text
    if not text:
        return []
    chunks: list[Chunk] = []
    start = 0
    index = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            boundary = text.rfind("\n", start, end)
            if boundary > start:
                end = boundary
        content = text[start:end]
        if content:
            chunk_id = f"{document.document_id}:{index}"
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    document_id=document.document_id,
                    source_hash=document.source_hash,
                    text=content,
                    source_reference=document.source_path,
                    start_char=start,
                    end_char=end,
                    metadata=dict(document.metadata),
                )
            )
            index += 1
        if end >= len(text):
            break
        start = max(end - overlap_chars, start + 1)
    return chunks
