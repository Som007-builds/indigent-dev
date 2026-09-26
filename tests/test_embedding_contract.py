"""Focused contract tests for the local embedding invariants.

These are code-contract tests, not live results: the HTTP transport is replaced so no
request can reach a model. The live path is proven by
``tests/test_rag_production.py::test_ollama_embedding_live_integration_is_opt_in``,
which requires a provisioned local embedding model (``INDIGENT_RAG_LIVE=1``).

What is asserted here is the set of properties that must hold no matter which local
embedding model is provisioned: explicit backend only, no fallback, strict dimension and
batch validation, rejection of empty/malformed vectors, and a local-only URL.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.rag.models import Document
from app.rag.production import (
    LocalEmbeddingError,
    OllamaEmbeddingAdapter,
    ProductionDocumentIngestor,
)


class ScriptedTransport(httpx.BaseTransport):
    """Serves only what a test declares; any undeclared request fails loudly."""

    def __init__(self, *, models: list[str] | None = None, embed_response=None, raw: str | None = None) -> None:
        self.models = ["embed-small:latest"] if models is None else models
        self.embed_response = embed_response
        self.raw = raw
        self.embed_calls: list[dict] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": n} for n in self.models]})
        if request.url.path == "/api/embed":
            self.embed_calls.append(json.loads(request.content))
            if self.raw is not None:
                return httpx.Response(200, content=self.raw)
            if self.embed_response is None:
                return httpx.Response(501, json={"error": "no embedding capability"})
            return httpx.Response(200, json=self.embed_response)
        raise AssertionError(f"unexpected request to {request.url.path}")


def adapter(transport: ScriptedTransport, model: str = "embed-small:latest", size: int = 4):
    return OllamaEmbeddingAdapter(
        "http://127.0.0.1:11434",
        model,
        size,
        client=httpx.Client(base_url="http://127.0.0.1:11434", transport=transport),
    )


# --- explicit backend, no alternative provider ---------------------------------------


def test_only_ollama_is_a_valid_embedding_backend():
    """There is no second backend to fall back to; anything else is refused at parse."""
    from pydantic import ValidationError

    assert Settings(embedding_backend="ollama").embedding_backend == "ollama"
    for rejected in ("openai", "groq", "sentence-transformers", "chromadb", "hash"):
        with pytest.raises(ValidationError):
            Settings(embedding_backend=rejected)
    assert Settings().embedding_backend is None


def test_unavailable_backend_refuses_rag_configuration():
    with pytest.raises(ValueError, match="required for production RAG"):
        Settings(embedding_backend=None, embedding_model=None).validate_rag_configuration()
    with pytest.raises(ValueError, match="required for production RAG"):
        Settings(embedding_backend="ollama", embedding_model=None).validate_rag_configuration()
    with pytest.raises(ValueError, match="must be positive"):
        Settings(
            embedding_backend="ollama", embedding_model="m", embedding_vector_size=None
        ).validate_rag_configuration()
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(embedding_backend="ollama", embedding_model="m", embedding_vector_size=0)


# --- successful embedding ------------------------------------------------------------


def test_successful_embedding_returns_validated_vectors():
    transport = ScriptedTransport(embed_response={"embeddings": [[0.1, 0.2, 0.3, 0.4]]})
    vectors = adapter(transport).embed(["pump pressure"])
    assert vectors == [[0.1, 0.2, 0.3, 0.4]]
    assert len(transport.embed_calls) == 1
    assert transport.embed_calls[0]["model"] == "embed-small:latest"


def test_batch_preserves_count_and_order():
    transport = ScriptedTransport(
        embed_response={"embeddings": [[0.1, 0.0, 0.0, 0.0], [0.0, 0.2, 0.0, 0.0]]}
    )
    vectors = adapter(transport).embed(["first", "second"])
    assert len(vectors) == 2
    assert vectors[0][1] == 0.0 and vectors[1][1] == 0.2


# --- wrong dimension, empty, malformed ----------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"embeddings": [[0.1, 0.2, 0.3]]},                       # too few dimensions
        {"embeddings": [[0.1, 0.2, 0.3, 0.4, 0.5]]},             # too many dimensions
        {"embeddings": [[0.1, 0.2, "x", 0.4]]},                  # non-numeric
        {"embeddings": [[]]},                                     # empty vector
        {"embeddings": []},                                       # empty batch for non-empty input
        {"embeddings": [[0.1, 0.2, 0.3, 0.4], [0.0, 0.0, 0.0, 0.0]]},  # count mismatch
        {"vectors": [[0.1, 0.2, 0.3, 0.4]]},                     # wrong response key
    ],
)
def test_invalid_embedding_payloads_are_rejected(payload):
    transport = ScriptedTransport(embed_response=payload)
    with pytest.raises(LocalEmbeddingError):
        adapter(transport).embed(["only one input"])


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_embedding_values_are_rejected(token):
    """Sent as a raw body because these are not valid JSON numbers for httpx."""
    transport = ScriptedTransport(raw=f'{{"embeddings": [[0.1, 0.2, {token}, 0.4]]}}')
    with pytest.raises(LocalEmbeddingError):
        adapter(transport).embed(["only one input"])


def test_empty_input_never_calls_the_model():
    transport = ScriptedTransport()
    assert adapter(transport).embed([]) == []
    assert transport.embed_calls == []


def test_non_text_input_is_rejected_before_any_request():
    transport = ScriptedTransport()
    with pytest.raises(ValueError):
        adapter(transport).embed(["ok", 42])
    assert transport.embed_calls == []


# --- unavailable model / backend ------------------------------------------------------


def test_unavailable_model_fails_closed_without_embedding():
    transport = ScriptedTransport(models=["some-other-model:latest"])
    with pytest.raises(LocalEmbeddingError, match="not provisioned in local Ollama"):
        adapter(transport).embed(["text"])
    assert transport.embed_calls == [], "must not embed when the model is absent"


def test_model_capability_failure_is_surfaced_not_swallowed():
    """The environment's real failure mode: model present, embedding unavailable."""
    transport = ScriptedTransport(embed_response=None)  # server answers 501
    with pytest.raises(httpx.HTTPStatusError) as error:
        adapter(transport).embed(["text"])
    assert error.value.response.status_code == 501


def test_malformed_model_inventory_is_rejected():
    class BadInventory(ScriptedTransport):
        def handle_request(self, request):
            if request.url.path == "/api/tags":
                return httpx.Response(200, json={"models": "not-a-list"})
            return super().handle_request(request)

    with pytest.raises(LocalEmbeddingError, match="malformed local model inventory"):
        adapter(BadInventory()).embed(["text"])


# --- no fallback ----------------------------------------------------------------------


def test_embedding_failure_never_falls_back_or_writes_to_qdrant():
    """A failing embedder must not reach the store, nor try an alternate backend."""
    writes: list[str] = []

    class RecordingStore:
        def upsert(self, chunks, vectors):
            writes.append("upsert")

        def replace_document(self, document_id, chunks, vectors):
            writes.append("replace_document")

    class FailingEmbedder:
        model = "embed-small:latest"

        def embed(self, texts):
            raise LocalEmbeddingError("embedding capability unavailable")

    class RecordingExtractor:
        def extract(self, path, mime):
            return Document(
                document_id="doc-1", source_path=str(path), source_hash="h",
                text="pump pressure stable", mime=mime, metadata={},
            )

    source = Path(__file__)
    ingestor = ProductionDocumentIngestor(
        RecordingExtractor(), FailingEmbedder(), RecordingStore(), vector_size=4
    )
    with pytest.raises(LocalEmbeddingError):
        ingestor.ingest(source, "doc-1", "text/plain")
    assert writes == [], "nothing may be persisted when embedding fails"


# --- local-only network behavior ------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://api.groq.com",
        "https://api.openai.com",
        "http://10.0.0.5:11434",
        "http://192.168.1.10:11434",
        "http://ollama.example.com:11434",
        "ftp://127.0.0.1",
    ],
)
def test_non_loopback_embedding_urls_are_refused(url):
    with pytest.raises(ValueError, match="loopback"):
        OllamaEmbeddingAdapter(url, "embed-small:latest", 4)


@pytest.mark.parametrize("url", ["http://127.0.0.1:11434", "http://localhost:11434", "http://[::1]:11434"])
def test_loopback_embedding_urls_are_accepted(url):
    assert OllamaEmbeddingAdapter(url, "embed-small:latest", 4).model == "embed-small:latest"


def test_embedding_and_generation_remain_separate_objects():
    """The embedder must not be the generation provider and must not share a client role."""
    from app.providers.ollama import OllamaProvider

    embedder = adapter(ScriptedTransport(embed_response={"embeddings": [[0.0, 0.0, 0.0, 0.0]]}))
    provider = OllamaProvider("http://127.0.0.1:11434", 60.0)
    assert isinstance(embedder, OllamaEmbeddingAdapter)
    assert not isinstance(embedder, OllamaProvider)
    assert not isinstance(provider, OllamaEmbeddingAdapter)
    assert not hasattr(embedder, "generate")
    assert not hasattr(embedder, "generate_with_images")


def test_constructor_rejects_non_positive_vector_size():
    for size in (0, -1):
        with pytest.raises(ValueError, match="positive vector size"):
            OllamaEmbeddingAdapter("http://127.0.0.1:11434", "embed-small:latest", size)
    assert OllamaEmbeddingAdapter("http://127.0.0.1:11434", "m", 768).vector_size == 768


def test_ingestor_rejects_vectors_that_disagree_with_configured_dimension():
    class Embedder:
        def embed(self, texts):
            return [[0.0, 0.0, 0.0]]  # 3 dimensions, configured 4

    class Extractor:
        def extract(self, path, mime):
            return Document(
                document_id="d", source_path=str(path), source_hash="h",
                text="pump", mime=mime, metadata={},
            )

    writes: list[str] = []

    class Store:
        def replace_document(self, document_id, chunks, vectors):
            writes.append("write")

    ingestor = ProductionDocumentIngestor(Extractor(), Embedder(), Store(), vector_size=4)
    with pytest.raises(ValueError, match="does not match configured Qdrant vector size"):
        ingestor.ingest(Path(__file__), "d", "text/plain")
    assert writes == []


# --- Qdrant filter shape accepted by the real server ----------------------------------


@pytest.mark.parametrize("document_ids", [["doc-a"], ["doc-a", "doc-b"], []])
def test_document_filter_uses_only_key_prefixed_field_conditions(document_ids):
    """Qdrant 1.19 answers 400 for bare ``has_key``/``match`` clauses inside ``must``.

    Asserting the emitted dict equals some literal is not enough: the previous shape looked
    reasonable and only failed against a live server. This locks every clause to the
    field-condition form Qdrant actually accepts, so a scoped query cannot 400 again. The
    live proof against a real Qdrant is tests/integration/test_live_rag_pipeline.py.
    """
    from app.rag.production import _document_filter

    clauses = _document_filter(document_ids)["must"]
    assert clauses, "a scoped filter must constrain something"
    for clause in clauses:
        assert "key" in clause, f"clause {clause!r} is not a field condition"
        assert "has_key" not in clause, f"bare has_key {clause!r} is rejected by Qdrant 1.19"
    matches = [clause["match"]["any"] for clause in clauses if "match" in clause]
    assert len(matches) == 1
    assert matches[0] == (["__indigent_no_document__"] if not document_ids else document_ids)
    assert {"key": "document_id", "is_empty": False} in clauses
