"""Step 3 — thin pytest wrapper that calls tools/contract_check.py.

Keeps contract_check.py as a standalone CLI tool but also lets it run under
``pytest -q`` so CI catches breakage automatically.
"""
from __future__ import annotations

import asyncio
import os


def test_g11_contract_check():
    """All G11 endpoints must pass contract_check.py with stub modules."""
    os.environ["INFERENCE_MODE"] = "local"
    os.environ["JOY_MODULES"] = "stub"
    os.environ.pop("GROQ_API_KEY", None)

    # Import after env vars are set so app/config picks them up correctly.
    from tools.contract_check import FAILURES, run_checks

    # Clear any failures from a previous run in the same process.
    FAILURES.clear()

    exit_code = asyncio.run(run_checks())
    assert exit_code == 0, "contract_check failed:\n" + "\n".join(f"  - {f}" for f in FAILURES)
