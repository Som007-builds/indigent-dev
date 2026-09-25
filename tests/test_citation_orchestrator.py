from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.agent.orchestrator import BoundedOrchestrator, OrchestratorDependencies
from app.agent.registry import ModelRegistry
from app.agent.resource_manager import ResourceManager
from app.agent.router import ModelRouter
from app.config import Settings
from app.contracts.models import PolicyDecision, TaskContext
from app.providers.types import InferenceResult, ModelInfo, ProviderHealth, ToolSchema
from app.rag.models import ClaimProvenance, EvidenceItem


class Provider:
    def is_local(self): return True
    def health_check(self): return ProviderHealth("ollama", True)
    def generate(self, model_id, messages, tools=None): return InferenceResult("", model_id, "ollama")


class Planner:
    async def classify(self, request, model_id, provider): return "inspection"
    async def plan(self, request, task_type, tools, model_id, provider): return ["read_file"]


class Policy:
    async def validate(self, ctx, request):
        return PolicyDecision(allowed=True, tool=request.tool, decision_id="d")


class Tools:
    async def execute(self, decision): return {"ok": True}


class BaseVerifier:
    async def verify(self, task): return True, "base"


class CitationVerifier:
    def __init__(self, results): self.results = iter(results)
    async def verify_citations(self, task, claims, evidence): return next(self.results)


class Artifacts:
    async def create(self, task): return []
    async def validate(self, task): return True, []


def make(citation_verifier):
    model = ModelInfo("m", "m", "ollama", "local", frozenset({"inspection"}), frozenset({"mac_silicon"}))
    router = ModelRouter(Settings(), ModelRegistry([model]), {"ollama": Provider()}, ResourceManager())
    deps = OrchestratorDependencies(
        Planner(), Tools(), BaseVerifier(), Artifacts(), Policy(), tools=(ToolSchema("read_file"),),
        approval=lambda task: asyncio.sleep(0, result=True), citation_verifier=citation_verifier,
        claims=(ClaimProvenance("c", "claim", ("chunk",)),),
        evidence=(EvidenceItem("d", "chunk", "h", "evidence"),),
    )
    return BoundedOrchestrator(router, deps)


@pytest.mark.asyncio
async def test_citation_failure_enters_repair():
    result = [event async for event in make(CitationVerifier([(False, "unsupported"), (True, "fixed")])).run(
        TaskContext(task_id="t", task_type=None, workspace=Path("."), inference_mode="local"), "request", []
    )]
    assert any(event.type == "repair" for event in result)
    assert result[-1].type == "completed"


@pytest.mark.asyncio
async def test_three_citation_failures_terminate():
    result = [event async for event in make(CitationVerifier([(False, "bad")] * 3)).run(
        TaskContext(task_id="t", task_type=None, workspace=Path("."), inference_mode="local"), "request", []
    )]
    assert result[-1].data["error"]["code"] == "VERIFICATION_FAILED"
