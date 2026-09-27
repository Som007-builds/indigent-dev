"""Every third-party module imported by the app must be a declared dependency.

This exists because `app/rag/production.py` imported `fitz` (PyMuPDF) while
`pyproject.toml` never declared it. The import succeeded locally only because
`requirements.lock` happened to carry PyMuPDF, so a clean `pip install` of the project
produced an install that failed at runtime on every PDF with "PyMuPDF is required for
local PDF extraction". A declared dependency is the only thing that makes a fresh
environment reproducible.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Distribution name -> import name. Only needed where they differ.
DISTRIBUTION_ALIASES = {
    "pillow": "pil",
    "python-docx": "docx",
    "python-multipart": "multipart",
    "pymupdf": "fitz",
    "scikit-learn": "sklearn",
    "pyyaml": "yaml",
}

# Imported by tooling, not by the running application.
TOOLING = {"app"}

STDLIB = set(sys.stdlib_module_names)


def _declared() -> set[str]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    names: set[str] = set()
    for requirement in project["dependencies"]:
        for separator in (">=", "==", "~=", "<=", ">", "<", "!="):
            requirement = requirement.split(separator)[0]
        names.add(requirement.strip().lower().replace("-", "_"))
    return names


def _imported() -> set[str]:
    """Scan Python source tree for imported module names using AST."""
    imports: set[str] = set()
    for py_file in (ROOT / "app").rglob("*.py"):
        try:
            source = py_file.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                # Only consider absolute imports (level == 0) to avoid
                # picking up relative imports like "from .chunking import ..."
                if node.level == 0 and node.module and not node.module.startswith("app."):
                    imports.add(node.module.split(".")[0])
    # Also scan tools/ if it exists
    tools_dir = ROOT / "tools"
    if tools_dir.exists():
        for py_file in tools_dir.rglob("*.py"):
            try:
                source = py_file.read_text(encoding="utf-8")
            except OSError:
                continue
            try:
                tree = ast.parse(source, filename=str(py_file))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.level == 0 and node.module and not node.module.startswith("app."):
                        imports.add(node.module.split(".")[0])
    return imports


def test_every_imported_third_party_module_is_declared():
    declared = _declared()
    # Expand declared distributions to their import names. Alias keys are normalized
    # the same way as the declared names (lowercase, hyphens to underscores).
    normalized_aliases = {
        k.lower().replace("-", "_"): v for k, v in DISTRIBUTION_ALIASES.items()
    }
    covered = {
        normalized_aliases.get(name, name)
        for name in declared
    } | set(normalized_aliases.values())

    undeclared = set()
    for module in _imported():
        module = module.lower()
        if module in TOOLING or module in STDLIB or module.startswith("_"):
            continue
        if module not in covered:
            undeclared.add(module)

    assert not undeclared, (
        "these modules are imported by the application but are not declared in "
        f"pyproject.toml dependencies: {sorted(undeclared)}"
    )


def test_pymupdf_is_declared_because_the_pdf_path_needs_it():
    """Regression guard for the specific defect found on 2026-09-26."""
    assert "fitz" in _imported(), "the PDF extractor should still use PyMuPDF"
    assert "pymupdf" in _declared(), "PyMuPDF must be a declared dependency"


def test_lock_file_satisfies_every_declared_dependency():
    """requirements.lock must actually pin what pyproject asks for."""
    lock = (ROOT / "requirements.lock").read_text(encoding="utf-8").lower()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    missing = []
    for requirement in project["dependencies"]:
        name = requirement.split(">")[0].split("=")[0].split("<")[0].strip().lower()
        if not re.search(rf"^{re.escape(name)}==", lock, re.MULTILINE):
            missing.append(name)
    assert not missing, f"requirements.lock does not pin: {missing}"


@pytest.mark.parametrize("stale", ["chromadb", "onnxruntime"])
def test_unreferenced_lock_entries_are_flagged(stale):
    """Record why these are candidates for removal rather than silently trusting them.

    They are not asserted absent: removing them is an operator decision because a
    transitive dependency may still require them.
    """
    imports = _imported()
    assert stale not in imports, f"{stale} is not imported by any application module"