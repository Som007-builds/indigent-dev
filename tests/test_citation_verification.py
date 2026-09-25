from __future__ import annotations

import json

import pytest

from app.agent.registry import ModelRegistry
from app.agent.resource_manager import ResourceManager
from app.agent.router import ModelRouter
from app.config import Settings
from app.providers.types import InferenceResult, ModelInfo, ProviderHealth
from app.rag.models import ClaimProvenance, EvidenceItem
from app.rag.verification import CitationVerifier, MalformedVerificationError


class Provider:
    def __init__(self, output):
        self.output = output
        self.calls = 0

    def is_local(self):
        return True

    def health_check(self):
        return ProviderHealth("ollama", True)

    def generate(self, model_id, messages, tools=None):
        self.calls += 1
        return InferenceResult(self.output, model_id, "ollama")


def verifier(output, threshold=0.75):
    provider = Provider(output)
    model = ModelInfo("verify", "verify", "ollama", "local", frozenset({"inspection"}), frozenset({"mac_silicon"}))
    router = ModelRouter(Settings(), ModelRegistry([model]), {"ollama": provider}, ResourceManager())
    return CitationVerifier(router, threshold=threshold), provider


def claim():
    return ClaimProvenance("claim-1", "The pump pressure is 10 bar", ("chunk-1",))


def evidence():
    return EvidenceItem("doc-1", "chunk-1", "hash-1", "The pump pressure is 10 bar", page=2, section="Operations")


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ({"verified": True, "confidence": 0.9, "reason": "supported"}, True),
        ({"verified": False, "confidence": 0.9, "reason": "contradicted"}, False),
        ({"verified": False, "confidence": 0.9, "reason": "irrelevant"}, False),
        ({"verified": True, "confidence": 0.7, "reason": "supported"}, False),
        ({"verified": True, "confidence": 0.75, "reason": "supported"}, True),
    ],
)
def test_verification_threshold_and_outcomes(output, expected):
    verifier_impl, _ = verifier(json.dumps(output))
    result = verifier_impl.verify(claim(), evidence())
    assert result.verified is expected


@pytest.mark.parametrize(
    "output",
    [
        "not json",
        json.dumps({"verified": True, "reason": "supported"}),
        json.dumps({"verified": True, "confidence": 2, "reason": "supported"}),
        json.dumps({"verified": "yes", "confidence": 0.9, "reason": "supported"}),
        json.dumps({"verified": False, "confidence": 0.9, "reason": "supported"}),
    ],
)
def test_malformed_verifier_output_fails_closed(output):
    verifier_impl, _ = verifier(output)
    with pytest.raises(MalformedVerificationError):
        verifier_impl.verify(claim(), evidence())


def test_provenance_and_router_are_preserved():
    verifier_impl, provider = verifier(json.dumps({"verified": True, "confidence": 0.9, "reason": "supported"}))
    result = verifier_impl.verify(claim(), evidence())
    assert provider.calls == 1
    assert result.evidence.document_id == "doc-1"
    assert result.evidence.chunk_id == "chunk-1"
    assert result.evidence.source_hash == "hash-1"
    assert result.verification.claim_id == "claim-1"
    assert result.verification.confidence == 0.9


def test_invalid_threshold_is_rejected():
    with pytest.raises(ValueError):
        verifier("{}", threshold=1.1)
