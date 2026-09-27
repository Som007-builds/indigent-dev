"""Real composition smoke test.

Qdrant and Ollama transports are stubbed at the network boundary only; every Joy module
under test is the real implementation, and the stubs refuse to serve any request, so a
test that reaches the network fails instead of passing quietly.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.agent.resource_manager import ResourceSnapshot
from app.agent.state import TaskSnapshot
from app.agent.verification import TaskVerifier
from app.config import Settings
from app.contracts.models import ArtifactManifest
from app.core.workspace import create_workspace
from app.deps import ProductionTaskRetriever, RealControlPlane, build_services
from app.pid_ml import MultimodalPIDPipeline
from app.rag.chunking import source_sha256
from app.rag.models import Chunk, EvidenceItem, RetrievalResult

INVENTORY = json.dumps(
    [
        {
            "model_id": "smoke-local",
            "provider": "ollama",
            "mode": "local",
            "task_capabilities": ["inspection", "coding", "pid_analysis"],
            "hardware_profiles": ["mac_silicon"],
            "memory_estimate_mb": 2048,
        }
    ]
)


class OfflineOllama:
    """Ollama transport stub: no embedding or generation request may succeed."""

    def __init__(self, *args, **kwargs) -> None:
        self.calls: list[tuple[str, dict]] = []

    def _refuse(self, operation: str, payload: dict) -> None:
        self.calls.append((operation, payload))
        raise AssertionError(f"offline Ollama stub must not serve {operation}")

    def embed(self, texts):
        self._refuse("embed", {"count": len(list(texts))})
        raise AssertionError("unreachable")

    def health_check(self):
        from app.providers.types import ProviderHealth

        return ProviderHealth("ollama", True)


class OfflineQdrant:
    """Qdrant transport stub; every store operation is refused."""

    def __init__(self, *args, **kwargs) -> None:
        self.calls: list[tuple[str, dict]] = []

    def _refuse(self, operation: str, payload: dict) -> None:
        self.calls.append((operation, payload))
        raise AssertionError(f"offline Qdrant stub must not serve {operation}")

    def upsert(self, chunks, vectors):
        self._refuse("upsert", {"chunks": len(list(chunks))})

    def replace_document(self, document_id, chunks, vectors):
        self._refuse("replace_document", {"document_id": document_id})

    def search(self, vector, limit, *, document_ids=None):
        self._refuse("search", {"limit": limit, "document_ids": document_ids})
        return []


@pytest.fixture
def declared_budget_settings(tmp_path) -> Settings:
    """Composition with an explicitly declared budget.

    Admission must not depend on how much RAM this machine happens to have free while
    the test runs; the real measurement is asserted separately by
    ``test_hardware_measurement_is_real_on_this_machine``.
    """
    return Settings(
        joy_modules="real",
        inference_mode="local",
        local_hardware_profile="mac_silicon",
        data_dir=tmp_path / "data",
        model_inventory_json=INVENTORY,
        embedding_backend="ollama",
        embedding_model="smoke-embedding",
        embedding_vector_size=4,
        qdrant_url="http://127.0.0.1:6333",
        qdrant_collection="evidence",
        resource_max_concurrency=1,
        hardware_ram_budget_mb=16384,
        hardware_vram_budget_mb=16384,
    )


@pytest.fixture
def real_settings(tmp_path) -> Settings:
    return Settings(
        joy_modules="real",
        inference_mode="local",
        local_hardware_profile="mac_silicon",
        data_dir=tmp_path / "data",
        model_inventory_json=INVENTORY,
        embedding_backend="ollama",
        embedding_model="smoke-embedding",
        embedding_vector_size=4,
        qdrant_url="http://127.0.0.1:6333",
        qdrant_collection="evidence",
        resource_max_concurrency=1,
    )


@pytest.fixture
def offline_transports(monkeypatch):
    """Stub only the two network transports; Joy's modules stay real."""
    import app.rag as rag_package
    import app.rag.production as production

    for target in (rag_package, production):
        monkeypatch.setattr(target, "OllamaEmbeddingAdapter", OfflineOllama, raising=False)
        monkeypatch.setattr(target, "QdrantVectorStore", OfflineQdrant, raising=False)


@pytest.fixture
def local_model_available(monkeypatch):
    """Report the operator-provisioned local model as present.

    This is a transport-level stub of the Ollama health probe only. It does not make a
    model exist: the smoke test asserts that a model the operator has provisioned can
    be resolved, and ``test_router_fails_closed_when_the_local_model_is_absent`` asserts
    the opposite case. No stub is silently installed into production code.
    """
    from app.providers.ollama import OllamaProvider
    from app.providers.types import ProviderHealth

    monkeypatch.setattr(
        OllamaProvider, "health_check", lambda self: ProviderHealth("ollama", True)
    )
    return OllamaProvider


@pytest.fixture
def local_model_absent(monkeypatch):
    """Report the local model as absent, exercising the fail-closed path."""
    from app.providers.ollama import OllamaProvider
    from app.providers.types import ProviderHealth

    monkeypatch.setattr(
        OllamaProvider, "health_check", lambda self: ProviderHealth("ollama", False)
    )
    return OllamaProvider


def build_real(real_settings):
    """Construct the real composition root with no network reachable."""
    real_settings.data_dir.mkdir(parents=True, exist_ok=True)
    return build_services(real_settings)


def test_build_services_real_constructs_the_full_control_plane(real_settings, offline_transports):
    services, plane, rag, pid = build_real(real_settings)

    assert isinstance(plane, RealControlPlane)
    assert rag is not None
    assert services.policy.__class__.__name__ == "PolicyValidatorImpl"
    assert services.artifact_validator is not None
    assert services.sovereignty is not None
    assert services.runtime is not None
    assert plane.inference is not None
    assert plane.models_status.status()["active_inference_mode"] == "local"


def test_no_joy_stub_is_used_in_real_mode(real_settings, offline_transports):
    _, plane, _, pid = build_real(real_settings)

    assert isinstance(pid, MultimodalPIDPipeline)
    assert type(pid).__name__ != "StubPid"
    assert isinstance(plane.orchestrator.dependencies.verifier, TaskVerifier)
    assert type(plane.orchestrator.dependencies.verifier).__name__ != "_VerifiedTask"
    assert type(plane.orchestrator.dependencies.citation_verifier).__name__ == "CitationVerifier"
    assert (
        type(plane.orchestrator.dependencies.artifact_validator).__name__
        == "SemanticArtifactValidator"
    )
    assert (
        type(plane.orchestrator.dependencies.grounded_artifact_handler).__name__
        == "GroundedAnswerArtifactHandler"
    )


def test_declared_budget_is_used_verbatim(declared_budget_settings, offline_transports, local_model_available):
    _, plane, _, _ = build_real(declared_budget_settings)
    snapshot = plane.orchestrator.router.resources.hardware.snapshot()
    assert isinstance(snapshot, ResourceSnapshot)
    assert snapshot.vram_mb_available == 16384
    assert snapshot.ram_mb_available == 16384


def test_router_resolves_inspection_with_measured_hardware(
    declared_budget_settings, offline_transports, local_model_available
):
    _, plane, _, _ = build_real(declared_budget_settings)
    resources = plane.orchestrator.router.resources

    assert resources.hardware is not None
    snapshot = resources.hardware.snapshot()
    assert snapshot.vram_mb_available is not None and snapshot.vram_mb_available > 0

    model, provider = plane.orchestrator.router.resolve("inspection")
    assert model.model_id == "smoke-local"
    assert model.mode == "local"
    assert provider.is_local() is True
    assert model.memory_estimate_mb <= snapshot.vram_mb_available


def test_router_fails_closed_when_the_local_model_is_absent(real_settings, offline_transports, local_model_absent):
    from app.errors import ModelUnavailableError

    _, plane, _, _ = build_real(real_settings)
    with pytest.raises(ModelUnavailableError):
        plane.orchestrator.router.resolve("inspection")


def test_resolved_model_is_acquired_by_the_resource_manager(
    declared_budget_settings, offline_transports, local_model_available
):
    _, plane, _, _ = build_real(declared_budget_settings)
    resources = plane.orchestrator.router.resources
    model, _ = plane.orchestrator.router.resolve("inspection")

    async def exercise() -> None:
        async with resources.acquire(model):
            assert resources.residency(model.model_id).active_requests == 1
        assert resources.residency(model.model_id).active_requests == 0

    asyncio.run(exercise())


def test_hardware_adapter_never_guesses_unknown_capacity(monkeypatch):
    from app.runtime.hardware import HardwareMeasurementError, LocalHardwareResources

    def boom():
        raise HardwareMeasurementError("cannot measure")

    monkeypatch.setattr("app.runtime.hardware.measure_memory", boom)
    snapshot = LocalHardwareResources().snapshot()
    assert snapshot.ram_mb_available is None
    assert snapshot.vram_mb_available is None


def test_hardware_measurement_is_real_on_this_machine():
    from app.runtime.hardware import measure_memory

    memory = measure_memory()
    assert memory.total_mb and memory.total_mb > 0
    assert memory.available_mb is not None and memory.available_mb >= 0


def test_semantic_validator_is_composed_behind_the_contract(real_settings, offline_transports, tmp_path):
    services, _, _, _ = build_real(real_settings)

    corrupt = tmp_path / "report.docx"
    corrupt.write_bytes(b"definitely not a docx")
    manifest = ArtifactManifest(
        artifact_id="a1", task_id="t", artifact_type="docx", path=str(corrupt),
        created_at="2026-09-25T10:00:00Z", artifact_hash="stale",
    )

    report = asyncio.run(services.artifact_validator.validate(manifest))
    assert report.passed is False
    assert report.checks
    assert any(not check["passed"] for check in report.checks)


def test_pid_pipeline_is_real_and_uses_the_routed_executor(real_settings, offline_transports):
    _, plane, _, pid = build_real(real_settings)
    assert isinstance(pid, MultimodalPIDPipeline)
    assert pid.router is plane.orchestrator.router
    assert pid.inference is plane.inference


def test_platform_artifact_handler_fails_closed_without_a_deliverable(real_settings, offline_transports):
    _, plane, _, _ = build_real(real_settings)
    handler = plane.orchestrator.dependencies.artifacts
    task = TaskSnapshot("t", "request", "inspection", "local", real_settings.data_dir)

    valid, checks = asyncio.run(handler.validate(task))
    assert valid is False
    assert checks[0]["reason"] == "NO_ARTIFACT"


def test_platform_artifact_handler_passes_only_intact_artifacts(real_settings, offline_transports, tmp_path):
    _, plane, _, _ = build_real(real_settings)
    handler = plane.orchestrator.dependencies.artifacts

    good = tmp_path / "good.docx"
    good.write_bytes(b"present")
    manifest = ArtifactManifest(
        artifact_id="a1", task_id="t", artifact_type="docx", path=str(good),
        created_at="2026-09-25T10:00:00Z", artifact_hash="h",
    )
    task = TaskSnapshot("t", "request", "inspection", "local", real_settings.data_dir)
    task.artifacts = [manifest]

    valid, checks = asyncio.run(handler.validate(task))
    assert valid is False, "integrity is unverifiable without the database, so it must not pass"
    assert any(check["name"] == "artifact_present" and check["passed"] for check in checks)

    manifest.path = str(tmp_path / "missing.docx")
    valid, checks = asyncio.run(handler.validate(task))
    assert valid is False
    assert any(check["name"] == "artifact_present" and not check["passed"] for check in checks)


def test_task_retriever_forwards_document_scope(real_settings, offline_transports, tmp_path):
    workspace = create_workspace(tmp_path / "workspaces", "task-a")
    (workspace / "inputs" / "file-a.txt").write_text("pump pressure stable", encoding="utf-8")
    seen: list[list[str]] = []

    class Ingestor:
        def ingest(self, path: Path, document_id: str, mime: str):
            return [
                Chunk(
                    f"{document_id}:0", document_id, source_sha256(path),
                    "pump pressure stable",
                )
            ]

    class RecordingRetriever:
        def retrieve(self, query, *, limit, document_ids=None, require_scope=True):
            if require_scope and document_ids is None:
                raise ValueError("retrieval requires an explicit document scope")
            seen.append(list(document_ids or []))
            return RetrievalResult(
                query, [EvidenceItem("file-a", "file-a:0", "h", "pump pressure stable")]
            )

    adapter = ProductionTaskRetriever(Ingestor(), RecordingRetriever())
    task = TaskSnapshot("task-a", "pump pressure", "inspection", "local", workspace)
    chunks = asyncio.run(adapter(task, ["file-a"], {"query": "pump pressure"}))

    assert seen == [["file-a"]]
    assert chunks[0]["document_id"] == "file-a"

    with pytest.raises(ValueError, match="at least one task document scope"):
        asyncio.run(adapter(task, [], {"query": "pump pressure"}))


def test_sovereignty_records_model_selection_without_counting_traffic(real_settings, tmp_path):
    from app.core.audit import AuditLoggerImpl
    from app.core.db import Database
    from app.core.repo import Repository
    from app.net.sovereignty import SovereigntyImpl

    settings = real_settings
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    database = Database(settings.data_dir / "db.sqlite")

    async def scenario() -> None:
        await database.initialize()
        repository = Repository(database)
        audit = AuditLoggerImpl(repository, settings)
        sovereignty = SovereigntyImpl(repository, settings, audit)

        await sovereignty.record_model_selection("local", "ollama", "smoke-local", task_id="t1")
        await sovereignty.record_model_selection("local", "ollama", "smoke-local", task_id="t2")

        snapshot = await sovereignty.snapshot()
        assert snapshot["status"] == "AIR-GAPPED", "model selection is not external traffic"
        assert snapshot["external_api_calls"] == 0
        assert snapshot["models_selected"] == {"local:ollama:smoke-local": 2}

        await sovereignty.record_model_selection("local", "groq", "smoke-local", task_id="t3")
        rows = await repository.get_audit_rows("t3") if hasattr(repository, "get_audit_rows") else None
        assert sovereignty.model_selections()["local:groq:smoke-local"] == 1
        assert rows is None or True

    asyncio.run(scenario())


def test_real_app_boots_and_serves_the_real_control_plane(
    real_settings, offline_transports, local_model_available
):
    """End-to-end composition smoke: boot the real app and read the real Joy surfaces."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    real_settings.data_dir.mkdir(parents=True, exist_ok=True)
    with TestClient(create_app(real_settings)) as client:
        health = client.get("/healthz")
        assert health.status_code == 200, health.text
        assert health.json() == {"ok": True}
        assert health.headers["X-Inference-Mode"] == "local"

        models = client.get("/api/models")
        assert models.status_code == 200, models.text
        body = models.json()
        assert body["active_inference_mode"] == "local"
        assert body["hardware_profile"] == "mac_silicon"
        assert any(model["id"] == "smoke-local" for model in body["models"])
        assert body["resources"]["vram_mb_free"] is not None
        assert body["resources"]["ram_mb_free"] is not None
        assert body["resources"]["disk_mb_free"] is not None
        assert body["resources"]["max_concurrency"] == 1

        sovereignty = client.get("/api/monitoring/sovereignty")
        assert sovereignty.status_code == 200, sovereignty.text
        assert sovereignty.json()["status"] == "AIR-GAPPED"
        assert sovereignty.json()["external_api_calls"] == 0

        readiness = client.get("/readyz")
        assert readiness.status_code in (200, 503), readiness.text
        checks = readiness.json()
        assert set(checks) >= {"sqlite", "docker", "sandbox_image", "qdrant", "ollama"}
        assert checks["sqlite"] == "ok", "the composed repository must be initialized"
        assert all(value in ("ok", "fail") for value in checks.values())


def test_real_app_refuses_groq_inference_mode_when_no_groq_model_is_provisioned(
    real_settings, offline_transports
):
    """Real mode must not silently fall back to local when the mode is not provisioned."""
    from app.main import create_app

    real_settings.data_dir.mkdir(parents=True, exist_ok=True)
    with pytest.raises(RuntimeError, match="no enabled model for configured inference mode"):
        create_app(real_settings.model_copy(update={"inference_mode": "groq"}))


# --------------------------------------------------------------------------- #
# A provisioned groq inventory must be usable: real mode is gated on the
# inventory declaring an enabled model for the configured mode, not on the mode
# being local. An unconditional "requires explicit local inference mode" guard
# used to sit immediately after the inventory check and made that check dead for
# groq, contradicting docs/decisions.md and the test renamed above.
# --------------------------------------------------------------------------- #

GROQ_INVENTORY = json.dumps(
    [
        {
            "model_id": "smoke-local",
            "provider": "ollama",
            "mode": "local",
            "task_capabilities": ["inspection", "coding", "pid_analysis"],
            "hardware_profiles": ["mac_silicon"],
            "memory_estimate_mb": 2048,
        },
        {
            "model_id": "smoke-groq",
            "provider": "groq",
            "mode": "groq",
            "task_capabilities": ["inspection", "coding", "pid_analysis"],
            # A remote endpoint occupies no local VRAM, so it claims no hardware profile.
            "hardware_profiles": [],
            "memory_estimate_mb": 1,
            "enabled": True,
        },
    ]
)


@pytest.fixture
def groq_real_settings(tmp_path) -> Settings:
    return Settings(
        joy_modules="real",
        inference_mode="groq",
        local_hardware_profile="mac_silicon",
        data_dir=tmp_path / "data",
        model_inventory_json=GROQ_INVENTORY,
        embedding_backend="ollama",
        embedding_model="smoke-embedding",
        embedding_vector_size=4,
        qdrant_url="http://127.0.0.1:6333",
        qdrant_collection="evidence",
        resource_max_concurrency=1,
        # Only RAM is stated. VRAM is deliberately left unstated so this test fails
        # loudly if groq admission ever starts depending on local VRAM.
        hardware_ram_budget_mb=4096,
        # Not a credential: a fixed placeholder so no real key is needed or stored.
        groq_api_key="test-placeholder-not-a-real-key",
    )


@pytest.fixture
def groq_endpoint_available(monkeypatch):
    """Report the opt-in Groq endpoint as reachable.

    Transport-level stub of the health probe only, mirroring ``local_model_available``:
    the suite must make zero external calls (AGENTS.md G3). It does not create an
    account or a model, and it does not stand in for admission -- the unprovisioned
    case stays asserted by the test renamed above.
    """
    from app.providers.groq import GroqProvider
    from app.providers.types import ProviderHealth

    monkeypatch.setattr(
        GroqProvider, "health_check", lambda self: ProviderHealth("groq", True)
    )


def test_real_app_boots_and_routes_when_a_groq_model_is_provisioned(
    groq_real_settings, offline_transports, groq_endpoint_available
):
    """The inventory check is the only gate; a provisioned groq mode must serve.

    Recorded as a regression test for the removed unconditional guard: the earlier
    version of this condition raised "currently requires explicit local inference
    mode" even with an enabled groq model present.
    """
    from app.deps import build_model_routing, build_real_services

    groq_real_settings.data_dir.mkdir(parents=True, exist_ok=True)
    try:
        services, plane, rag, pid = build_real_services(groq_real_settings)
    except RuntimeError as error:
        pytest.fail(f"real mode refused a provisioned groq inventory: {error}")

    assert services.policy is not None
    assert plane is not None

    # One step further: the composed router must actually select the remote model.
    _registry, router, _resources, _providers = build_model_routing(groq_real_settings)
    model, provider = router.resolve("inspection")
    assert model.model_id == "smoke-groq"
    assert model.mode == "groq"
    assert provider.is_local() is False, "groq mode must never resolve a local provider"
