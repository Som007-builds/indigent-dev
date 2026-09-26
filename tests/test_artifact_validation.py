from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Literal, cast

import pytest

from app.artifact_validation import ArtifactValidationContext, SemanticArtifactValidator
from app.contracts.models import ArtifactManifest
from app.rag.models import ClaimProvenance, EvidenceItem, VerificationProvenance

ArtifactKind = Literal["docx", "xlsx", "graph_json", "code_package", "pid_overlay"]


def manifest(
    path: Path,
    kind: ArtifactKind = "docx",
    metadata: dict | None = None,
    digest: str = "placeholder",
) -> ArtifactManifest:
    return ArtifactManifest(
        artifact_id="artifact-1",
        task_id="task-1",
        artifact_type=kind,
        path=str(path),
        created_at="2026-09-25T10:00:00Z",
        artifact_hash=digest,
        metadata=metadata or {},
    )


def make_docx(path: Path) -> None:
    pytest.importorskip("docx")
    from app.runtime.generators.docx import generate

    generate(path, {"title": "Report", "recommendation": "Proceed", "sections": []})


def test_valid_docx_and_hash_stability(tmp_path):
    path = tmp_path / "report.docx"
    make_docx(path)
    validator = SemanticArtifactValidator()
    item = manifest(path)
    first = asyncio.run(validator.validate(item))
    second = asyncio.run(validator.validate(item))
    assert first.status in {"VALID", "UNVERIFIED"}
    assert first.artifact_hash == second.artifact_hash == hashlib.sha256(path.read_bytes()).hexdigest()


def test_missing_malformed_wrong_type_and_metadata(tmp_path):
    validator = SemanticArtifactValidator()
    missing = asyncio.run(validator.validate(manifest(tmp_path / "missing.docx")))
    assert missing.status == "INVALID"
    path = tmp_path / "bad.docx"
    path.write_text("not docx")
    malformed = asyncio.run(validator.validate(manifest(path)))
    wrong = asyncio.run(validator.validate(manifest(path, "xlsx")))
    metadata = asyncio.run(validator.validate(manifest(path, metadata=None)))
    assert malformed.status in {"INVALID", "UNVERIFIED"}
    assert wrong.status in {"INVALID", "UNVERIFIED"}
    assert metadata.status in {"INVALID", "UNVERIFIED"}


def test_graph_json_validation(tmp_path):
    path = tmp_path / "graph.json"
    path.write_text(json.dumps({"nodes": [], "edges": []}))
    valid = asyncio.run(SemanticArtifactValidator().validate(manifest(path, "graph_json")))
    path.write_text("{")
    invalid = asyncio.run(SemanticArtifactValidator().validate(manifest(path, "graph_json")))
    assert valid.status == "VALID"
    assert invalid.status == "INVALID"


def test_xlsx_structural_check_without_optional_runtime_dependency(tmp_path):
    path = tmp_path / "report.xlsx"
    path.write_bytes(b"not an xlsx archive")
    result = asyncio.run(SemanticArtifactValidator().validate(manifest(path, "xlsx")))
    assert result.status in {"INVALID", "UNVERIFIED"}


def test_claim_evidence_citation_and_provenance_chain(tmp_path):
    path = tmp_path / "graph.json"
    path.write_text('{"nodes": [], "edges": []}')
    claim = ClaimProvenance("claim-1", "Claim", ("chunk-1",), verification_id="verify-1", artifact_id="artifact-1")
    evidence = EvidenceItem("doc-1", "chunk-1", "source-hash", "Text")
    verification = VerificationProvenance("verify-1", "claim-1", True, .9, "supported")
    context = ArtifactValidationContext(claims=(claim,), evidence=(evidence,), verifications=(verification,))
    result = asyncio.run(SemanticArtifactValidator().validate(manifest(path, "graph_json"), context))
    assert result.status == "VALID"
    assert result.provenance[0]["document_id"] == "doc-1"
    assert result.provenance[0]["chunk_id"] == "chunk-1"
    assert result.provenance[0]["source_hash"] == "source-hash"


@pytest.mark.parametrize("context, expected", [
    (ArtifactValidationContext(claims=(ClaimProvenance("c", "Claim"),)), "INVALID"),
    (ArtifactValidationContext(claims=(ClaimProvenance("c", "Claim", ("missing",)),)), "INVALID"),
    (ArtifactValidationContext(claims=(ClaimProvenance("c", "Claim", ("e",), verification_id="v"),), evidence=(EvidenceItem("d", "e", "h", "text"),), verifications=(VerificationProvenance("v", "c", False, .9, "failed"),)), "INVALID"),
    (ArtifactValidationContext(claims=(ClaimProvenance("c", "Claim", ("e",)),), evidence=(EvidenceItem("d", "e", "h", "text"),)), "UNVERIFIED"),
])
def test_semantic_evidence_states(tmp_path, context, expected):
    path = tmp_path / "g.json"
    path.write_text('{"nodes": [], "edges": []}')
    result = asyncio.run(SemanticArtifactValidator().validate(manifest(path, "graph_json"), context))
    assert result.status == expected


def test_calculation_correct_wrong_and_unverified(tmp_path):
    path = tmp_path / "g.json"
    path.write_text('{"nodes": [], "edges": []}')
    validator = SemanticArtifactValidator()
    correct = ArtifactValidationContext(calculations=({"name": "sum", "formula": "a + b", "inputs": {"a": "2", "b": "3"}, "result": "5"},))
    wrong = ArtifactValidationContext(calculations=({"name": "sum", "formula": "a + b", "inputs": {"a": "2", "b": "3"}, "result": "6"},))
    unsure = ArtifactValidationContext(calculations=({"name": "formula", "formula": "sqrt(a)", "inputs": {"a": "4"}, "result": "2"},))
    assert asyncio.run(validator.validate(manifest(path, "graph_json"), correct)).status == "VALID"
    assert asyncio.run(validator.validate(manifest(path, "graph_json"), wrong)).status == "INVALID"
    assert asyncio.run(validator.validate(manifest(path, "graph_json"), unsure)).status == "UNVERIFIED"


def test_changed_bytes_change_hash_and_malformed_input_fails_closed(tmp_path):
    path = tmp_path / "g.json"
    path.write_text('{"nodes": [], "edges": []}')
    validator = SemanticArtifactValidator()
    first = asyncio.run(validator.validate(manifest(path, "graph_json")))
    path.write_text('{"nodes": [], "edges": [], "x": 1}')
    second = asyncio.run(validator.validate(manifest(path, "graph_json")))
    assert first.artifact_hash != second.artifact_hash
    invalid = asyncio.run(validator.validate(cast(ArtifactManifest, "malformed")))
    assert invalid.status == "INVALID"
