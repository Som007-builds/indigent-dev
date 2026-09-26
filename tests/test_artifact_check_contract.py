"""Regression coverage for the artifact-validation check contract.

The platform contract is ``ValidationReport.checks: list[dict]`` where every entry is
exactly ``{"name": str, "passed": bool, "detail": str}``. The underlying validator
reports its verdict as ``reason`` and uses ``None`` for a check it could not decide, so
the adapter must normalise both without dropping or relaxing any check.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.artifact_validation import SemanticArtifactValidator
from app.config import Settings
from app.contracts.models import ArtifactManifest
from app.deps import _ArtifactValidatorContract, _as_check

CHECK_KEYS = {"name", "passed", "detail"}


def test_dict_with_reason_is_mapped_onto_detail() -> None:
    assert _as_check({"name": "docx_readable", "passed": True, "reason": "DOCX_OK"}) == {
        "name": "docx_readable",
        "passed": True,
        "detail": "DOCX_OK",
    }


def test_undecided_check_never_leaks_a_null_passed() -> None:
    """A None verdict must surface as a failed bool, not as null in the contract."""
    normalised = _as_check({"name": "calculation", "passed": None, "reason": "CALCULATION_UNVERIFIED"})
    assert normalised["passed"] is False
    assert isinstance(normalised["passed"], bool)
    assert normalised["detail"] == "CALCULATION_UNVERIFIED"


def test_check_shape_is_exact_and_typed() -> None:
    for raw in (
        {"name": "a", "passed": True, "reason": "R"},
        {"name": "b", "passed": None, "reason": "R"},
        {"name": "c", "passed": False, "detail": "D"},
        {"passed": True, "reason": "R"},
        {},
    ):
        check = _as_check(raw)
        assert set(check) == CHECK_KEYS, check
        assert isinstance(check["name"], str)
        assert isinstance(check["passed"], bool)
        assert isinstance(check["detail"], str)


def test_existing_detail_is_preserved() -> None:
    assert _as_check({"name": "x", "passed": False, "detail": "already"})["detail"] == "already"


def test_object_valued_check_is_normalised() -> None:
    class Check:
        name = "obj"
        passed = None
        reason = "OBJ_REASON"

    assert _as_check(Check()) == {"name": "obj", "passed": False, "detail": "OBJ_REASON"}


def test_unrecognised_check_fails_closed() -> None:
    normalised = _as_check(object())
    assert normalised["passed"] is False
    assert set(normalised) == CHECK_KEYS


def test_no_check_is_dropped_even_when_unrecognised() -> None:
    """Normalisation must never silently discard a failed check."""
    checks = [{"name": "a", "passed": False, "reason": "R1"}, object(), {"name": "c", "passed": None}]
    assert len([_as_check(item) for item in checks]) == 3


def _manifest(path: Path, artifact_type: str = "docx") -> ArtifactManifest:
    return ArtifactManifest(
        artifact_id="a1",
        task_id="t1",
        artifact_type=artifact_type,
        path=str(path),
        created_at="2026-09-25T10:00:00Z",
        artifact_hash="hash",
    )


def test_contract_adapter_emits_the_exact_platform_shape(tmp_path) -> None:
    """End-to-end through the real validator and the platform adapter."""
    pytest.importorskip("docx")
    from app.runtime.generators.docx import generate

    path = tmp_path / "report.docx"
    generate(path, {"title": "Report", "recommendation": "Proceed", "sections": []})
    import hashlib

    manifest = _manifest(path)
    manifest.artifact_hash = hashlib.sha256(path.read_bytes()).hexdigest()

    adapter = _ArtifactValidatorContract(SemanticArtifactValidator(), Settings())
    report = asyncio.run(adapter.validate(manifest))

    assert isinstance(report.passed, bool)
    assert report.checks, "the adapter must not drop every check"
    for check in report.checks:
        assert set(check) == CHECK_KEYS, check
        assert isinstance(check["name"], str)
        assert isinstance(check["passed"], bool)
        assert isinstance(check["detail"], str)
        assert "reason" not in check, "the verdict must be carried in detail, not reason"


def test_validator_status_semantics_are_preserved_by_the_adapter(tmp_path) -> None:
    """VALID / INVALID / UNVERIFIED must survive normalisation unchanged."""
    pytest.importorskip("docx")
    from app.runtime.generators.docx import generate

    path = tmp_path / "ok.docx"
    generate(path, {"title": "Report", "recommendation": "Proceed", "sections": []})
    import hashlib

    good = _manifest(path)
    good.artifact_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    missing = _manifest(tmp_path / "missing.docx")

    adapter = _ArtifactValidatorContract(SemanticArtifactValidator(), Settings())
    validator = SemanticArtifactValidator()

    ok_result = asyncio.run(validator.validate(good))
    bad_result = asyncio.run(validator.validate(missing))
    assert ok_result.status in {"VALID", "UNVERIFIED"}
    assert bad_result.status == "INVALID"

    ok_report = asyncio.run(adapter.validate(good))
    bad_report = asyncio.run(adapter.validate(missing))
    assert ok_report.passed is bool(ok_result.valid)
    assert bad_report.passed is False
    assert any(not check["passed"] for check in bad_report.checks)
