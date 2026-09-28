"""The active inference mode must have exactly one truth, reported by every surface.

The Sovereignty Monitor is the product's central claim, so a mode disagreement is a
security defect, not a cosmetic one. Three surfaces expose the mode and must never
diverge: the ``X-Inference-Mode`` response header, the ``active_inference_mode``
field of ``GET /api/models``, and the ``inference_mode``/``status`` pair of
``GET /api/monitoring/sovereignty``.

The mode is read from configuration only (``INFERENCE_MODE``); no surface may infer
it, default it, or hardcode it. A stub that reports ``"local"`` while the process runs
in ``groq`` mode makes the monitor lie about external inference being active.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.stubs.models_status import StubModelsStatus

MODES = ["local", "groq"]


@pytest.fixture(autouse=True)
def hermetic_groq_resolution(monkeypatch):
    """Keep booting in ``groq`` mode free of external DNS.

    The egress guard resolves ``api.groq.com`` at startup to build its allow-list.
    That lookup is correct production behavior but is a network call, and the suite
    must make none. Mode reporting is not what is under test here, so the resolver
    is replaced with a fixed answer; egress policy keeps its own coverage.
    """
    monkeypatch.setattr("app.net.egress_guard._resolve_groq", lambda: {"203.0.113.10"})


def _client(tmp_path, mode: str) -> TestClient:
    return TestClient(create_app(Settings(data_dir=tmp_path, inference_mode=mode)))


@pytest.mark.parametrize("mode", MODES)
def test_models_endpoint_reports_the_configured_mode(tmp_path, mode: str) -> None:
    with _client(tmp_path, mode) as client:
        response = client.get("/api/models")
    assert response.status_code == 200
    assert response.json()["active_inference_mode"] == mode


@pytest.mark.parametrize("mode", MODES)
def test_every_mode_survacing_surface_agrees(tmp_path, mode: str) -> None:
    """One configuration value, three surfaces, zero room for disagreement."""
    with _client(tmp_path, mode) as client:
        header = client.get("/healthz").headers["X-Inference-Mode"]
        models = client.get("/api/models").json()
        sovereignty = client.get("/api/monitoring/sovereignty").json()

    assert header == mode
    assert models["active_inference_mode"] == mode
    assert sovereignty["inference_mode"] == mode
    assert {header, models["active_inference_mode"], sovereignty["inference_mode"]} == {mode}


def test_groq_mode_is_never_presented_as_air_gapped(tmp_path) -> None:
    with _client(tmp_path, "groq") as client:
        sovereignty = client.get("/api/monitoring/sovereignty").json()
    assert sovereignty["status"] != "AIR-GAPPED"
    assert sovereignty["status"] == "EXTERNAL INFERENCE ACTIVE"


def test_local_mode_reports_air_gapped(tmp_path) -> None:
    with _client(tmp_path, "local") as client:
        sovereignty = client.get("/api/monitoring/sovereignty").json()
    assert sovereignty["status"] == "AIR-GAPPED"


@pytest.mark.parametrize("mode", MODES)
def test_stub_models_status_reads_settings_rather_than_a_literal(mode: str) -> None:
    settings = Settings(inference_mode=mode)
    assert StubModelsStatus(settings).status()["active_inference_mode"] == mode


def test_stub_models_status_keeps_the_documented_response_shape() -> None:
    """Fixing the mode must not quietly drop or rename contract fields.

    ``active_model_id`` was added deliberately (Frontend-fix.md item 2.4): the frontend
    reads it from ``GET /api/models`` to know which model is selected, and previously
    the value set via ``POST /api/models/active`` was acknowledged but never returned.
    """
    body = StubModelsStatus(Settings()).status()
    assert set(body) == {
        "active_inference_mode",
        "hardware_profile",
        "active_model_id",
        "models",
        "resident_models",
        "resources",
    }
    assert set(body["resources"]) == {
        "vram_mb_free",
        "ram_mb_free",
        "disk_mb_free",
        "max_concurrency",
    }


def test_stub_models_status_reports_no_active_model_before_any_selection() -> None:
    """A key that is absent is indistinguishable from a selection that was dropped.

    The stub must emit ``active_model_id: null`` rather than omitting the key, so the
    frontend can tell "nothing selected yet" from "this build does not report it".
    """
    body = StubModelsStatus(Settings()).status()
    assert "active_model_id" in body
    assert body["active_model_id"] is None


def test_stub_models_status_round_trips_a_selection() -> None:
    """POST /api/models/active must be observable on the next GET /api/models."""
    stub = StubModelsStatus(Settings())
    assert stub.status()["active_model_id"] is None

    stub.set_active_model("some-local-model")

    body = stub.status()
    assert body["active_model_id"] == "some-local-model"
    # Recording a selection is not a claim that anything is loaded: the stub has no
    # registry, so it must still report zero models and nothing resident.
    assert body["models"] == []
    assert body["resident_models"] == []


def test_model_selection_round_trips_through_the_api(tmp_path) -> None:
    """The switcher must survive a reload (Frontend-fix.md item 2.4)."""
    with _client(tmp_path, "local") as client:
        assert client.get("/api/models").json()["active_model_id"] is None

        ok = client.post("/api/models/active", json={"model_id": "local-model-a"})
        assert ok.status_code == 200
        assert ok.json()["active_model_id"] == "local-model-a"

        assert client.get("/api/models").json()["active_model_id"] == "local-model-a"


def test_registration_that_cannot_be_stored_is_reported_as_such(tmp_path) -> None:
    """A discarded write must never be acknowledged as stored.

    ``StubModelsStatus`` has no registry, so ``POST /api/models`` cannot honour the
    registration. It used to return ``{"status": "ok"}`` anyway, which the frontend
    rendered as a successful registration (Frontend-fix.md item 1.12).
    """
    with _client(tmp_path, "local") as client:
        res = client.post("/api/models", json={"id": "x", "name": "Some Model"})

    assert res.status_code == 501
    assert res.json()["error"]["code"] == "MODEL_REGISTRY_UNSUPPORTED"
