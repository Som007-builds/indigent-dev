"""Focused coverage for the five production ML tools.

Each tool must return a real result or fail closed with an explicit reason. None of them
may fabricate success, and all of them must respect the task workspace boundary and the
document scope, because these are the tools the policy allow-list exposes to the model.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from app.deps import MLToolUnavailable, _ProductionRetrievalTools
from app.rag.models import Chunk, Document


class Ctx:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.task_id = "task-1"


class Store:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []
        self.calls: list[tuple[Any, ...]] = []

    def search(self, vector, limit, *, document_ids=None):
        self.calls.append((limit, tuple(document_ids) if document_ids else None))
        return self.rows[:limit]


class Embedder:
    def embed(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


def chunk(chunk_id: str, document_id: str, section: str, text: str) -> dict[str, Any]:
    return {
        "chunk": Chunk(
            chunk_id=chunk_id,
            document_id=document_id,
            text=text,
            source_hash=f"hash-{chunk_id}",
            section=section,
            page=1,
        )
    }


def tools(tmp_path: Path, *, rows=None, extractor=None, pid=None, router=None, inference=None):
    from app.rag.retrieval import LexicalReranker, Retriever

    store = Store(rows)
    retriever = Retriever(Embedder(), store, LexicalReranker())

    async def retrieve(task, file_ids, args):
        result = retriever.retrieve(args.get("query", ""), document_ids=file_ids or None)
        return [item.__dict__ for item in result.items]

    return (
        _ProductionRetrievalTools(
            retrieve,
            retriever=retriever,
            extractor=extractor,
            router=router,
            inference=inference,
            pid=pid,
        ),
        store,
    )


# --- retrieve_section -------------------------------------------------------------------


def test_retrieve_section_returns_scoped_section_with_provenance(tmp_path):
    rows = [
        chunk("c1", "doc-a", "Bearing lubrication", "reservoir holds 40 litres"),
        chunk("c2", "doc-b", "Vibration", "4.5 mm/s RMS"),
    ]
    ml, store = tools(tmp_path, rows=rows)
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "doc-a.txt").write_text("pump", encoding="utf-8")

    result = asyncio.run(
        ml.call(
            "retrieve_section",
            Ctx(tmp_path),
            {"document_id": "doc-a", "section": "Bearing lubrication"},
        )
    )
    assert result["document_id"] == "doc-a"
    assert result["section_found"] is True
    assert [c["chunk_id"] for c in result["chunks"]] == ["c1"]
    assert result["chunks"][0]["source_hash"] == "hash-c1"
    assert result["chunks"][0]["document_id"] == "doc-a"
    # The query must be scoped to the single requested document.
    assert store.calls[-1][1] == ("doc-a",)


def test_retrieve_section_refuses_a_document_outside_the_task(tmp_path):
    ml, _ = tools(tmp_path, rows=[])
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "doc-a.txt").write_text("pump", encoding="utf-8")

    with pytest.raises(MLToolUnavailable) as caught:
        asyncio.run(
            ml.call(
                "retrieve_section",
                Ctx(tmp_path),
                {"document_id": "other-task-doc", "section": "Anything"},
            )
        )
    assert caught.value.code == "SCOPE_VIOLATION"


def test_retrieve_section_requires_both_arguments(tmp_path):
    ml, _ = tools(tmp_path)
    with pytest.raises(MLToolUnavailable) as caught:
        asyncio.run(ml.call("retrieve_section", Ctx(tmp_path), {"section": "S"}))
    assert caught.value.code == "TOOL_ARGUMENT_MISSING"


def test_retrieve_section_does_not_invent_a_missing_section(tmp_path):
    rows = [chunk("c1", "doc-a", "Some Other Section", "text")]
    ml, _ = tools(tmp_path, rows=rows)
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "doc-a.txt").write_text("pump", encoding="utf-8")

    result = asyncio.run(
        ml.call("retrieve_section", Ctx(tmp_path), {"document_id": "doc-a", "section": "Absent"})
    )
    assert result["section_found"] is False
    assert all(c["section"] != "Absent" for c in result["chunks"])


# --- ocr_document -----------------------------------------------------------------------


class TextExtractor:
    def __init__(self, document: Document | Exception) -> None:
        self.document = document

    def extract(self, path: Path, mime: str) -> Document:
        if isinstance(self.document, Exception):
            raise self.document
        return self.document


def test_ocr_document_extracts_real_text(tmp_path):
    document = Document(document_id="d", source_path="manual.txt", source_hash="hash-manual", text="Bearing reservoir 40 litres")
    ml, _ = tools(tmp_path, extractor=TextExtractor(document))
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "manual.txt").write_text("Bearing reservoir 40 litres", encoding="utf-8")

    result = asyncio.run(ml.call("ocr_document", Ctx(tmp_path), {"path": "inputs/manual.txt"}))
    assert result["text"] == "Bearing reservoir 40 litres"
    assert result["characters"] == len("Bearing reservoir 40 litres")
    # Provenance comes from the extractor, not from re-deriving it here.
    assert result["source_hash"] == "hash-manual"
    assert result["document_id"] == "d"


def test_ocr_document_fails_closed_for_a_scanned_document(tmp_path):
    """No OCR engine is provisioned, so an image-only PDF must not be invented."""
    ml, _ = tools(tmp_path, extractor=TextExtractor(RuntimeError("no extractable text; local OCR is unavailable")))
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "scan.pdf").write_bytes(b"%PDF-1.4 scanned")

    with pytest.raises(MLToolUnavailable) as caught:
        asyncio.run(ml.call("ocr_document", Ctx(tmp_path), {"path": "inputs/scan.pdf"}))
    assert caught.value.code == "OCR_UNAVAILABLE"


def test_ocr_document_fails_closed_on_an_empty_text_layer(tmp_path):
    ml, _ = tools(tmp_path, extractor=TextExtractor(Document(document_id="d", source_path="blank.txt", source_hash="hash-blank", text="   ")))
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "blank.txt").write_text("   ", encoding="utf-8")

    with pytest.raises(MLToolUnavailable) as caught:
        asyncio.run(ml.call("ocr_document", Ctx(tmp_path), {"path": "inputs/blank.txt"}))
    assert caught.value.code == "OCR_UNAVAILABLE"


def test_ocr_document_rejects_a_path_outside_the_workspace(tmp_path):
    from app.errors import PathRejectedError

    ml, _ = tools(tmp_path, extractor=TextExtractor(Document(document_id="d", source_path="s.txt", source_hash="h", text="x")))
    (tmp_path / "inputs").mkdir()
    (tmp_path / "secret.txt").write_text("classified", encoding="utf-8")

    with pytest.raises(PathRejectedError):
        asyncio.run(ml.call("ocr_document", Ctx(tmp_path), {"path": "../secret.txt"}))


def test_ocr_document_rejects_a_missing_file(tmp_path):
    ml, _ = tools(tmp_path, extractor=TextExtractor(Document(document_id="d", source_path="s.txt", source_hash="h", text="x")))
    (tmp_path / "inputs").mkdir()
    with pytest.raises(MLToolUnavailable) as caught:
        asyncio.run(ml.call("ocr_document", Ctx(tmp_path), {"path": "nope.txt"}))
    assert caught.value.code == "FILE_NOT_FOUND"


# --- extract_pid_graph ------------------------------------------------------------------


class FakePID:
    def __init__(self, graph=None, error=None):
        self.graph = graph
        self.error = error
        self.paths: list[str] = []

    async def extract_pid_graph(self, image_path: str, *, task_id=None):
        self.paths.append(image_path)
        if self.error:
            raise self.error
        return self.graph


def test_extract_pid_graph_uses_the_real_pipeline(tmp_path):
    class Graph:
        nodes = [{"id": "pump-1"}]
        edges = [{"from": "pump-1", "to": "valve-1"}]
        narrative = "Pump feeds valve."
        confidence_summary = {"overall": 0.8}
        overlay_image_path = "/tmp/overlay.png"

    pid = FakePID(graph=Graph())
    ml, _ = tools(tmp_path, pid=pid)
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "pid.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    result = asyncio.run(ml.call("extract_pid_graph", Ctx(tmp_path), {"path": "inputs/pid.png"}))
    assert result["nodes"] == [{"id": "pump-1"}]
    assert result["edges"] == [{"from": "pump-1", "to": "valve-1"}]
    assert result["narrative"] == "Pump feeds valve."
    assert result["confidence_summary"] == {"overall": 0.8}
    assert pid.paths == [str(tmp_path / "inputs" / "pid.png")]


def test_extract_pid_graph_propagates_a_pipeline_failure(tmp_path):
    pid = FakePID(error=RuntimeError("P&ID model output was not valid JSON"))
    ml, _ = tools(tmp_path, pid=pid)
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "pid.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    with pytest.raises(RuntimeError, match="not valid JSON"):
        asyncio.run(ml.call("extract_pid_graph", Ctx(tmp_path), {"path": "inputs/pid.png"}))


def test_extract_pid_graph_requires_a_configured_pipeline(tmp_path):
    ml, _ = tools(tmp_path, pid=None)
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "pid.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(MLToolUnavailable) as caught:
        asyncio.run(ml.call("extract_pid_graph", Ctx(tmp_path), {"path": "inputs/pid.png"}))
    assert caught.value.code == "PID_UNAVAILABLE"


# --- analyze_image ----------------------------------------------------------------------


def test_analyze_image_fails_closed_without_vision_support(tmp_path):
    """The configured local model is text-only, so image analysis must not be faked."""

    class Router:
        def resolve(self, task_type, requested_model_id=None, *, requires_images=False):
            from app.errors import ModelUnavailableError

            assert requires_images, "image analysis must demand an image-capable model"
            raise ModelUnavailableError("no local model accepts images")

    ml, _ = tools(tmp_path, router=Router(), inference=object())
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    from app.errors import ModelUnavailableError

    with pytest.raises(ModelUnavailableError):
        asyncio.run(ml.call("analyze_image", Ctx(tmp_path), {"path": "inputs/photo.png"}))


def test_analyze_image_uses_the_real_executor_contract(tmp_path):
    """The tool must call RoutedInferenceExecutor with (model, provider, messages, images)."""
    seen: dict = {}

    class Model:
        model_id = "vision-model"
        mode = "local"

    class Provider:
        name = "ollama"

    class Router:
        def resolve(self, task_type, requested_model_id=None, *, requires_images=False):
            seen["requires_images"] = requires_images
            seen["task_type"] = task_type
            return Model(), Provider()

    class Inference:
        async def generate_with_images(self, model, provider, messages, images, tools=None, *, task_id=None):
            seen.update(model=model, provider=provider, messages=messages, images=images, task_id=task_id)
            return type("Execution", (), {"result": type("R", (), {"text": "A pump with a check valve."})()})()

    ml, _ = tools(tmp_path, router=Router(), inference=Inference())
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    result = asyncio.run(
        ml.call("analyze_image", Ctx(tmp_path), {"path": "inputs/photo.png", "question": "What is this?"})
    )
    assert result["analysis"] == "A pump with a check valve."
    assert result["model_id"] == "vision-model"
    assert result["media_type"] == "image/png"
    # The model and provider are passed as objects, not as a model id string.
    assert isinstance(seen["model"], Model)
    assert isinstance(seen["provider"], Provider)
    assert seen["requires_images"] is True
    assert seen["task_type"] == "pid_analysis"
    assert seen["task_id"] == "task-1"
    assert seen["messages"][0].content == "What is this?"
    assert seen["images"][0].media_type == "image/png"
    assert seen["images"][0].data == b"\x89PNG\r\n\x1a\n"


def test_analyze_image_refuses_a_non_local_provider(tmp_path):
    """Local-only is a sovereignty rule, not a preference."""

    class Model:
        model_id = "remote-vision"
        mode = "groq"

    class Router:
        def resolve(self, task_type, requested_model_id=None, *, requires_images=False):
            return Model(), object()

    ml, _ = tools(tmp_path, router=Router(), inference=object())
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    with pytest.raises(MLToolUnavailable) as caught:
        asyncio.run(ml.call("analyze_image", Ctx(tmp_path), {"path": "inputs/photo.png"}))
    assert caught.value.code == "IMAGE_ANALYSIS_UNAVAILABLE"
    assert "local" in str(caught.value)


def test_analyze_image_fails_closed_on_an_empty_model_reply(tmp_path):
    class Router:
        def resolve(self, task_type, requested_model_id=None, *, requires_images=False):
            return type("M", (), {"model_id": "vision-model", "mode": "local"})(), object()

    class Inference:
        async def generate_with_images(self, model, provider, messages, images, tools=None, *, task_id=None):
            return type("Execution", (), {"result": type("R", (), {"text": "   "})()})()

    ml, _ = tools(tmp_path, router=Router(), inference=Inference())
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    with pytest.raises(MLToolUnavailable) as caught:
        asyncio.run(ml.call("analyze_image", Ctx(tmp_path), {"path": "inputs/photo.png"}))
    assert caught.value.code == "EMPTY_ANALYSIS"
    assert "vision model" in str(caught.value)


# --- unknown tools ----------------------------------------------------------------------


def test_unknown_tool_is_rejected(tmp_path):
    ml, _ = tools(tmp_path)
    with pytest.raises(ValueError, match="unsupported production ML tool"):
        asyncio.run(ml.call("exfiltrate", Ctx(tmp_path), {}))


def test_ocr_unavailable_error_names_the_remedy(tmp_path):
    """An operator must be able to resolve the gap from the error alone."""
    ml, _ = tools(tmp_path, extractor=TextExtractor(RuntimeError("no extractable text")))
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "scan.pdf").write_bytes(b"%PDF-1.4 scanned")

    with pytest.raises(MLToolUnavailable) as caught:
        asyncio.run(ml.call("ocr_document", Ctx(tmp_path), {"path": "inputs/scan.pdf"}))
    message = str(caught.value)
    assert caught.value.code == "OCR_UNAVAILABLE"
    assert "tesseract" in message, message
    assert "install" in message.lower(), message
    # The underlying cause is preserved for diagnosis.
    assert "no extractable text" in message, message


def test_extract_pid_graph_reports_a_missing_vision_model_clearly(tmp_path):
    """The real pipeline must reject a text-only model instead of inventing a graph."""
    from app.errors import ModelUnavailableError
    from app.pid_ml.pipeline import MultimodalPIDPipeline

    class Router:
        def resolve(self, task_type, requested_model_id=None, *, requires_images=False):
            assert requires_images
            raise ModelUnavailableError("no local model accepts images")

    pipeline = MultimodalPIDPipeline(Router(), object())
    ml, _ = tools(tmp_path, pid=pipeline)
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "pid.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    with pytest.raises(ModelUnavailableError, match="images"):
        asyncio.run(ml.call("extract_pid_graph", Ctx(tmp_path), {"path": "inputs/pid.png"}))
