from __future__ import annotations

import pytest

from app.agent.state import TaskSnapshot
from app.agent.verification import TaskVerifier


def task(*calls: dict) -> TaskSnapshot:
    snapshot = TaskSnapshot(
        task_id="t1", user_request="do the thing", task_type="coding", inference_mode="local"
    )
    snapshot.tool_calls = list(calls)
    return snapshot


def ok(tool: str, **overrides) -> dict:
    call = {"tool": tool, "ok": True, "exit_code": 0, "data": {}, "resource_events": []}
    call.update(overrides)
    return call


@pytest.mark.asyncio
async def test_no_tool_results_is_never_verified():
    verified, reason = await TaskVerifier().verify(task())
    assert not verified
    assert reason == "NO_TOOL_RESULTS"


@pytest.mark.asyncio
async def test_successful_execution_and_tests_verify():
    verified, reason = await TaskVerifier().verify(
        task(ok("create_code"), ok("execute_code"), ok("run_tests", data={"passed": 3, "failed": 0}))
    )
    assert verified
    assert reason.startswith("VERIFIED:")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "call,expected",
    [
        (ok("execute_code", ok=False, error="boom"), "TOOL_FAILED"),
        (ok("execute_code", exit_code=1), "NONZERO_EXIT"),
        (ok("execute_code", resource_events=["TIMEOUT"]), "TOOL_TIMEOUT"),
        (ok("execute_code", resource_events=["OOM_KILLED"]), "RESOURCE_LIMIT"),
        (ok("execute_code", resource_events=["PIDS_LIMIT"]), "RESOURCE_LIMIT"),
        (ok("run_tests", data={"passed": 1, "failed": 2}), "TESTS_FAILED"),
    ],
)
async def test_evidence_based_failures_are_reported(call, expected):
    verified, reason = await TaskVerifier().verify(task(ok("create_code"), call))
    assert not verified
    assert reason.startswith(expected)


@pytest.mark.asyncio
async def test_verification_is_independent_of_the_status_flag():
    """The verifier must not be satisfiable by setting its own status field."""
    snapshot = task(ok("read_file"))
    snapshot.verification_status = "passed"
    verified, reason = await TaskVerifier().verify(snapshot)
    assert not verified
    assert reason == "NO_TERMINAL_RESULT"


@pytest.mark.asyncio
async def test_terminal_result_is_required_by_default_and_optional_otherwise():
    calls = task(ok("read_file"))
    verified, reason = await TaskVerifier().verify(calls)
    assert not verified and reason == "NO_TERMINAL_RESULT"

    lenient = TaskVerifier(require_terminal_result=False)
    verified, _ = await lenient.verify(calls)
    assert verified
