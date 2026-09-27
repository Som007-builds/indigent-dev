"""Regression guards for the two Soham-side XLSX/calculation gaps.

Both gaps shared one shape: the machinery was correct and reachable, but nothing
ever fed it. These tests pin the wiring, not the machinery.

1. The planner's tool menu is derived from Joy's allow-list, so a tool cannot be
   advertised without being permitted, nor permitted-and-required while invisible.
2. ``GroundedAnswerArtifactHandler`` carries a well-formed ``calculations`` payload
   through to the DOCX spec and the validation context, and fails closed on
   anything malformed instead of forwarding it to the validator.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.agent.grounded_artifact import (
    CALCULATIONS_FIELD,
    GroundedAnswerArtifactHandler,
    _validated_calculations,
)
from app.agent.state import TaskSnapshot
from app.contracts.models import ArtifactManifest, TaskContext
from app.deps import (
    _REQUIRED_PLANNER_TOOLS,
    _TOOL_SCHEMA_CATALOG,
    _planner_tool_schemas,
)
from app.policy.allowlist import ALLOWED_TOOLS, KNOWN_TOOLS
from app.rag.models import ClaimProvenance, EvidenceItem, EvidenceProvenance, VerificationProvenance
from app.rag.verification import CitationVerificationResult


class MemoryArtifactStore:
    def __init__(self):
        self.registered: list[ArtifactManifest] = []

    async def register(self, ctx, artifact_type, path, source_evidence_ids=None, metadata=None):
        manifest = ArtifactManifest(
            artifact_id=f"artifact-{len(self.registered) + 1}",
            task_id=ctx.task_id,
            artifact_type=artifact_type,
            path=path,
            created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            artifact_hash=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            source_evidence_ids=source_evidence_ids or [],
            metadata=metadata or {},
        )
        self.registered.append(manifest)
        return manifest


# --------------------------------------------------------------------------- #
# 1. Planner tool menu is sourced from the allow-list, never hand-duplicated.
# --------------------------------------------------------------------------- #


def test_planner_menu_exposes_both_artifact_generators():
    names = {schema.name for schema in _planner_tool_schemas()}
    assert "create_docx" in names, "DOCX generation was invisible to the planner"
    assert "create_xlsx" in names, "XLSX generation was invisible to the planner"
    assert _REQUIRED_PLANNER_TOOLS <= names


def test_every_planner_tool_is_allow_listed_so_the_menu_cannot_outrun_policy():
    """Menu subset of the allow-list: the planner can never be offered a tool that
    policy.validate would deny, which would burn a turn and fail the task."""
    for schema in _planner_tool_schemas():
        assert schema.name in KNOWN_TOOLS, f"{schema.name} is advertised but not allow-listed"
        assert any(
            schema.name in tools for tools in ALLOWED_TOOLS.values()
        ), f"{schema.name} is in KNOWN_TOOLS but in no task type"


def test_planner_menu_is_derived_from_the_allow_list_rather_than_hardcoded(monkeypatch):
    """A tool added to Joy's allow-list and to the catalog appears automatically.

    This is the anti-drift property: the menu is a projection of the catalog, not
    three hand-written tuples, so adding a tool cannot require editing deps.py.
    """
    import app.policy.allowlist as allowlist

    widened = {
        task_type: tools | {"run_tests"} for task_type, tools in allowlist.ALLOWED_TOOLS.items()
    }
    monkeypatch.setattr(allowlist, "ALLOWED_TOOLS", widened)
    monkeypatch.setattr(
        allowlist, "KNOWN_TOOLS", frozenset().union(*widened.values())
    )
    monkeypatch.setitem(
        _TOOL_SCHEMA_CATALOG, "run_tests", ("Run the task test suite.", {"type": "object"})
    )
    names = {schema.name for schema in _planner_tool_schemas()}
    assert "run_tests" in names


def test_planner_menu_refuses_to_advertise_a_tool_policy_does_not_allow(monkeypatch):
    """Drift in the dangerous direction fails the build loudly, not silently."""
    monkeypatch.setitem(_TOOL_SCHEMA_CATALOG, "not_allow_listed", ("Nope.", {"type": "object"}))
    with pytest.raises(RuntimeError, match="not_allow_listed"):
        _planner_tool_schemas()


def test_planner_menu_refuses_to_build_when_a_required_tool_disappears(monkeypatch):
    """Guards the original bug: dropping create_xlsx from the menu must not
    silently return, because the artifact stage would then be unreachable."""
    for name in ("create_docx", "create_xlsx"):
        monkeypatch.delitem(_TOOL_SCHEMA_CATALOG, name)
    with pytest.raises(RuntimeError, match="missing required tools"):
        _planner_tool_schemas()


def test_planner_schemas_carry_real_descriptions_and_parameter_objects():
    for schema in _planner_tool_schemas():
        assert schema.description.strip(), f"{schema.name} has no description"
        assert schema.parameters.get("type") == "object", f"{schema.name} has no object schema"
    by_name = {schema.name: schema for schema in _planner_tool_schemas()}
    for name in ("create_docx", "create_xlsx"):
        assert set(by_name[name].parameters["required"]) == {"output", "spec"}


# --------------------------------------------------------------------------- #
# 2. Calculations pass through, or fail closed.
# --------------------------------------------------------------------------- #


def _task(tmp_path: Path, final_result: dict) -> TaskSnapshot:
    return TaskSnapshot(
        task_id="calc-task",
        user_request="question",
        task_type="inspection",
        inference_mode="local",
        workspace=tmp_path,
        final_result=final_result,
        verification_status="passed",
    )


def _context(tmp_path: Path) -> TaskContext:
    return TaskContext(
        task_id="calc-task", task_type="inspection", workspace=tmp_path, inference_mode="local"
    )


def _claim_and_result():
    evidence = [EvidenceItem("doc", "chunk-1", "source-hash", "Pressure is 10 bar.", page=3, section="Operation")]
    evp = EvidenceProvenance("doc", "chunk-1", "source-hash", "claim-1", "verification-1")
    vp = VerificationProvenance("verification-1", "claim-1", True, 0.95, "supported")
    result = CitationVerificationResult(True, 0.95, "supported", "claim-1", evp, vp)
    return evidence, [ClaimProvenance("claim-1", "supported", ("chunk-1",))], [result]


def test_validated_calculations_accepts_a_well_formed_payload():
    payload = {
        CALCULATIONS_FIELD: [
            {"name": "margin", "formula": "a - b", "inputs": {"a": "10", "b": "4"}, "result": "6"}
        ]
    }
    assert _validated_calculations(payload, "t") == payload[CALCULATIONS_FIELD]


def test_validated_calculations_drops_extra_keys_the_docx_spec_forbids():
    """CalculationSpec sets extra="forbid"; unfiltered pass-through would abort
    the whole DOCX build with VALIDATION_ERROR instead of dropping one entry."""
    payload = {
        CALCULATIONS_FIELD: [
            {
                "name": "margin",
                "formula": "a - b",
                "inputs": {"a": "10", "b": "4"},
                "result": "6",
                "unit": "bar",
                "confidence": 0.9,
            }
        ]
    }
    assert _validated_calculations(payload, "t") == [
        {"name": "margin", "formula": "a - b", "inputs": {"a": "10", "b": "4"}, "result": "6"}
    ]


def test_validated_calculations_defaults_to_empty_and_logs_when_absent(caplog):
    with caplog.at_level(logging.INFO, logger="app.agent.grounded_artifact"):
        assert _validated_calculations({"answer": "x"}, "t") == []
    assert any("no calculations field" in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({CALCULATIONS_FIELD: "a - b"}, "not a list"),
        ({CALCULATIONS_FIELD: {"formula": "a"}}, "not a list"),
        ({CALCULATIONS_FIELD: ["a - b"]}, "not an object"),
        ({CALCULATIONS_FIELD: [{}]}, "name must be a non-empty string"),
        ({CALCULATIONS_FIELD: [{"name": "m"}]}, "formula must be a non-empty string"),
        ({CALCULATIONS_FIELD: [{"name": "m", "formula": "  "}]}, "formula must be a non-empty string"),
        ({CALCULATIONS_FIELD: [{"name": "m", "formula": 7}]}, "formula must be a non-empty string"),
        ({CALCULATIONS_FIELD: [{"name": 5, "formula": "a"}]}, "name must be a non-empty string"),
        ({CALCULATIONS_FIELD: [{"name": "m", "formula": "a", "inputs": "a=1"}]}, "strings to strings"),
        ({CALCULATIONS_FIELD: [{"name": "m", "formula": "a", "inputs": {"a": 1}}]}, "strings to strings"),
        ({CALCULATIONS_FIELD: [{"name": "m", "formula": "a", "inputs": {"a": "1"}}]}, "result must be a non-empty string"),
        ({CALCULATIONS_FIELD: [{"name": "m", "formula": "a", "inputs": {"a": "1"}, "result": 6}]}, "does not accept a bare number"),
        ({CALCULATIONS_FIELD: [{"name": "m", "formula": "a", "inputs": {"a": "1"}, "result": True}]}, "result must be a non-empty string"),
    ],
)
def test_validated_calculations_fails_closed_on_malformed_input(payload, reason, caplog):
    with caplog.at_level(logging.WARNING, logger="app.agent.grounded_artifact"):
        assert _validated_calculations(payload, "t") == []
    assert any(reason in record.getMessage() for record in caplog.records), caplog.records


def test_validated_calculations_keeps_good_entries_and_drops_only_the_bad():
    payload = {
        CALCULATIONS_FIELD: [
            {"name": "sum", "formula": "a + b", "inputs": {"a": "2", "b": "3"}, "result": "5"},
            {"name": "broken", "formula": "", "inputs": {"a": "1"}, "result": "1"},
            {"name": "product", "formula": "a * b", "inputs": {"a": "2", "b": "4"}, "result": "8"},
        ]
    }
    assert [item["name"] for item in _validated_calculations(payload, "t")] == ["sum", "product"]


@pytest.mark.asyncio
async def test_grounded_artifact_threads_calculations_into_spec_and_validation_context(tmp_path):
    pytest.importorskip("docx")
    (tmp_path / "outputs").mkdir()
    store = MemoryArtifactStore()
    handler = GroundedAnswerArtifactHandler(store)
    evidence, claims, results = _claim_and_result()
    calculations = [{"name": "margin", "formula": "a - b", "inputs": {"a": "10", "b": "4"}, "result": "6"}]

    manifest = await handler.create(
        _task(tmp_path, {"answer": "supported", CALCULATIONS_FIELD: calculations}),
        _context(tmp_path),
        claims,
        evidence,
        results,
    )

    # Both spec copies carry it -- they are now the same object, so they cannot drift.
    assert manifest.metadata["spec"]["calculations"] == calculations
    context = handler.validation_context("calc-task")
    assert context is not None
    assert [dict(item) for item in context.calculations] == calculations


@pytest.mark.asyncio
async def test_grounded_artifact_fails_closed_on_malformed_calculations(tmp_path, caplog):
    pytest.importorskip("docx")
    (tmp_path / "outputs").mkdir()
    store = MemoryArtifactStore()
    handler = GroundedAnswerArtifactHandler(store)
    evidence, claims, results = _claim_and_result()

    with caplog.at_level(logging.WARNING, logger="app.agent.grounded_artifact"):
        manifest = await handler.create(
            _task(tmp_path, {"answer": "supported", CALCULATIONS_FIELD: ["garbage", 17]}),
            _context(tmp_path),
            claims,
            evidence,
            results,
        )

    assert manifest.metadata["spec"]["calculations"] == []
    context = handler.validation_context("calc-task")
    assert context is not None and context.calculations == ()
    assert any("not an object" in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_grounded_artifact_without_calculations_field_still_validates(tmp_path):
    """The overwhelmingly common case: no field at all must behave exactly as before."""
    pytest.importorskip("docx")
    (tmp_path / "outputs").mkdir()
    store = MemoryArtifactStore()
    handler = GroundedAnswerArtifactHandler(store)
    evidence, claims, results = _claim_and_result()

    manifest = await handler.create(
        _task(tmp_path, {"answer": "supported"}), _context(tmp_path), claims, evidence, results
    )

    assert manifest.metadata["spec"]["calculations"] == []
    context = handler.validation_context("calc-task")
    assert context is not None and context.calculations == ()


@pytest.mark.asyncio
async def test_grounded_artifact_calculation_reaches_the_semantic_validator(tmp_path):
    """End of the chain: a threaded calculation is actually verified, proving
    _safe_arithmetic finally has a production caller."""
    pytest.importorskip("docx")
    from app.artifact_validation import SemanticArtifactValidator

    (tmp_path / "outputs").mkdir()
    store = MemoryArtifactStore()
    handler = GroundedAnswerArtifactHandler(store)
    evidence, claims, results = _claim_and_result()

    manifest = await handler.create(
        _task(
            tmp_path,
            {
                "answer": "supported",
                CALCULATIONS_FIELD: [
                    {"name": "margin", "formula": "a - b", "inputs": {"a": "10", "b": "4"}, "result": "6"}
                ],
            },
        ),
        _context(tmp_path),
        claims,
        evidence,
        results,
    )

    report = await SemanticArtifactValidator().validate(manifest, handler.validation_context("calc-task"))
    calculation_checks = [check for check in report.checks if check.get("name") == "calculation"]
    assert calculation_checks, "no calculation check ran -- the payload never reached the validator"
    assert calculation_checks[0]["passed"] is True
    assert calculation_checks[0]["computed"] == 6
