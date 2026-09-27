from __future__ import annotations

import asyncio
import json

import pytest
from pydantic import ValidationError

from app.agent.inference import RoutedInferenceExecutor
from app.agent.registry import ModelRegistry
from app.agent.resource_manager import ResourceManager
from app.agent.router import ModelRouter
from app.config import Settings
from app.errors import ModelUnavailableError
from app.pid_ml import MultimodalPIDPipeline, StructuredPIDGraph
from app.pid_ml.pipeline import PIDModelOutputError
from app.providers.types import ImageInput, InferenceResult, ModelInfo, ProviderHealth


class Provider:
    def __init__(self, response: str):
        self.response = response
        self.calls = 0
        self.received_images = []

    def is_local(self): return True
    def supports_images(self): return True
    def health_check(self): return ProviderHealth("ollama", True)
    def generate(self, model_id, messages, tools=None):
        self.calls += 1
        return InferenceResult(self.response, model_id, "ollama")
    def generate_with_images(self, model_id, messages, images, tools=None):
        self.calls += 1
        self.received_images = images
        assert "attached P&ID image" in messages[-1].content
        return InferenceResult(self.response, model_id, "ollama")


def graph_payload():
    return {
        "nodes": [{"node_id": "n-1", "category": "pump", "label": "P-101", "bbox": [1, 2, 3, 4], "confidence": 0.8, "image_id": "image-1"}],
        "edges": [{"edge_id": "e-1", "source_node_id": "n-1", "target_node_id": "n-1", "relationship": "connects", "confidence": 0.7, "image_id": "image-1"}],
        "overlay_image_path": "overlay.png",
        "narrative": "Pump P-101 is connected to itself in this synthetic fixture.",
        "confidence_summary": {"overall": 0.75},
    }


class Sovereignty:
    def __init__(self):
        self.external_calls = []

    async def record_external_call(self, provider, bytes_out, bytes_in):
        self.external_calls.append((provider, bytes_out, bytes_in))

    async def snapshot(self):
        return {}


def pipeline(response, *, mode: str = "local"):
    provider = Provider(response)
    model = ModelInfo(
        "vlm", "vlm", "ollama", "local", 
        frozenset({"pid_analysis"}), 
        frozenset({"mac_silicon"}),
        modalities=frozenset({"text", "image"})
    )
    resources = ResourceManager()
    router = ModelRouter(Settings(inference_mode=mode), ModelRegistry([model]), {"ollama": provider}, resources)  # type: ignore[arg-type]
    sovereignty = Sovereignty()
    executor = RoutedInferenceExecutor(resources, sovereignty, mode)
    return MultimodalPIDPipeline(router, executor), provider, resources, sovereignty


@pytest.mark.asyncio
async def test_valid_pid_graph_uses_real_image_through_routed_executor(tmp_path):
    image = tmp_path / "pid.png"
    image.write_bytes(b"image-bytes")
    impl, provider, resources, sovereignty = pipeline(json.dumps(graph_payload()))
    graph = await impl.extract_pid_graph(str(image))
    assert provider.calls == 1
    assert provider.received_images == [ImageInput("image/png", b"image-bytes")]
    assert resources.residency("vlm").active_requests == 0
    assert sovereignty.external_calls == []
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
@pytest.mark.asyncio
async def test_malformed_or_partial_model_graph_is_rejected(tmp_path, payload):
    image = tmp_path / "pid.png"
    image.write_bytes(b"image")
    impl, _, resources, _ = pipeline(payload)
    with pytest.raises(PIDModelOutputError):
        await impl.extract_pid_graph(str(image))
    assert resources.residency("vlm").active_requests == 0


@pytest.mark.asyncio
async def test_model_unavailable_and_no_mode_fallback(tmp_path):
    image = tmp_path / "pid.png"
    image.write_bytes(b"image")
    impl, _, _, _ = pipeline(json.dumps(graph_payload()), mode="groq")
    with pytest.raises(ModelUnavailableError):
        await impl.extract_pid_graph(str(image))


@pytest.mark.asyncio
async def test_missing_image_path_is_rejected_before_model_use(tmp_path):
    impl, provider, _, _ = pipeline(json.dumps(graph_payload()))
    with pytest.raises(PIDModelOutputError):
        await impl.extract_pid_graph(str(tmp_path / "missing.png"))
    assert provider.calls == 0


class TextOnlyProvider(Provider):
    def supports_images(self): return False


def _router(provider, *, mode: str = "local"):
    model = ModelInfo("vlm", "vlm", "ollama", "local", frozenset({"pid_analysis"}), frozenset({"mac_silicon"}))
    resources = ResourceManager()
    return ModelRouter(Settings(inference_mode=mode), ModelRegistry([model]), {"ollama": provider}, resources)  # type: ignore[arg-type]


def test_pid_analysis_is_never_routed_to_a_provider_without_image_support(tmp_path):
    """Item 7: image-only work must not land on an adapter that would drop the image."""
    image = tmp_path / "pid.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    router = _router(TextOnlyProvider(json.dumps(graph_payload())))
    with pytest.raises(ModelUnavailableError):
        router.resolve("pid_analysis", requires_images=True)

    executor = RoutedInferenceExecutor(ResourceManager(), Sovereignty(), "local")
    pipeline = MultimodalPIDPipeline(router, executor)
    with pytest.raises(ModelUnavailableError):
        asyncio.run(pipeline.extract_pid_graph(str(image)))


def test_text_only_routing_is_unaffected_for_non_image_tasks(tmp_path):
    image = tmp_path / "pid.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    router = _router(TextOnlyProvider(json.dumps(graph_payload())))
    model, provider = router.resolve("pid_analysis")
    assert provider.supports_images() is False
    assert model.model_id == "vlm"
