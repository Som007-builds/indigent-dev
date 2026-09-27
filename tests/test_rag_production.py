from __future__ import annotations

import os
import sys
import types
import uuid
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.contracts.models import FileRecord
from app.rag import (
    Chunk,
    Document,
    LexicalReranker,
    LocalEmbeddingError,
    LocalPDFTextExtractor,
    OllamaEmbeddingAdapter,
    ProductionDocumentIngestor,
    QdrantVectorStore,
    Retriever,
    chunk_document,
)


class FakeModels:
    class Distance:
        COSINE = "cosine"

    class VectorParams:
        def __init__(self, size, distance):
            self.size = size
            self.distance = distance

    class PointStruct:
        def __init__(self, id, vector, payload):
            self.id, self.vector, self.payload = id, vector, payload


class FakePoint:
    def __init__(self, payload, score=0.75):
        self.payload = payload
        self.score = score


class FakeClient:
    def __init__(self, exists=False):
        self.exists = exists
        self.created = []
        self.points = {}
        self.search_query = None

    def collection_exists(self, collection_name):
        return self.exists

    def get_collection(self, collection_name):
        return types.SimpleNamespace(config=types.SimpleNamespace(params=types.SimpleNamespace(vectors=types.SimpleNamespace(size=2))))

    def create_collection(self, **kwargs):
        self.created.append(kwargs)
        self.exists = True

    def upsert(self, collection_name, points, wait):
        for point in points:
            self.points[str(point["id"])] = types.SimpleNamespace(
                id=point["id"], vector=point["vector"], payload=point["payload"]
            )

    def delete_document(self, collection_name, document_id):
        self.points = {
            key: point for key, point in self.points.items()
            if point.payload.get("document_id") != document_id
        }

    def create_payload_index(self, collection_name, field_name, field_schema="keyword"):
        pass

    def query_points(self, **kwargs):
        self.search_query = kwargs
        allowed = None
        query_filter = kwargs.get("filter")
        if query_filter is not None:
            allowed = {str(value) for value in query_filter["must"][1]["match"]["any"]}
        points = [
            point
            for point in self.points.values()
            if allowed is None or point.payload.get("document_id") in allowed
        ]
        return types.SimpleNamespace(points=[FakePoint(point.payload) for point in points])


def install_fake_qdrant(monkeypatch):
    qdrant = types.ModuleType("qdrant_client")
    qdrant.QdrantClient = lambda **kwargs: None
    http = types.ModuleType("qdrant_client.http")
    http.models = FakeModels
    monkeypatch.setitem(sys.modules, "qdrant_client", qdrant)
    monkeypatch.setitem(sys.modules, "qdrant_client.http", http)
    monkeypatch.setitem(sys.modules, "qdrant_client.http.models", FakeModels)


def test_qdrant_initializes_collection_and_upserts_chunk_provenance(monkeypatch):
    install_fake_qdrant(monkeypatch)
    client = FakeClient()
    store = QdrantVectorStore("http://localhost:6333", "evidence", vector_size=2, client=client)
    chunk = Chunk(
        "doc:0", "doc", "sha256-value", "pressure stable", page=3,
        section="Operations", source_reference="manual.pdf", start_char=10,
        end_char=25, metadata={"source": "upload"},
    )
    store.upsert([chunk], [[0.1, 0.2]])
    assert client.created[0]["collection_name"] == "evidence"
    assert client.created[0]["vectors_config"] == {"size": 2, "distance": "Cosine"}
    point = client.points[str(uuid.uuid5(uuid.NAMESPACE_URL, "doc:0"))]
    assert point.payload["source_hash"] == "sha256-value"
    assert point.payload["page"] == 3
    assert point.payload["section"] == "Operations"
    assert point.payload["source_reference"] == "manual.pdf"
    assert point.payload["metadata"] == {"source": "upload"}


def test_qdrant_search_round_trip_retrieval_and_existing_reranker(monkeypatch):
    install_fake_qdrant(monkeypatch)
    client = FakeClient()
    store = QdrantVectorStore("http://127.0.0.1:6333", "evidence", vector_size=2, client=client)
    chunks = [
        Chunk("doc:0", "doc", "hash", "pump pressure stable", page=1, section="Ops"),
        Chunk("doc:1", "doc", "hash", "other content", page=2),
    ]
    store.upsert(chunks, [[1.0, 0.0], [0.0, 1.0]])
    store.search([1.0, 0.0], 2)
    assert client.search_query["with_payload"] is True
    assert client.search_query["filter"] is None
    scoped = store.search([1.0, 0.0], 2, document_ids=["doc"])
    assert client.search_query["filter"] == {
        "must": [
            {"key": "document_id", "is_empty": False},
            {"key": "document_id", "match": {"any": ["doc"]}},
        ]
    }
    assert {row["chunk"].chunk_id for row in scoped} == {"doc:0", "doc:1"}
    assert store.search([1.0, 0.0], 2, document_ids=["other"]) == []
    assert store.search([1.0, 0.0], 2, document_ids=[]) == []
    retriever = Retriever(type("Embed", (), {"embed": lambda self, texts: [[1.0, 0.0]]})(), store, LexicalReranker())
    result = retriever.retrieve("pump pressure", document_ids=["doc"])
    assert result.items[0].chunk_id == "doc:0"
    assert result.items[0].document_id == "doc"
    assert result.items[0].source_hash == "hash"
    assert result.items[0].page == 1
    assert result.items[0].section == "Ops"
    assert result.items[0].retrieval_score == 0.75
    assert result.items[0].reranking_score == 1.0


def test_qdrant_rest_transport_uses_local_http_api(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(404, json={"status": "not found"})
        return httpx.Response(200, json={"result": {"points": []}})

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kwargs: original_client(transport=transport, **kwargs)
    )
    store = QdrantVectorStore("http://localhost:6333", "evidence", vector_size=2)
    store.upsert([Chunk("doc:0", "doc", "hash", "text")], [[1.0, 0.0]])
    # Sequence: GET /collections/evidence (404), PUT /collections/evidence (create),
    # PUT /collections/evidence/index (payload index), PUT /collections/evidence/points (upsert)
    assert requests[0].url.path == "/collections/evidence"
    assert requests[1].url.path == "/collections/evidence"
    assert requests[2].method == "PUT"
    assert requests[2].url.path == "/collections/evidence/index"
    assert requests[3].method == "PUT"
    assert requests[3].url.path == "/collections/evidence/points"


def test_local_pdf_extractor_preserves_page_start_metadata(monkeypatch, tmp_path):
    class Page:
        def __init__(self, value):
            self.value = value

        def get_text(self, kind):
            return self.value

    class Pdf:
        def __enter__(self):
            return [Page("first page"), Page("second page")]

        def __exit__(self, *args):
            return None

    monkeypatch.setitem(sys.modules, "fitz", types.SimpleNamespace(open=lambda path: Pdf()))
    pdf_path = tmp_path / "manual.pdf"
    pdf_path.write_bytes(b"pdf bytes")
    document = LocalPDFTextExtractor().extract(pdf_path, "application/pdf")
    chunks = chunk_document(document, max_chars=10, overlap_chars=0)
    assert document.source_hash
    assert any(chunk.page == 1 for chunk in chunks)
    assert any(chunk.page == 2 for chunk in chunks)


def test_qdrant_existing_collection_dimension_mismatch_and_remote_url_fail(monkeypatch):
    install_fake_qdrant(monkeypatch)
    with pytest.raises(ValueError, match="loopback"):
        QdrantVectorStore("https://qdrant.example.com", "evidence", vector_size=2, client=FakeClient())
    client = FakeClient(exists=True)
    client.get_collection = lambda **kwargs: types.SimpleNamespace(
        config=types.SimpleNamespace(params=types.SimpleNamespace(vectors=types.SimpleNamespace(size=3)))
    )
    with pytest.raises(ValueError, match="vector size"):
        QdrantVectorStore("http://localhost:6333", "evidence", vector_size=2, client=client)


def test_ollama_embedding_adapter_batches_checks_model_and_dimension(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "embed-small:latest", "model": "embed-small:latest"}]})
        assert request.url.path == "/api/embed"
        return httpx.Response(200, json={"embeddings": [[0.25, 0.75], [0.5, 0.5]]})

    client = httpx.Client(base_url="http://localhost:11434", transport=httpx.MockTransport(handler))
    embedder = OllamaEmbeddingAdapter(
        "http://localhost:11434", "embed-small:latest", 2, client=client
    )
    vectors = embedder.embed(["valve pressure", "pump flow"])
    assert vectors == [[0.25, 0.75], [0.5, 0.5]]
    assert len(requests) == 2
    assert [request.url.path for request in requests] == ["/api/tags", "/api/embed"]


def test_ollama_embedding_empty_input_and_missing_or_invalid_model():
    class Client:
        def __init__(self, model_present=True, vectors=None):
            self.calls = []
            self.model_present = model_present
            self.vectors = vectors or [[0.1, 0.2]]

        def get(self, path):
            self.calls.append(("GET", path))
            names = [{"name": "embed:latest"}] if self.model_present else []
            return httpx.Response(200, request=httpx.Request("GET", "http://localhost" + path), json={"models": names})

        def post(self, path, json):
            self.calls.append(("POST", path, json))
            return httpx.Response(200, request=httpx.Request("POST", "http://localhost" + path), json={"embeddings": self.vectors})

    empty_client = Client()
    assert OllamaEmbeddingAdapter("http://localhost:11434", "embed:latest", 2, client=empty_client).embed([]) == []
    assert empty_client.calls == []

    unavailable = OllamaEmbeddingAdapter(
        "http://localhost:11434", "missing:latest", 2, client=Client(model_present=False)
    )
    with pytest.raises(LocalEmbeddingError, match="not provisioned"):
        unavailable.embed(["text"])

    bad_dimension = OllamaEmbeddingAdapter(
        "http://localhost:11434", "embed:latest", 3, client=Client()
    )
    with pytest.raises(LocalEmbeddingError, match="dimension"):
        bad_dimension.embed(["text"])


def test_ollama_embedding_repeated_input_is_stable_and_never_uses_remote_urls():
    class Client:
        def __init__(self):
            self.posts = 0

        def get(self, path):
            return httpx.Response(200, request=httpx.Request("GET", "http://localhost" + path), json={"models": [{"name": "embed:latest"}]})

        def post(self, path, json):
            self.posts += 1
            return httpx.Response(200, request=httpx.Request("POST", "http://localhost" + path), json={"embeddings": [[0.125, 0.875] for _ in json["input"]]})

    client = Client()
    embedder = OllamaEmbeddingAdapter("http://127.0.0.1:11434", "embed:latest", 2, client=client)
    first = embedder.embed(["same text"])
    second = embedder.embed(["same text"])
    assert first == second
    assert len(first[0]) == embedder.vector_size == 2
    with pytest.raises(ValueError, match="loopback"):
        OllamaEmbeddingAdapter("https://embedding.example", "embed", 2, client=client)



def test_ollama_embedding_live_integration_is_opt_in():
    if os.environ.get("INDIGENT_RAG_LIVE") != "1":
        pytest.skip("set INDIGENT_RAG_LIVE=1 to use a pre-provisioned local Ollama model")

    model = os.environ.get("EMBEDDING_MODEL")
    vector_size = os.environ.get("EMBEDDING_VECTOR_SIZE")
    if not model or not vector_size:
        pytest.fail("EMBEDDING_MODEL and EMBEDDING_VECTOR_SIZE must be configured for live test")
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    embedder = OllamaEmbeddingAdapter(base_url, model, int(vector_size))
    first = embedder.embed(["A pump maintains stable pressure."])
    second = embedder.embed(["A pump maintains stable pressure."])
    assert len(first) == 1
    assert len(first[0]) == int(vector_size)
    assert first[0] == second[0]


def test_ingestion_has_stable_ids_and_reingestion_upserts_once(tmp_path):
    path = tmp_path / "guide.txt"
    path.write_text("one two three\nfour five", encoding="utf-8")

    class Extractor:
        def extract(self, source, mime):
            from app.rag import PlainTextExtractor
            result = PlainTextExtractor().extract(source, mime)
            return Document("incoming-id", result.source_path, result.source_hash, result.text, mime, {"site": "A"})

    class Embed:
        def embed(self, texts):
            return [[1.0, float(len(text))] for text in texts]

    class Store:
        def __init__(self):
            self.by_id = {}
            self.upsert_batches = []

        def upsert(self, chunks, vectors):
            self.upsert_batches.append(list(chunks))
            self.by_id.update({chunk.chunk_id: (chunk, list(vector)) for chunk, vector in zip(chunks, vectors, strict=True)})

        def replace_document(self, document_id, chunks, vectors):
            self.by_id = {key: value for key, value in self.by_id.items() if value[0].document_id != document_id}
            self.upsert(chunks, vectors)

        def search(self, vector, limit):
            return []

    store = Store()
    ingest = ProductionDocumentIngestor(Extractor(), Embed(), store, max_chars=8, overlap_chars=1)
    first = ingest.ingest(path, "stable-doc", "text/plain")
    second = ingest.ingest(path, "stable-doc", "text/plain")
    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert all(chunk.document_id == "stable-doc" for chunk in second)
    assert len(store.by_id) == len(first)
    assert len(store.upsert_batches) == 2
    assert {chunk.source_hash for chunk in first} == {chunk.source_hash for chunk in second}
    assert first[0].metadata == {"site": "A"}


def test_reingestion_with_shorter_document_removes_stale_chunks(tmp_path):
    path = tmp_path / "changing.txt"
    path.write_text("a" * 30, encoding="utf-8")

    class Extractor:
        def extract(self, source, mime):
            from app.rag import PlainTextExtractor
            return PlainTextExtractor().extract(source, mime)

    class Embed:
        def embed(self, texts):
            return [[1.0, 0.0] for _ in texts]

    class Store:
        def __init__(self):
            self.points = {}

        def replace_document(self, document_id, chunks, vectors):
            self.points = {key: value for key, value in self.points.items() if value.document_id != document_id}
            self.points.update({chunk.chunk_id: chunk for chunk in chunks})

        def upsert(self, chunks, vectors):
            raise AssertionError("replace_document should be used")

        def search(self, vector, limit):
            return []

    store = Store()
    ingestion = ProductionDocumentIngestor(Extractor(), Embed(), store, max_chars=8, overlap_chars=1)
    first = ingestion.ingest(path, "doc", "text/plain")
    path.write_text("short", encoding="utf-8")
    second = ingestion.ingest(path, "doc", "text/plain")
    assert len(store.points) == len(second) < len(first)


@pytest.mark.asyncio
async def test_platform_ingestor_returns_failure_contract_and_success_count(tmp_path):
    from app.rag import ProductionRagIngestor

    path = tmp_path / "file.txt"
    path.write_text("some content", encoding="utf-8")

    class DocumentIngest:
        def ingest(self, path, document_id, mime):
            return [Chunk(f"{document_id}:0", document_id, "hash", "some content")]

    record = FileRecord(
        file_id="f1", task_id=None, kind="knowledge", original_name="file.txt",
        stored_path=str(path), size_bytes=12, sha256="hash", mime="text/plain",
    )
    result = await ProductionRagIngestor(DocumentIngest()).ingest(record)
    assert result.status == "ok" and result.chunks == 1

    class Failure:
        def ingest(self, *args):
            raise ValueError("unsupported")

    failed = await ProductionRagIngestor(Failure()).ingest(record)
    assert failed.status == "failed"
    assert "unsupported" in failed.error

    class Empty:
        def ingest(self, *args):
            return []

    empty = await ProductionRagIngestor(Empty()).ingest(record)
    assert empty.status == "failed"
    assert empty.chunks == 0


def test_ingestion_empty_document_does_not_embed_or_upsert(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")

    class Extractor:
        def extract(self, source, mime):
            return Document("d", str(source), "hash", "", mime)

    class Forbidden:
        def embed(self, texts):
            raise AssertionError("empty documents must not be embedded")

    class Store:
        def upsert(self, chunks, vectors):
            raise AssertionError("empty documents must not be stored")

        def search(self, vector, limit):
            return []

    assert ProductionDocumentIngestor(Extractor(), Forbidden(), Store()).ingest(path, "d", "text/plain") == []


def test_ingestion_embedding_and_qdrant_errors_are_not_swallowed(tmp_path):
    path = tmp_path / "doc.txt"
    path.write_text("something", encoding="utf-8")

    class Extractor:
        def extract(self, source, mime):
            return Document("d", str(source), "hash", "something", mime)

    class BadEmbed:
        def embed(self, texts):
            raise RuntimeError("embedding failed")

    class UnusedStore:
        def upsert(self, chunks, vectors):
            raise AssertionError

        def search(self, vector, limit):
            return []

    with pytest.raises(RuntimeError, match="embedding failed"):
        ProductionDocumentIngestor(Extractor(), BadEmbed(), UnusedStore()).ingest(path, "d", "text/plain")

    class Embed:
        def embed(self, texts):
            return [[1.0] for _ in texts]

    class BadStore(UnusedStore):
        def upsert(self, chunks, vectors):
            raise RuntimeError("Qdrant down")

    with pytest.raises(RuntimeError, match="Qdrant down"):
        ProductionDocumentIngestor(Extractor(), Embed(), BadStore()).ingest(path, "d", "text/plain")


def test_production_factory_uses_ollama_embedder(monkeypatch):
    import app.deps as deps
    import app.rag as rag

    settings = Settings(
        qdrant_url="http://127.0.0.1:6333",
        embedding_backend="ollama",
        embedding_model="embed-small:latest",
        embedding_vector_size=2,
    )
    seen = {}

    class Store:
        def __init__(self, url, collection, *, vector_size):
            seen["store"] = (url, collection, vector_size)

        def upsert(self, chunks, vectors):
            pass

        def search(self, vector, limit):
            return []

    monkeypatch.setattr(rag, "QdrantVectorStore", Store)
    pipeline = deps.build_production_rag(settings)
    assert pipeline.ingestor.embedder.__class__ is rag.OllamaEmbeddingAdapter
    assert pipeline.ingestor.embedder.model == "embed-small:latest"
    assert pipeline.ingestor.vector_size == 2
    assert seen["store"] == (settings.qdrant_url, settings.qdrant_collection, 2)


def test_unsupported_extraction_fails_and_rag_config_is_strict():
    from app.rag import PlainTextExtractor

    with pytest.raises(ValueError, match="unsupported"):
        PlainTextExtractor().extract(Path("fake.pdf"), "application/pdf")
    with pytest.raises(ValueError, match="required"):
        Settings().validate_rag_configuration()
    Settings(
        qdrant_url="http://127.0.0.1:6333", embedding_backend="ollama",
        embedding_model="local-model", embedding_vector_size=384,
    ).validate_rag_configuration()
    from app.deps import build_production_rag
    with pytest.raises(RuntimeError, match="Invalid production RAG configuration"):
        build_production_rag(Settings())
    with pytest.raises(ValueError, match="loopback"):
        Settings(
            qdrant_url="https://qdrant.example", embedding_backend="ollama",
            embedding_model="local-model", embedding_vector_size=384,
        ).validate_rag_configuration()
