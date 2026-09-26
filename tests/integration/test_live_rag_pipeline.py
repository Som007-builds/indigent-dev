"""Live end-to-end verification of the production RAG path.

Gated on ``INDIGENT_RAG_LIVE=1``. Unlike the hermetic suite, nothing here is mocked:
``OllamaEmbeddingAdapter`` calls the real local Ollama server and ``QdrantVectorStore``
calls the real local Qdrant server, using the production settings from ``.env``
(``embeddinggemma:latest``, 768 dimensions, collection ``indigent_evidence``).

This proves the acceptance criteria for the real ingestion/retrieval milestone:
real 768-dimension vectors are stored with document provenance, retrieval returns the
semantically relevant chunk, cross-document leakage is impossible under task scope,
the lexical reranker participates, retrieved evidence keeps the provenance the
grounded answer layer needs, and embedding failures propagate instead of falling back.

Every vector used here is produced by the real embedder; none is synthetic. Per
docs/demo-runbook.md the Qdrant data volume is persistent, so this test never drops a
collection. It removes only the documents it created, through the production
``replace_document`` path.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.agent.state import TaskSnapshot
from app.config import Settings
from app.core.workspace import create_workspace
from app.deps import ProductionTaskRetriever, _build_rag_components
from app.rag.production import OllamaEmbeddingAdapter, ProductionDocumentIngestor
from app.rag.retrieval import LexicalReranker, Retriever

pytestmark = pytest.mark.skipif(
    os.environ.get("INDIGENT_RAG_LIVE") != "1",
    reason="set INDIGENT_RAG_LIVE=1 to exercise real Ollama embeddings and real Qdrant",
)

# Two documents of deliberately unrelated subject matter, each long enough to be split
# into several chunks by the production chunker (max_chars=1000, overlap_chars=100).
PUMP_DOCUMENT = """Rotating Equipment Inspection Standard RCP-PUMP-114.

The feedwater pump P-101A is a horizontal split-case centrifugal pump rated at 850 cubic
metres per hour against a total head of 145 metres. The design driver speed is 1480
revolutions per minute and the impeller diameter is 310 millimetres.

The pump is driven by a 250 kilowatt induction motor with class F insulation and a
thermistor winding for continuous temperature monitoring. Motor terminal box protection
is IP55 and the ambient design temperature is 45 degrees Celsius.

Bearing 101DE is a double row spherical roller bearing with an oil bath supplied by a
dedicated lube oil pump. The oil reservoir holds 40 litres of ISO VG 46 lubricant and the
sight glass ranges between 30 and 55 millimetres at normal operating level.

The mechanical seal is a cartridge type with a tungsten carbide seat and a carbon face.
The seal flush plan is API Plan 11 from the discharge nozzle. A piping crossover from the
seal chamber discharge to the flare is not required for this service.

Vibration acceptance at the drive end is 4.5 millimetres per second RMS measured at the
bearing housing in the velocity overall frequency band from 10 hertz to 1000 hertz.

The pump casing is ductile iron with a bronze impeller and a carbon steel shaft. The
casing mounting feet are bolted to a fabricated steel baseplate grouted with non-shrink
epoxy mortar. Coupling alignment tolerance is 0.05 millimetres offset and 0.04 degrees
angular misalignment.

Insulation resistance of the motor winding shall exceed 100 megohms at 500 volts DC
measured at ambient temperature of 40 degrees Celsius or lower.
"""

HYDROCARBON_DOCUMENT = """Crude Distillation Unit Operating Summary CDU-200.

The atmospheric crude distillation tower C-100 has a top temperature of 82 degrees
Celsius and a bottoms temperature of 348 degrees Celsius at a reduced pressure of 12
kilopascals. The tower has 42 trays numbered from the bottom as tray 1 to tray 42.

Light naphtha is drawn from tray 3 and routed to the naphtha splitter column N-101. The
naphtha cut point is defined by a 70 degree Celsius initial boiling point.

The vacuum column V-200 operates at 33 kilopascals absolute at the flash zone and
processes the atmospheric residue. Vacuum column bottoms yield a resid of 4.5 weight
percent sulphur. The vacuum ejector system uses three stages of steam ejectors.

Kerosene is withdrawn from tray 18 with a 190 degree Celsius flash point specification
and a maximum of 0.03 weight percent sulphur. Jet fuel kerosene is produced from the
same stream after the kero treating unit K-201 removes nitrogen compounds.

Diesel oil is drawn from tray 30 and has a cetane number of not less than 48. The
hydrotreater H-300 charges diesel from tray 32 and operates at a hydrogen pressure of
6.5 megapascals with a hydrogen to hydrocarbon ratio of 320 standard cubic metres per
cubic metre of feed.

Spent caustide solution from the side stripper is routed to the amine contactor C-210
for selective hydrogen sulfide removal before discharge to the effluent system.
"""


def _live_settings() -> Settings:
    """Load the operator's real configuration.

    ``tests/conftest.py`` deliberately points INDIGENT_ENV_FILE at a nonexistent file so
    the hermetic suite never inherits a machine-specific ``.env``. That isolation is
    correct and is not weakened here: this live test opts in explicitly by naming the
    env file, and only when the operator has set INDIGENT_RAG_LIVE=1.
    """
    env_file = Path(".env")
    if not env_file.is_file():
        pytest.skip("no operator .env present; this live test needs the real local config")
    return Settings(_env_file=env_file)


def _pipeline():
    """Real production components built from the real .env configuration."""
    settings = _live_settings()
    settings.validate_rag_configuration()
    rag, embedder, store = _build_rag_components(settings)
    return settings, rag.ingestor, embedder, store


@pytest.fixture
def live_rag(tmp_path):
    settings, ingestor, embedder, store = _pipeline()
    created: list[str] = []
    yield settings, ingestor, embedder, store, created
    # Remove only what this test created, through the production deletion path.
    for document_id in created:
        store.replace_document(document_id, [], [])


def _write_inputs(tmp_path: Path, task_id: str, documents: dict[str, str]) -> TaskSnapshot:
    workspace = create_workspace(tmp_path, task_id)
    for file_id, text in documents.items():
        (workspace / "inputs" / f"{file_id}.txt").write_text(text, encoding="utf-8")
    return TaskSnapshot(task_id, "inspection question", "inspection", "local", workspace)


# --- A/B: real ingestion with 768-dimensional vectors ---------------------------------


def test_real_ingestion_stores_768_dim_vectors(live_rag, tmp_path):
    settings, ingestor, embedder, store, created = live_rag
    created.append("live-pump-doc")

    assert embedder.model == settings.embedding_model == "embeddinggemma:latest"
    assert embedder.vector_size == 768 == settings.embedding_vector_size
    assert store.vector_size == 768, "collection must be configured for 768 dimensions"

    source = tmp_path / "pump.txt"
    source.write_text(PUMP_DOCUMENT, encoding="utf-8")
    chunks = ingestor.ingest(source, "live-pump-doc", "text/plain")

    assert len(chunks) > 1, "the production chunker must split a long document"
    assert all(chunk.document_id == "live-pump-doc" for chunk in chunks)
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks), "chunk ids are unique"

    # The same chunks re-embedded through the real adapter are 768-dimensional.
    vectors = embedder.embed([chunk.text for chunk in chunks])
    assert len(vectors) == len(chunks)
    assert all(len(vector) == 768 for vector in vectors)


def test_live_collection_dimension_is_768(live_rag):
    _, _, _, store, _ = live_rag
    info = store.client.get_collection(collection_name=store.collection)
    assert info.config.params.vectors.size == 768, (
        "live Qdrant collection must be 768-dimensional, matching EMBEDDING_VECTOR_SIZE"
    )


# --- C/D: retrieval relevance and cross-document isolation -----------------------------


@pytest.mark.asyncio
async def test_scoped_retrieval_is_relevant_and_never_leaks(live_rag, tmp_path):
    _, ingestor, embedder, store, created = live_rag
    created.extend(["live-pump-doc", "live-cdu-doc"])

    retriever = Retriever(embedder, store, LexicalReranker())
    task_retriever = ProductionTaskRetriever(ingestor, retriever)

    pump_task = _write_inputs(tmp_path, "live-task-pump", {"live-pump-doc": PUMP_DOCUMENT})
    cdu_task = _write_inputs(tmp_path, "live-task-cdu", {"live-cdu-doc": HYDROCARBON_DOCUMENT})
    await task_retriever(pump_task, ["live-pump-doc"], {"query": "bearing oil level"})
    await task_retriever(cdu_task, ["live-cdu-doc"], {"query": "diesel cetane number"})

    # C: a relevant query scoped to the pump document returns the pump fact.
    query = "how much lube oil does the bearing reservoir hold"
    scoped = await task_retriever(pump_task, ["live-pump-doc"], {"query": query})
    assert scoped, "scoped retrieval must return evidence"
    assert all(item["document_id"] == "live-pump-doc" for item in scoped)
    assert "40 litres" in scoped[0]["text"], f"got: {scoped[0]['text'][:140]!r}"
    assert "ISO VG 46" in scoped[0]["text"], "must be the bearing-lubrication chunk"

    # D: the same query scoped to the distillation document cannot return pump chunks.
    other = await task_retriever(cdu_task, ["live-cdu-doc"], {"query": query})
    assert all(item["document_id"] == "live-cdu-doc" for item in other)
    assert not any("oil reservoir" in item["text"] for item in other)

    # D: an empty scope admits nothing, and an unscoped query is refused outright.
    assert retriever.retrieve(query, limit=5, document_ids=[]).items == []
    with pytest.raises(ValueError, match="explicit document scope"):
        retriever.retrieve(query, limit=5)


@pytest.mark.asyncio
async def test_each_document_retrieves_only_its_own_top_fact(live_rag, tmp_path):
    """Bilateral check: pump query finds the pump fact, CDU query finds the CDU fact."""
    _, ingestor, embedder, store, created = live_rag
    created.extend(["live-pump-doc", "live-cdu-doc"])

    retriever = Retriever(embedder, store, LexicalReranker())
    task_retriever = ProductionTaskRetriever(ingestor, retriever)
    pump_task = _write_inputs(tmp_path, "live-task-bilateral", {"live-pump-doc": PUMP_DOCUMENT})
    cdu_task = _write_inputs(tmp_path, "live-task-bilateral", {"live-cdu-doc": HYDROCARBON_DOCUMENT})
    await task_retriever(pump_task, ["live-pump-doc"], {"query": "vibration acceptance"})
    await task_retriever(cdu_task, ["live-cdu-doc"], {"query": "diesel cetane"})

    vibration = await task_retriever(
        pump_task, ["live-pump-doc"], {"query": "vibration acceptance limit at the drive end"}
    )
    assert "4.5 millimetres per second RMS" in vibration[0]["text"]

    cetane = await task_retriever(
        cdu_task, ["live-cdu-doc"], {"query": "what cetane number is required for diesel oil"}
    )
    assert "cetane number of not less than 48" in cetane[0]["text"]
    assert all(item["document_id"] == "live-cdu-doc" for item in cetane)


# --- 10/11: reranking and provenance for the grounded answer layer --------------------


@pytest.mark.asyncio
async def test_retrieved_evidence_keeps_provenance_and_rerank_score(live_rag, tmp_path):
    from app.rag.chunking import source_sha256

    _, ingestor, embedder, store, created = live_rag
    created.append("live-pump-doc")

    retriever = Retriever(embedder, store, LexicalReranker())
    task_retriever = ProductionTaskRetriever(ingestor, retriever)
    task = _write_inputs(tmp_path, "live-task-prov", {"live-pump-doc": PUMP_DOCUMENT})
    source = task.workspace / "inputs" / "live-pump-doc.txt"

    items = await task_retriever(
        task, ["live-pump-doc"], {"query": "vibration acceptance limit at the drive end"}
    )
    assert items
    for item in items:
        assert item["document_id"] == "live-pump-doc"
        assert item["chunk_id"].startswith("live-pump-doc:")
        assert item["source_hash"] == source_sha256(source), "provenance must name the source"
        assert isinstance(item["text"], str) and item["text"].strip()
        assert item["source_reference"], "source reference must survive the round trip"
        assert item["retrieval_score"] is not None, "real Qdrant similarity must be present"
        assert item["reranking_score"] is not None, "the production reranker must participate"
    assert "4.5 millimetres per second RMS" in items[0]["text"]


# --- E: embedding failure propagates, never falls back ---------------------------------


def test_live_embedding_failure_propagates_and_persists_nothing(live_rag, tmp_path):
    import httpx

    settings, ingestor, embedder, store, created = live_rag
    created.append("live-fail-doc")

    # The other locally provisioned model is completion-only, so the real server refuses
    # to embed with it. This is a genuine live failure, not a stub.
    completion_only = "qwen3.8-27b-abliterated:latest"
    tags = {
        name
        for entry in embedder.client.get("/api/tags").json()["models"]
        for name in (entry.get("name"), entry.get("model"))
    }
    if completion_only not in tags:
        pytest.skip("completion-only model is not provisioned on this machine")

    failing_adapter = OllamaEmbeddingAdapter(settings.ollama_base_url, completion_only, 768)
    with pytest.raises(httpx.HTTPStatusError) as error:
        failing_adapter.embed(["this must not silently fall back"])
    assert error.value.response.status_code == 501

    failing_ingestor = ProductionDocumentIngestor(
        ingestor.extractor, failing_adapter, store, vector_size=768
    )
    source = tmp_path / "fail.txt"
    source.write_text(PUMP_DOCUMENT, encoding="utf-8")
    with pytest.raises(httpx.HTTPStatusError):
        failing_ingestor.ingest(source, "live-fail-doc", "text/plain")

    # Nothing was persisted and no fallback model was consulted.
    query_vector = embedder.embed(["probe for residue"])[0]
    assert store.search(query_vector, 10, document_ids=["live-fail-doc"]) == []


def test_live_ingestion_is_idempotent_and_replaces_stale_chunks(live_rag, tmp_path):
    """Re-ingesting the same document must not duplicate, and must drop stale chunks."""
    _, ingestor, embedder, store, created = live_rag
    created.append("live-residue-doc")
    source = tmp_path / "residue.txt"
    source.write_text(PUMP_DOCUMENT, encoding="utf-8")

    first = ingestor.ingest(source, "live-residue-doc", "text/plain")
    probe = embedder.embed(["bearing oil reservoir level"])[0]
    assert len(store.search(probe, 20, document_ids=["live-residue-doc"])) == len(first)

    source.write_text(HYDROCARBON_DOCUMENT, encoding="utf-8")
    second = ingestor.ingest(source, "live-residue-doc", "text/plain")
    assert len(second) == len(first)
    remaining = store.search(probe, 20, document_ids=["live-residue-doc"])
    assert all("oil reservoir" not in row["chunk"].text for row in remaining), (
        "stale chunks from the replaced document must be gone"
    )
