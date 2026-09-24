"""Joint real-module acceptance matrix; never substitutes stubs for Joy's modules."""

from importlib.util import find_spec

import pytest

JOY_MODULES = (
    "app.agent",
    "app.providers",
    "app.rag",
    "app.artifact_validation",
    "app.policy",
)


def _require_real_modules() -> None:
    missing = [module for module in JOY_MODULES if find_spec(module) is None]
    if missing:
        pytest.skip(
            "Joy-owned real modules have not been merged: " + ", ".join(missing)
        )


@pytest.mark.needs_models
@pytest.mark.parametrize(
    ("row", "scenario", "expected"),
    [
        (1, "local chat Demo A", "task completes with local inference"),
        (2, "Groq chat", "external inference active and counters increment"),
        (3, "local provider down", "task fails and Groq call count is zero"),
        (4, "missing local model", "clean task failure"),
        (5, "unauthorized tool", "rejected and POLICY_DENIED is audited"),
        (6, "relative and absolute path traversal", "paths are rejected"),
        (7, "sandbox outbound connection", "blocked and audited"),
        (8, "sandbox host-file access", "denied"),
        (9, "malformed upload", "ingest fails while service stays available"),
        (10, "PDF prompt injection", "no tool authority is gained"),
        (11, "false citation", "VERIFY fails and REPAIR begins"),
        (12, "bad calculation", "artifact validation fails"),
        (13, "repeated failed code tests", "more than three repairs fails safely"),
        (14, "runaway loop", "hard task timeout"),
        (15, "tool timeout", "controlled failure is audited"),
        (16, "output flood", "controlled failure"),
        (17, "resource exhaustion", "controlled failure"),
        (18, "approve and reject", "human approval flow is retained"),
        (19, "invalid artifact", "artifact validation rejects it"),
        (20, "demo audit timeline", "all required categories include inference_mode"),
        (21, "both sovereignty modes", "dashboard matches configured mode"),
        (22, "Demo B and Demo C", "both paths complete safely"),
    ],
    ids=lambda value: f"row-{value}" if isinstance(value, int) else str(value),
)
def test_real_module_failure_and_security_matrix(row: int, scenario: str, expected: str) -> None:
    """Gate every required acceptance scenario on the merged, real control plane.

    The fixture deliberately skips rather than faking a result: expected behavior
    is an integration obligation of the real modules named in the PRD.
    """
    _require_real_modules()
    pytest.fail(
        f"Matrix row {row} ({scenario}) requires Joy's merged real-module test harness: {expected}"
    )
