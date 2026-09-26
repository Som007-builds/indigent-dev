from __future__ import annotations

import asyncio
import math
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from .chunking import chunk_document
from .interfaces import Embedder, TextExtractor, VectorStore
from .models import Chunk, Document


class LocalEmbeddingError(RuntimeError):
    pass


class OllamaEmbeddingAdapter:
    """Local Ollama embeddings over loopback HTTP; never pulls missing models."""

    def __init__(
        self,
        base_url: str,
        model: str,
        vector_size: int,
        *,
        timeout: float = 60.0,
        client: Any | None = None,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or (parsed.hostname or "").lower() not in {
            "localhost", "127.0.0.1", "::1"
        }:
            raise ValueError("Ollama embedding URL must target a loopback host")
        if not model.strip() or vector_size < 1:
            raise ValueError("Ollama embedding model and positive vector size are required")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.vector_size = vector_size
        self.timeout = timeout
        self.client = client or httpx.Client(
            base_url=self.base_url, timeout=timeout, trust_env=False
        )

    def _assert_model_is_local(self) -> None:
        response = self.client.get("/api/tags")
        response.raise_for_status()
        payload = response.json()
        models = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(models, list):
            raise LocalEmbeddingError("Ollama returned a malformed local model inventory")
        names = {
            name
            for item in models
            if isinstance(item, dict)
            for name in (item.get("name"), item.get("model"))
            if isinstance(name, str)
        }
        if self.model not in names:
            raise LocalEmbeddingError(
                f"configured embedding model {self.model!r} is not provisioned in local Ollama"
            )

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if any(not isinstance(text, str) for text in texts):
            raise ValueError("embedding inputs must be text")
        if not texts:
            return []
        self._assert_model_is_local()
        response = self.client.post(
            "/api/embed", json={"model": self.model, "input": list(texts)}
        )
        response.raise_for_status()
        payload = response.json()
        vectors = payload.get("embeddings") if isinstance(payload, dict) else None
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise LocalEmbeddingError("Ollama returned an invalid embedding batch")
        validated: list[list[float]] = []
        for vector in vectors:
            if not isinstance(vector, list) or len(vector) != self.vector_size:
                raise LocalEmbeddingError(
                    "Ollama embedding dimension does not match EMBEDDING_VECTOR_SIZE"
                )
            try:
                values = [float(value) for value in vector]
            except (TypeError, ValueError) as error:
                raise LocalEmbeddingError("Ollama returned nonnumeric embedding values") from error
            if any(not math.isfinite(value) for value in values):
                raise LocalEmbeddingError("Ollama returned non-finite embedding values")
            validated.append(values)
        return validated


def _document_filter(document_ids: Sequence[str] | None) -> dict[str, Any] | None:
    """Build a server-side Qdrant filter so scoping never under-returns a limited query.

    Qdrant 1.19 rejects bare ``{"has_key": ...}`` and bare ``{"match": ...}`` clauses inside
    ``must`` with a 400 "Expected some form of condition"; every clause must be a field
    condition carrying its own ``key``. The existence check is therefore expressed as
    ``is_empty: false``, which keeps the original intent (a point must actually carry a
    document_id) in the form the server accepts.
    """
    if document_ids is None:
        return None
    if isinstance(document_ids, (str, bytes)):
        raise ValueError("document scope must be a sequence of ids")
    ids = [str(value) for value in document_ids]
    present: dict[str, Any] = {"key": "document_id", "is_empty": False}
    if not ids:
        # Fail closed: an empty scope names a sentinel document that can never exist, so
        # the query matches nothing instead of everything.
        return {"must": [present, {"key": "document_id", "match": {"any": ["__indigent_no_document__"]}}]}
    return {"must": [present, {"key": "document_id", "match": {"any": ids}}]}


class QdrantVectorStore:
    """Persistent local Qdrant adapter implementing the existing VectorStore protocol."""

    def __init__(
        self,
        url: str,
        collection: str,
        *,
        vector_size: int,
        client: Any | None = None,
    ) -> None:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or host not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Qdrant URL must target a loopback host")
        if not collection or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in collection) or vector_size < 1:
            raise ValueError("Qdrant collection name and positive vector size are required")
        if client is None:
            client = _QdrantRestClient(url)
        self.client = client
        self.collection = collection
        self.vector_size = vector_size
        self._models = None
        self._initialize()

    def _initialize(self) -> None:
        exists = self.client.collection_exists(collection_name=self.collection)
        if exists:
            info = self.client.get_collection(collection_name=self.collection)
            actual_size = info.config.params.vectors.size
            if actual_size != self.vector_size:
                raise ValueError("configured Qdrant vector size does not match collection")
            return
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config={"size": self.vector_size, "distance": "Cosine"},
        )

    def upsert(self, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunk/vector count mismatch")
        if not chunks:
            return
        points = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            values = [float(value) for value in vector]
            if len(values) != self.vector_size or any(not math.isfinite(value) for value in values):
                raise ValueError("vector has invalid dimensions or values")
            points.append(
                {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_URL, chunk.chunk_id)),
                    "vector": values,
                    "payload": {
                        "chunk_id": chunk.chunk_id,
                        "document_id": chunk.document_id,
                        "source_hash": chunk.source_hash,
                        "text": chunk.text,
                        "page": chunk.page,
                        "section": chunk.section,
                        "source_reference": chunk.source_reference,
                        "start_char": chunk.start_char,
                        "end_char": chunk.end_char,
                        "metadata": chunk.metadata,
                    },
                }
            )
        self.client.upsert(collection_name=self.collection, points=points, wait=True)

    def replace_document(
        self, document_id: str, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]
    ) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunk/vector count mismatch")
        for vector in vectors:
            values = [float(value) for value in vector]
            if len(values) != self.vector_size or any(not math.isfinite(value) for value in values):
                raise ValueError("vector has invalid dimensions or values")
        self.client.delete_document(collection_name=self.collection, document_id=document_id)
        self.upsert(chunks, vectors)

    def search(
        self, vector: Sequence[float], limit: int, *, document_ids: Sequence[str] | None = None
    ) -> list[dict[str, Any]]:
        if limit < 1:
            return []
        if document_ids is not None and not list(document_ids):
            return []
        values = [float(value) for value in vector]
        if len(values) != self.vector_size or any(not math.isfinite(value) for value in values):
            raise ValueError("query vector has invalid dimensions or values")
        points = self.client.query_points(
            collection_name=self.collection,
            query=values,
            limit=limit,
            with_payload=True,
            with_vectors=False,
            filter=_document_filter(document_ids),
        ).points
        rows: list[dict[str, Any]] = []
        for point in points:
            payload = point.payload
            if not isinstance(payload, dict):
                raise ValueError("Qdrant returned a point without metadata")
            try:
                chunk = Chunk(
                    chunk_id=payload["chunk_id"],
                    document_id=payload["document_id"],
                    source_hash=payload["source_hash"],
                    text=payload["text"],
                    page=payload.get("page"),
                    section=payload.get("section"),
                    source_reference=payload.get("source_reference"),
                    start_char=payload.get("start_char", 0),
                    end_char=payload.get("end_char", 0),
                    metadata=payload.get("metadata", {}),
                )
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("Qdrant returned malformed chunk metadata") from error
            rows.append({"chunk": chunk, "score": float(point.score)})
        return rows


class _QdrantRestClient:
    """Minimal Qdrant REST transport; URL is already restricted to loopback."""

    def __init__(self, url: str) -> None:
        self._client = httpx.Client(base_url=url.rstrip("/"), timeout=10, trust_env=False)

    def collection_exists(self, collection_name: str) -> bool:
        collection_name = quote(collection_name, safe="")
        response = self._client.get(f"/collections/{collection_name}")
        if response.status_code == 404:
            return False
        response.raise_for_status()
        return True

    def get_collection(self, collection_name: str) -> Any:
        collection_name = quote(collection_name, safe="")
        response = self._client.get(f"/collections/{collection_name}")
        response.raise_for_status()
        data = response.json()["result"]
        vectors = data["config"]["params"]["vectors"]
        if isinstance(vectors, dict) and "size" not in vectors:
            raise ValueError("named Qdrant vector collections are not supported")
        return type("CollectionInfo", (), {
            "config": type("Config", (), {
                "params": type("Params", (), {"vectors": type("Vectors", (), {"size": vectors["size"]})()})()
            })()
        })()

    def create_collection(self, collection_name: str, vectors_config: dict[str, Any]) -> None:
        collection_name = quote(collection_name, safe="")
        response = self._client.put(
            f"/collections/{collection_name}",
            json={"vectors": vectors_config},
        )
        response.raise_for_status()

    def upsert(self, collection_name: str, points: list[dict[str, Any]], wait: bool) -> None:
        collection_name = quote(collection_name, safe="")
        response = self._client.put(
            f"/collections/{collection_name}/points",
            params={"wait": str(wait).lower()},
            json={"points": points},
        )
        response.raise_for_status()

    def delete_document(self, collection_name: str, document_id: str) -> None:
        collection_name = quote(collection_name, safe="")
        response = self._client.post(
            f"/collections/{collection_name}/points/delete",
            params={"wait": "true"},
            json={"filter": {"must": [{"key": "document_id", "match": {"value": document_id}}]}},
        )
        response.raise_for_status()

    def query_points(self, **kwargs: Any) -> Any:
        collection_name = quote(kwargs.pop("collection_name"), safe="")
        body: dict[str, Any] = {
            "query": kwargs["query"],
            "limit": kwargs["limit"],
            "with_payload": kwargs["with_payload"],
            "with_vector": kwargs["with_vectors"],
        }
        if kwargs.get("filter") is not None:
            body["filter"] = kwargs["filter"]
        response = self._client.post(
            f"/collections/{collection_name}/points/query",
            json=body,
        )
        response.raise_for_status()
        points = response.json()["result"]["points"]
        return type("QueryResult", (), {
            "points": [type("ScoredPoint", (), {"payload": p["payload"], "score": p["score"]})() for p in points]
        })()


class ProductionDocumentIngestor:
    """Extract, deterministically chunk, embed, and persist one source document."""

    def __init__(
        self,
        extractor: TextExtractor,
        embedder: Embedder,
        store: VectorStore,
        *,
        max_chars: int = 1000,
        overlap_chars: int = 100,
        vector_size: int | None = None,
    ) -> None:
        self.extractor = extractor
        self.embedder = embedder
        self.store = store
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars
        self.vector_size = vector_size

    def ingest(self, path: Path, document_id: str, mime: str) -> list[Chunk]:
        if not path.is_file():
            raise FileNotFoundError("source document does not exist")
        if not document_id.strip():
            raise ValueError("document_id must not be empty")
        document = self.extractor.extract(path, mime)
        if document.document_id != document_id:
            document = Document(
                document_id=document_id,
                source_path=document.source_path,
                source_hash=document.source_hash,
                text=document.text,
                mime=document.mime,
                metadata=document.metadata,
            )
        chunks = chunk_document(
            document, max_chars=self.max_chars, overlap_chars=self.overlap_chars
        )
        if not chunks:
            return []
        vectors = self.embedder.embed([chunk.text for chunk in chunks])
        if len(vectors) != len(chunks):
            raise ValueError("embedding interface returned an invalid result")
        if self.vector_size is not None and any(len(vector) != self.vector_size for vector in vectors):
            raise ValueError("embedding vector size does not match configured Qdrant vector size")
        replace_document = getattr(self.store, "replace_document", None)
        if callable(replace_document):
            replace_document(document_id, chunks, vectors)
        else:
            self.store.upsert(chunks, vectors)
        return chunks


class LocalDocumentExtractor:
    """Dispatch to installed local text extractors; unsupported formats fail closed."""

    def __init__(self) -> None:
        from .extractors import PlainTextExtractor

        self.plain_text = PlainTextExtractor()
        self.pdf = LocalPDFTextExtractor()

    def extract(self, path: Path, mime: str) -> Document:
        if mime in self.plain_text.supported_mimes:
            return self.plain_text.extract(path, mime)
        if mime == "application/pdf":
            return self.pdf.extract(path, mime)
        raise ValueError("unsupported document type for local RAG extraction")


class ProductionRagIngestor:
    """Async platform contract backed by local extraction, embeddings, and Qdrant."""

    def __init__(self, ingestor: ProductionDocumentIngestor) -> None:
        self.ingestor = ingestor

    async def ingest(self, file: Any) -> Any:
        from app.contracts.models import IngestResult

        try:
            chunks = await asyncio.to_thread(
                self.ingestor.ingest, Path(file.stored_path), file.file_id, file.mime
            )
            if not chunks:
                return IngestResult(file_id=file.file_id, status="failed", error="document contains no extractable text")
            return IngestResult(file_id=file.file_id, status="ok", chunks=len(chunks))
        except Exception as error:
            return IngestResult(
                file_id=file.file_id,
                status="failed",
                error=f"{type(error).__name__}: {error}",
            )


class LocalPDFTextExtractor:
    """Local PDF text extraction; scanned pages fail explicitly until OCR is available."""

    def extract(self, path: Path, mime: str) -> Document:
        if mime != "application/pdf":
            raise ValueError("unsupported document type for PDF extraction")
        try:
            import fitz
        except ImportError as error:
            raise RuntimeError("PyMuPDF is required for local PDF extraction") from error
        from .chunking import source_sha256

        with fitz.open(path) as pdf:
            pages = [page.get_text("text") for page in pdf]
        if not any(page.strip() for page in pages):
            raise RuntimeError("PDF contains no extractable text; local OCR is unavailable")
        page_starts: list[int] = []
        parts: list[str] = []
        offset = 0
        for page_text in pages:
            page_starts.append(offset)
            parts.append(page_text)
            offset += len(page_text) + 1
        text = "\n".join(parts)
        return Document(
            document_id=path.stem,
            source_path=str(path),
            source_hash=source_sha256(path),
            text=text,
            mime=mime,
            metadata={"page_count": len(pages), "page_starts": page_starts},
        )
