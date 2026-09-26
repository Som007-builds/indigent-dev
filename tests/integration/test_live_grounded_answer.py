"""Live end-to-end verification of Grounded Answer + Citation Verification.

Gated on ``INDIGENT_RAG_LIVE=1``. Nothing is mocked.

Model roles are kept strictly separate and asserted here:
  * ``embeddinggemma:latest`` (300M) is the only embedding model. It produces the document
    and query vectors for RAG retrieval and is never asked to generate.
  * ``qwen3.8-27b-abliterated:latest`` (27B) is the only generation model. It is reached
    only after real evidence has been retrieved, for the grounded answer and for each
    citation verification.

This closes the gap the hermetic suite cannot: ``tests/test_grounded_answer.py`` drives
``GroundedAnswerGenerator`` and ``CitationVerifier`` with canned strings from a stub
provider, so neither the model's JSON discipline nor the verifier's judgement has ever
been exercised against a real model.

Phases, in order, per the milestone:
  PHASE 1 retrieval  real embeddinggemma vectors -> real Qdrant, scoped, with provenance
  PHASE 2 generation real Qwen grounded answer over that evidence only
  PHASE 3 verify     real citation verdicts: supported passes; unsupported, self-cited
                     fabrications, and another document's evidence all fail

Machine note (MacBook Air M5, 24 GB unified): the 27B model needs 16030 MB and takes
~19 GB resident, so it can only be held once. ``ResourceManager`` adds ``memory_mb`` to
``_reserved_memory_mb`` on load and only clears it on an explicit ``unload``, and it has no
unload hook in production, so the model is genuinely released through Ollama before each
generation. That is real management of a real constraint on this host: it relaxes no
assertion, substitutes no model output, and fails loudly if memory cannot be freed.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import httpx
import pytest
from test_live_rag_pipeline import HYDROCARBON_DOCUMENT, PUMP_DOCUMENT

from app.config import Settings
from app.core.db import Database
from app.core.repo import Repository
from app.deps import ProductionTaskRetriever, _build_rag_components, build_services
from app.rag.models import ClaimProvenance, EvidenceItem
from app.rag.retrieval import LexicalReranker, Retriever

pytestmark = pytest.mark.skipif(
    os.environ.get("INDIGENT_RAG_LIVE") != "1",
    reason="set INDIGENT_RAG_LIVE=1 to run real local generation for grounded answers",
)

EMBEDDING_MODEL = "embeddinggemma:latest"
GENERATION_MODEL = "qwen3.8-27b-abliterated:latest"
GENERATION_MEMORY_MB = 16030
PUMP_DOC = "live-ga-pump"
CDU_DOC = "live-ga-cdu"
TASK_ID = "live-grounded-answer"

_START = time.monotonic()


def _log(message: str) -> None:
    print(f"[{time.monotonic() - _START:7.1f}s] {message}", flush=True)


def _live_settings() -> Settings:
    env_file = Path(".env")
    if not env_file.is_file():
        pytest.skip("no operator .env present; this live test needs the real local config")
    settings = Settings(_env_file=env_file)
    settings.validate_rag_configuration()
    return settings


@pytest.fixture
async def live_plane():
    """Build real services. Nothing here loads a model or calls inference."""
    settings = _live_settings()
    database = Database(Path(settings.data_dir) / "db.sqlite")
    await database.initialize()
    _, plane, rag, _ = build_services(settings, repository=Repository(database))
    _, embedder, store = _build_rag_components(settings)
    created: list[str] = []
    yield settings, plane, ProductionTaskRetriever(rag.ingestor, Retriever(embedder, store, LexicalReranker())), store, created
    for document_id in created:
        store.replace_document(document_id, [], [])


async def _free_generation_slot(plane) -> None:
    """Release the resident 27B in Ollama and in the ResourceManager before generating."""
    router = plane.orchestrator.dependencies.answer_generator.router
    provider = router.providers["ollama"]
    with httpx.Client(timeout=30.0, trust_env=False) as client:
        resident = {
            entry.get("name") or entry.get("model")
            for entry in client.get(f"{provider.base_url}/api/ps").json().get("models", [])
        }
    for model in router.registry.models():
        if model.provider != "ollama" or model.model_id not in resident:
            continue
        await router.resources.unload(model)
        with httpx.Client(timeout=120.0, trust_env=False) as client:
            client.post(
                f"{provider.base_url}/api/generate",
                json={"model": model.model_id, "prompt": "", "keep_alive": 0},
            )
        _log(f"released {model.model_id} from Ollama")
    for attempt in range(120):
        available = router.resources.hardware.snapshot().ram_mb_available or 0
        if available >= GENERATION_MEMORY_MB:
            _log(f"admission budget ready: ram_mb_available={available}")
            return
        if attempt % 10 == 0:
            _log(f"waiting for memory: {available} MB < {GENERATION_MEMORY_MB} MB")
        await asyncio.sleep(1)
    pytest.fail(
        f"could not free {GENERATION_MEMORY_MB} MB for the real generation model; "
        "this 24 GB host cannot run the live generation test"
    )


def _write_inputs(tmp_path: Path, task_id: str, documents: dict[str, str]):
    from app.agent.state import TaskSnapshot
    from app.core.workspace import create_workspace

    workspace = create_workspace(tmp_path, task_id)
    for file_id, text in documents.items():
        (workspace / "inputs" / f"{file_id}.txt").write_text(text, encoding="utf-8")
    return TaskSnapshot(task_id, "inspection question", "inspection", "local", workspace)


async def _retrieve(task_retriever, task, file_ids, query) -> list[EvidenceItem]:
    """PHASE 1. Uses only the real embedding model and the real Qdrant collection."""
    fields = EvidenceItem.__dataclass_fields__
    started = time.monotonic()
    raw = await task_retriever(task, file_ids, {"query": query})
    evidence = [EvidenceItem(**{k: v for k, v in item.items() if k in fields}) for item in raw]
    _log(
        f"PHASE1 retrieved {[(e.chunk_id, e.document_id) for e in evidence]} "
        f"in {time.monotonic() - started:.1f}s"
    )
    return evidence


# --- 1/2: the model-role boundary is real and enforced ---------------------------------


async def test_model_roles_are_separate(live_plane):
    """EmbeddingGemma embeds; Qwen generates. Neither is ever used for the other's job."""
    settings, plane, _, _, _ = live_plane
    router = plane.orchestrator.dependencies.answer_generator.router
    _, embedder, _ = _build_rag_components(settings)

    assert embedder.model == EMBEDDING_MODEL
    assert embedder.vector_size == 768

    # resolve() acquires and loads the generation model, so an earlier live test may have
    # left it resident on this 24 GB host. Release it first, exactly as the real path does.
    await _free_generation_slot(plane)

    model, provider = router.resolve("inspection")
    assert model.model_id == GENERATION_MODEL
    assert model.model_id != embedder.model, "the embedding model must never be the generation model"
    assert provider.is_local() is True
    _log(f"roles: embedder={embedder.model} (768d)  generator={model.model_id}")


# --- 1-8 + 10: retrieval, real generation, real verification, sovereignty --------------


async def test_phases_retrieval_then_generation_then_verification(live_plane, tmp_path):
    settings, plane, task_retriever, _, created = live_plane
    created.append(PUMP_DOC)
    deps = plane.orchestrator.dependencies

    evidence = await _retrieve(
        task_retriever,
        _write_inputs(tmp_path, TASK_ID, {PUMP_DOC: PUMP_DOCUMENT}),
        [PUMP_DOC],
        "how much lube oil does the bearing reservoir hold",
    )
    assert evidence, "real retrieval must return evidence before any generation"
    chunk_ids = [item.chunk_id for item in evidence]
    assert all(item.document_id == PUMP_DOC for item in evidence), "document scope must hold"

    # Keep the generation workload small: one chunk is enough to ground one claim.
    focused = next((i for i in evidence if "40 litres" in i.text), evidence[0])

    before = dict(await plane.inference.sovereignty.snapshot())
    await _free_generation_slot(plane)
    started = time.monotonic()
    answer = await deps.answer_generator.generate(
        "How much lube oil does the bearing oil reservoir hold, and what lubricant grade is it?",
        [focused],
        task_id=TASK_ID,
    )
    _log(f"PHASE2 answer generated in {time.monotonic() - started:.1f}s")

    meta = answer.execution.metadata
    assert meta.model_id == GENERATION_MODEL
    assert meta.provider == "ollama" and meta.local is True and meta.mode == "local"
    assert meta.success is True
    assert answer.claims, "the model must ground at least one claim"
    for claim in answer.claims:
        assert claim.claim_id and claim.claim.strip() and claim.evidence_chunk_ids
        for cited in claim.evidence_chunk_ids:
            assert cited in chunk_ids, f"claim cited unknown chunk {cited}"
    _log(f"PHASE2 answer={answer.answer[:120]!r}")
    for claim in answer.claims:
        _log(f"PHASE2 claim {claim.claim_id}: {claim.claim[:100]!r} -> {claim.evidence_chunk_ids}")

    by_id = {item.chunk_id: item for item in evidence}
    for claim in answer.claims:
        await _free_generation_slot(plane)
        started = time.monotonic()
        result = await deps.citation_verifier.verify_citation(
            claim, by_id[claim.evidence_chunk_ids[0]], task_id=TASK_ID
        )
        _log(
            f"PHASE3 verify {claim.claim_id}: verified={result.verified} "
            f"conf={result.confidence:.2f} reason={result.reason[:70]!r} "
            f"({time.monotonic() - started:.1f}s)"
        )
        assert result.verified, f"grounded claim failed verification: {result.reason}"
        assert result.confidence >= deps.citation_verifier.threshold
        assert result.verification.passed is True
        assert result.evidence.chunk_id == claim.evidence_chunk_ids[0]
        assert result.evidence.source_hash == by_id[claim.evidence_chunk_ids[0]].source_hash

    after = dict(await plane.inference.sovereignty.snapshot())
    for key in ("external_api_calls", "external_connections", "external_bytes_out", "external_bytes_in"):
        assert before.get(key) == 0 and after.get(key) == 0, f"{key} moved during local generation"
    _log("sovereignty external counters still zero after local generation")


# --- 9/10/11: the verifier must reject, and must not trust self-reported citations ------


async def test_verifier_rejects_unsupported_self_cited_and_cross_document_claims(live_plane, tmp_path):
    _, plane, task_retriever, _, created = live_plane
    created.extend([PUMP_DOC, CDU_DOC])
    deps = plane.orchestrator.dependencies

    task = _write_inputs(
        tmp_path, f"{TASK_ID}-negatives", {PUMP_DOC: PUMP_DOCUMENT, CDU_DOC: HYDROCARBON_DOCUMENT}
    )
    pump_evidence = await _retrieve(
        task_retriever, task, [PUMP_DOC], "vibration acceptance at the drive end"
    )
    cdu_evidence = await _retrieve(
        task_retriever, task, [CDU_DOC], "diesel oil cetane number specification"
    )
    vibration = next(i for i in pump_evidence if "4.5 millimetres per second RMS" in i.text)
    cdu_chunk = next(i for i in cdu_evidence if "cetane" in i.text.lower())
    assert vibration.document_id != cdu_chunk.document_id

    cases = [
        (
            "unsupported",
            ClaimProvenance(
                "claim-unsupported",
                "The pump casing is rated for a maximum service pressure of 250 bar and the "
                "impeller is machined from marine-grade titanium alloy.",
                (vibration.chunk_id,),
            ),
            vibration,
        ),
        (
            "self-cited-fabrication",
            # Metadata is internally consistent and cites a real, correctly scoped chunk.
            # Only the text is fabricated, so a verifier that trusted evidence_chunk_ids
            # would wrongly pass this.
            ClaimProvenance(
                "claim-self-cited",
                "Bearing housing vibration at the drive end must not exceed 1.2 millimetres "
                "per second RMS over a 10 hertz to 1000 hertz band.",
                (vibration.chunk_id,),
            ),
            vibration,
        ),
        (
            "cross-document",
            ClaimProvenance(
                "claim-cross-doc",
                "Drive-end vibration acceptance at the pump bearing housing is 4.5 mm/s RMS.",
                (cdu_chunk.chunk_id,),
            ),
            cdu_chunk,
        ),
    ]
    for label, claim, evidence in cases:
        await _free_generation_slot(plane)
        started = time.monotonic()
        result = await deps.citation_verifier.verify_citation(claim, evidence, task_id=TASK_ID)
        _log(
            f"PHASE3 {label}: verified={result.verified} conf={result.confidence:.2f} "
            f"reason={result.reason[:70]!r} ({time.monotonic() - started:.1f}s)"
        )
        assert not result.verified, f"{label} claim wrongly passed verification"
        assert result.verification.passed is False

    # The verifier discriminates on content rather than refusing everything: the genuine
    # 4.5 mm/s figure against the same chunk must pass.
    truthful = ClaimProvenance(
        "claim-truthful", "Drive-end vibration acceptance is 4.5 mm/s RMS.", (vibration.chunk_id,)
    )
    await _free_generation_slot(plane)
    supported = await deps.citation_verifier.verify_citation(truthful, vibration, task_id=TASK_ID)
    _log(f"PHASE3 truthful-control: verified={supported.verified} conf={supported.confidence:.2f}")
    assert supported.verified, f"genuinely supported claim was rejected: {supported.reason}"
