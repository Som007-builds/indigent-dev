from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.agent.registry import ModelRegistry
from app.agent.resource_manager import ResourceManager
from app.agent.router import ModelRouter
from app.config import Settings
from app.errors import ModelUnavailableError
from app.pid_ml import MultimodalPIDPipeline, StructuredPIDGraph
from app.pid_ml.pipeline import PIDModelOutputError
from app.providers.types import InferenceResult, ModelInfo, ProviderHealth


class Provider:
    def __init__(self, response: str):
        self.response = response
        self.calls = 0

    def is_local(self): return True
    def health_check(self): return ProviderHealth("ollama", True)
    def generate(self, model_id, messages, tools=None):
        self.calls += 1
        return InferenceResult(self.response, model_id, "ollama")


def graph_payload():
    return {
        "nodes": [{"node_id": "n-1", "category": "pump", "label": "P-101", "bbox": [1, 2, 3, 4], "confidence": 0.8, "image_id": "image-1"}],
        "edges": [{"edge_id": "e-1", "source_node_id": "n-1", "target_node_id": "n-1", "relationship": "connects", "confidence": 0.7, "image_id": "image-1"}],
        "overlay_image_path": "overlay.png",
        "narrative": "Pump P-101 is connected to itself in this synthetic fixture.",
        "confidence_summary": {"overall": 0.75},
    }


def pipeline(response, *, mode: str = "local"):
    provider = Provider(response)
    model = ModelInfo("vlm", "vlm", "ollama", "local", frozenset({"pid_analysis"}), frozenset({"mac_silicon"}))
    router = ModelRouter(Settings(inference_mode=mode), ModelRegistry([model]), {"ollama": provider}, ResourceManager())  # type: ignore[arg-type]
    return MultimodalPIDPipeline(router), provider


def test_valid_pid_graph_and_router_provider_use(tmp_path):
    image = tmp_path / "pid.png"
    image.write_bytes(b"image")
    impl, provider = pipeline(json.dumps(graph_payload()))
    graph = impl.extract_pid_graph(str(image))
    assert provider.calls == 1
    assert graph.nodes[0]["node_id"] == "n-1"
    assert graph.edges[0]["source_node_id"] == "n-1"
    assert graph.confidence_summary["overall"] == 0.75


def test_node_edge_validation_stable_ids_and_confidence():
    valid = StructuredPIDGraph.model_validate(graph_payload())
    assert valid.nodes[0].confidence == 0.8
    assert valid.nodes[0].image_id == "image-1"
    duplicate = graph_payload()
    duplicate["nodes"].append(dict(duplicate["nodes"][0]))
    with pytest.raises(ValidationError, match="unique"):
        StructuredPIDGraph.model_validate(duplicate)
    invalid_confidence = graph_payload()
    invalid_confidence["nodes"][0]["confidence"] = 2
    with pytest.raises(ValidationError, match="between"):
        StructuredPIDGraph.model_validate(invalid_confidence)


def test_empty_graph_and_overlay_path_are_valid():
    graph = StructuredPIDGraph.model_validate({"nodes": [], "edges": [], "overlay_image_path": "overlay.png", "confidence_summary": {}})
    assert graph.nodes == [] and graph.overlay_image_path == "overlay.png"


@pytest.mark.parametrize(
    "payload",
    ["not json", json.dumps({"nodes": []}), json.dumps({**graph_payload(), "edges": [{"edge_id": "e", "source_node_id": "missing", "target_node_id": "n-1", "relationship": "x"}]})],
)
def test_malformed_or_partial_model_graph_is_rejected(tmp_path, payload):
    image = tmp_path / "pid.png"
    image.write_bytes(b"image")
    impl, _ = pipeline(payload)
    with pytest.raises(PIDModelOutputError):
        impl.extract_pid_graph(str(image))


def test_model_unavailable_and_no_mode_fallback(tmp_path):
    image = tmp_path / "pid.png"
    image.write_bytes(b"image")
    impl, _ = pipeline(json.dumps(graph_payload()), mode="groq")
    with pytest.raises(ModelUnavailableError):
        impl.extract_pid_graph(str(image))


def test_missing_image_path_is_rejected_before_model_use(tmp_path):
    impl, provider = pipeline(json.dumps(graph_payload()))
    with pytest.raises(PIDModelOutputError):
        impl.extract_pid_graph(str(tmp_path / "missing.png"))
    assert provider.calls == 0
