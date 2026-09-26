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

EVIDENCE = EvidenceItem("d", "chunk", "h", "evidence")


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
    """Records every (claim, evidence) pair it is asked to judge.

    A repair is only real if the claims handed to this verifier change, so the
    verifier records its inputs instead of replaying a scripted verdict sequence.
    """

    def __init__(self, *, unsupported: set[str] | None = None, fail_all: bool = False) -> None:
        self.unsupported = unsupported or set()
        self.fail_all = fail_all
        self.calls: list[tuple[str, ...]] = []

    async def verify_citations(self, task, claims, evidence):
        claim_ids = tuple(claim.claim_id for claim in claims)
        self.calls.append(claim_ids)
        unsupported = self.fail_all or any(
            claim.claim_id in self.unsupported for claim in claims
        )
        return (not unsupported), ("unsupported" if unsupported else "supported")


class Artifacts:
    async def create(self, task): return []
    async def validate(self, task): return True, []


def make(citation_verifier, *, citation_repair=None, claims=None):
    model = ModelInfo("m", "m", "ollama", "local", frozenset({"inspection"}), frozenset({"mac_silicon"}))
    router = ModelRouter(Settings(), ModelRegistry([model]), {"ollama": Provider()}, ResourceManager())
    deps = OrchestratorDependencies(
        Planner(), Tools(), BaseVerifier(), Artifacts(), Policy(), tools=(ToolSchema("read_file"),),
        approval=lambda task: asyncio.sleep(0, result=True), citation_verifier=citation_verifier,
        claims=claims if claims is not None else (ClaimProvenance("c", "claim", ("chunk",)),),
        evidence=(EVIDENCE,),
        citation_repair=citation_repair,
    )
    return BoundedOrchestrator(router, deps)


def context():
    return TaskContext(task_id="t", task_type=None, workspace=Path("."), inference_mode="local")


async def run(orchestrator):
    return [event async for event in orchestrator.run(context(), "request", [])]


@pytest.mark.asyncio
async def test_citation_failure_without_repair_fails_clearly_and_does_not_reverify():
    """No repair callback means the claims cannot change, so the task must not pretend.

    The verifier must be consulted exactly once: re-running it on identical claims can
    only repeat the identical verdict while burning real generation time.
    """
    verifier = CitationVerifier(unsupported={"c"})
    result = await run(make(verifier))

    assert len(verifier.calls) == 1, f"identical re-verification happened: {verifier.calls}"
    assert not any(event.type == "repair" for event in result)
    assert result[-1].type == "failed"
    assert result[-1].data["error"]["code"] == "CITATION_UNREPAIRABLE"
    assert any(event.type == "verification" and event.data["status"] == "failed" for event in result)


@pytest.mark.asyncio
async def test_repair_callback_changes_the_claims_that_are_reverified():
    """A repair must materially change the input to verification."""
    verifier = CitationVerifier(unsupported={"c"})
    repaired_claims = (ClaimProvenance("c-fixed", "corrected claim", ("chunk",)),)

    calls: list[int] = []

    async def repair(task, failures):
        calls.append(len(failures))
        return repaired_claims

    result = await run(make(verifier, citation_repair=repair))

    assert calls, "the repair callback must actually be used"
    assert verifier.calls == [("c",), ("c-fixed",)], (
        f"verification must see changed claims, saw {verifier.calls}"
    )
    repair_events = [event for event in result if event.type == "repair"]
    assert repair_events, "a real repair must emit a repair event"
    assert repair_events[0].data["attempt"] == 1
    assert repair_events[0].data["checks"], "the repair event must carry the failure detail"
    assert result[-1].type == "completed"


@pytest.mark.asyncio
async def test_repair_is_bounded_and_terminates_as_unrecoverable():
    """MAX_REPAIR_ATTEMPTS stays bounded, then the task fails closed."""
    verifier = CitationVerifier(fail_all=True)
    attempts = 0

    async def repair(task, failures):
        # Return a different claim id each time so every attempt is a real repair.
        nonlocal attempts
        attempts += 1
        return (ClaimProvenance(f"c-fix-{attempts}", "still unsupported", ("chunk",)),)

    result = await run(make(verifier, citation_repair=repair))

    repair_events = [event for event in result if event.type == "repair"]
    assert len(repair_events) == 2, f"repair must be bounded, got {len(repair_events)}"
    assert verifier.calls == [("c",), ("c-fix-1",), ("c-fix-2",)], verifier.calls
    assert result[-1].type == "failed"
    assert result[-1].data["error"]["code"] == "VERIFICATION_FAILED"


@pytest.mark.asyncio
async def test_repair_returning_no_claims_fails_closed():
    """A repair that produces nothing must not silently pass the task."""
    verifier = CitationVerifier(unsupported={"c"})

    async def repair(task, failures):
        return ()

    result = await run(make(verifier, citation_repair=repair))
    assert result[-1].type == "failed"
    assert result[-1].data["error"]["code"] == "CITATION_REPAIR_FAILED"
    assert len(verifier.calls) == 1, verifier.calls


@pytest.mark.asyncio
async def test_supported_claims_complete_without_any_repair():
    verifier = CitationVerifier()
    result = await run(make(verifier))
    assert not any(event.type == "repair" for event in result)
    assert result[-1].type == "completed"
    assert verifier.calls == [("c",)]
