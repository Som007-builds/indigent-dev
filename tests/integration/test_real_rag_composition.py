from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.state import TaskSnapshot
from app.config import Settings
from app.deps import ProductionTaskRetriever, build_production_rag
from app.rag.models import Chunk, EvidenceItem, RetrievalResult


def test_real_rag_configuration_is_required_before_construction():
    with pytest.raises(RuntimeError, match="EMBEDDING_BACKEND and EMBEDDING_MODEL"):
        build_production_rag(Settings())


@pytest.mark.asyncio
async def test_task_retriever_ingests_once_and_returns_provenance(tmp_path):
    from app.core.workspace import create_workspace

    workspace = create_workspace(tmp_path, "task-1")
    source = workspace / "inputs" / "file-1.txt"
    source.write_text("Inspection: pump pressure is stable.", encoding="utf-8")
    ingested = []

    class DocumentIngestor:
        def ingest(self, path: Path, document_id: str, mime: str):
            ingested.append((path, document_id, mime))
            from app.rag.chunking import source_sha256

            return [Chunk("file-1:0", "file-1", source_sha256(path), "pump pressure is stable", page=1)]

    class Retriever:
        def __init__(self):
            self.queries = []
            self.scopes = []
            self.path = source

        def retrieve(self, query: str, *, limit: int, document_ids=None, require_scope: bool = True):
            if require_scope and document_ids is None:
                raise ValueError("retrieval requires an explicit document scope")
            self.queries.append((query, limit))
            self.scopes.append(list(document_ids or []))
            from app.rag.chunking import source_sha256

            return RetrievalResult(query, [EvidenceItem(
                "file-1", "file-1:0", source_sha256(self.path), "pump pressure is stable", page=1,
                source_reference="file-1.txt", retrieval_score=0.91, reranking_score=1.0,
            )])

    retriever = Retriever()
    adapter = ProductionTaskRetriever(DocumentIngestor(), retriever)
    task = TaskSnapshot("task-1", "find pump pressure", "inspection", "local", workspace)
    first = await adapter(task, ["file-1"], {"query": "pump pressure"})
    second = await adapter(task, ["file-1"], {"query": "pump pressure"})

    assert len(ingested) == 1
    assert ingested[0][1:] == ("file-1", "text/plain")
    assert retriever.queries == [("pump pressure", 5), ("pump pressure", 5)]
    # Task scope is forwarded on every query, so retrieval can never leave the task.
    assert retriever.scopes == [["file-1"], ["file-1"]]
    assert first == second
    assert first[0]["document_id"] == "file-1"
    assert first[0]["chunk_id"] == "file-1:0"
    assert len(first[0]["source_hash"]) == 64
    assert first[0]["retrieval_score"] == 0.91
    assert first[0]["reranking_score"] == 1.0


@pytest.mark.asyncio
async def test_task_retriever_rejects_unknown_or_unsupported_task_input(tmp_path):
    from app.core.workspace import create_workspace

    workspace = create_workspace(tmp_path, "task-2")
    (workspace / "inputs" / "bad.docx").write_bytes(b"PK\x03\x04unsupported")

    class ForbiddenIngestor:
        def ingest(self, *args):
            raise AssertionError("unsupported input must fail before extraction")

    class EmptyRetriever:
        def retrieve(self, *args, **kwargs):
            return RetrievalResult("query", [])

    adapter = ProductionTaskRetriever(ForbiddenIngestor(), EmptyRetriever())
    task = TaskSnapshot("task-2", "question", "inspection", "local", workspace)
    with pytest.raises(ValueError, match="unsupported"):
        await adapter(task, ["bad"], {"query": "query"})
