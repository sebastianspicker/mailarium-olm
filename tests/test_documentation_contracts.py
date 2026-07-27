"""Enforce concise documentation coverage without duplicating test names."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]
PYTHON_ROOTS = (REPO_ROOT / "mailarium", REPO_ROOT / "scripts", REPO_ROOT / "tests")
PRODUCTION_ROOTS = (REPO_ROOT / "mailarium", REPO_ROOT / "scripts")
SHELL_SCRIPTS = tuple(sorted((REPO_ROOT / "scripts").glob("*.sh")))
SHELL_META_COMMENT_PREFIXES = ("# noqa", "# pylint", "# shellcheck", "# todo")
LOW_SIGNAL_DOCSTRING_FRAGMENTS = (
    "for the current operation",
    "for current operation",
    "for the caller",
    "for later method calls",
    "from the state used by",
    "in the shape consumed by",
    "at the private boundary used to assemble this tool response",
    "as part of the controlled flow in",
    "across this module's data flow",
    "before accepting the value",
    "compares or persists it",
    "eligibility gate before downstream work",
    "extracted for clarity",
    "for this workflow",
    "in-progress payload without changing its public schema",
    "matches the required policy",
    "meets the classification rule",
    "normal lifecycle checks",
    "outcome across all explicit fallback branches",
    "profile profile",
    "into the representation required by",
    "representation required by the next response-construction step",
    "returns the normalized local result expected by the surrounding code path",
    "satisfies the required condition",
    "standardized error json",
    "to produce the value consumed by this code path",
    "without duplicating its underlying records",
)
LOW_SIGNAL_TEST_MODULE_PREFIXES = (
    "Collects shared cases for ",
    "Coverage for test ",
    "Fixture cases covering ",
    "Shared test helpers for ",
    "Tests for ",
    "Verifies the focused behavioral contract and safety boundaries exercised by this test slice.",
)
LOW_SIGNAL_TEST_MODULE_FRAGMENTS = (
    "coverage analysis",
    "increase coverage",
    "low-coverage",
    "targeting uncovered",
    "targeting >=",
    "uncovered handler logic",
    "uncovered lines",
)
LOW_SIGNAL_PRODUCTION_MODULE_FRAGMENTS = (
    "consolidated from",
    "helpers extracted from",
    "ponytail principle",
    "split helpers for",
    "to keep each module",
)
GENERATED_DOCSTRING_PATTERNS = tuple(
    re.compile(pattern, re.DOTALL | re.IGNORECASE)
    for pattern in (
        r"Enforces the admission rule for this branch\.",
        r"Checks `[^`]+` before allowing this branch to continue\.",
        r"Accept input only when `[^`]+`\.",
        r"Initialize [^.]+ state and dependencies\.",
        r"(?:Return|Resolve).*?`[^`]*…[^`]*`.*?(?:value|selects)",
    )
)


def _python_files(roots: Iterable[Path]) -> list[Path]:
    return sorted(path for root in roots for path in root.rglob("*.py"))


def _parsed_module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _direct_production_definitions(tree: ast.Module) -> Iterable[ast.AST]:
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        yield node
        if isinstance(node, ast.ClassDef):
            yield from (
                member for member in node.body if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            )


def _required_production_definitions(tree: ast.Module) -> Iterable[ast.AST]:
    """Yield public top-level APIs and public members of public classes."""
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if str(getattr(node, "name", "")).startswith("_"):
            continue
        yield node
        if isinstance(node, ast.ClassDef):
            yield from (
                member
                for member in node.body
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
                and (
                    not str(getattr(member, "name", "")).startswith("_")
                    or (
                        str(getattr(member, "name", "")) == "__init__"
                        and any(isinstance(descendant, ast.Raise) for descendant in ast.walk(member))
                    )
                )
            )


def _location(path: Path, node: ast.AST | None = None) -> str:
    relative = path.relative_to(REPO_ROOT)
    return f"{relative}:{getattr(node, 'lineno', 1)}"


def _name_only_docstring(node: ast.AST, docstring: str) -> bool:
    name = str(getattr(node, "name", "")).lstrip("_")
    normalized = docstring.casefold()
    words = name.replace("_", " ")
    verbs = (
        "build",
        "calculate",
        "compute",
        "create",
        "derive",
        "find",
        "handle",
        "load",
        "normalize",
        "prepare",
        "process",
        "read",
        "record",
        "render",
        "return",
        "run",
        "select",
        "update",
        "validate",
    )
    if normalized in {f"{verb} {words}." for verb in verbs} | {f"{verb} the {words}." for verb in verbs}:
        return True
    for prefix in ("can_", "has_", "is_", "should_"):
        if name.startswith(prefix):
            subject = name.removeprefix(prefix).replace("_", " ")
            return normalized == f"return whether {subject}."
    return False


def _looks_generated_docstring(docstring: str) -> bool:
    """Reject implementation-shaped prose that obscures intent instead of explaining it."""
    if not docstring:
        return False
    normalized = " ".join(docstring.split())
    return any(pattern.search(normalized) for pattern in GENERATED_DOCSTRING_PATTERNS)


def _looks_like_test_name_inventory(docstring: str) -> bool:
    """Identify semicolon-delimited test-name summaries without rejecting behavioral prose."""
    summary = docstring.split("\n\n", 1)[0].strip()
    return summary.casefold().startswith("exercises ") and ";" in summary


def test_every_python_module_explains_its_scope() -> None:
    missing = [
        _location(path)
        for path in _python_files(PYTHON_ROOTS)
        if not (ast.get_docstring(_parsed_module(path), clean=True) or "").strip()
    ]

    assert not missing, f"Python modules without purpose docstrings: {missing}"


def test_shell_scripts_explain_their_scope_after_the_shebang() -> None:
    missing = []
    for path in SHELL_SCRIPTS:
        lines = path.read_text(encoding="utf-8").splitlines()
        header = next((line.strip() for line in lines[1:] if line.strip()), "")
        normalized = header.casefold()
        if not header.startswith("#") or not header.lstrip("#").strip() or normalized.startswith(SHELL_META_COMMENT_PREFIXES):
            missing.append(str(path.relative_to(REPO_ROOT)))

    assert not missing, f"Shell scripts without purpose comments: {missing}"


def test_test_module_docstrings_describe_behavior_not_filename() -> None:
    low_signal: list[str] = []
    locations_by_docstring: dict[str, list[str]] = {}
    for path in _python_files((REPO_ROOT / "tests",)):
        docstring = ast.get_docstring(_parsed_module(path), clean=True) or ""
        normalized = docstring.casefold()
        if (
            normalized.startswith(tuple(prefix.casefold() for prefix in LOW_SIGNAL_TEST_MODULE_PREFIXES))
            or any(fragment in normalized for fragment in LOW_SIGNAL_TEST_MODULE_FRAGMENTS)
            or _looks_like_test_name_inventory(docstring)
        ):
            low_signal.append(f"{_location(path)} ({docstring!r})")
        locations_by_docstring.setdefault(docstring, []).append(_location(path))

    repeated_generic = {
        docstring: locations
        for docstring, locations in locations_by_docstring.items()
        if docstring and len(docstring) < 200 and len(locations) >= 3
    }

    assert not low_signal, f"Test modules with filename-only purpose docstrings: {low_signal}"
    assert not repeated_generic, f"Test modules sharing a generic purpose docstring: {repeated_generic}"


def test_production_module_docstrings_describe_runtime_scope() -> None:
    low_signal = []
    for path in _python_files(PRODUCTION_ROOTS):
        docstring = ast.get_docstring(_parsed_module(path), clean=True) or ""
        normalized = docstring.casefold()
        if any(fragment in normalized for fragment in LOW_SIGNAL_PRODUCTION_MODULE_FRAGMENTS):
            low_signal.append(f"{_location(path)} ({docstring!r})")

    assert not low_signal, f"Production modules with history-only purpose docstrings: {low_signal}"


def test_generated_docstring_classifier_is_narrow() -> None:
    rejected = (
        "Enforces the admission rule for this branch.",
        "checks `value < 0` before allowing this branch to continue.",
        "Initialize SearchIndex state and dependencies.",
        "Return `_build_payload(items…` as the dict value.",
        "Useful summary.\n\nreturn `_build_payload(items…` as the dict value.",
    )
    accepted = (
        "Resolve output format; `json` selects `JsonRenderer`.",
        "Interpret `start…stop` as an inclusive range.",
        "Return `tenant_id` as the cache partition value.",
    )

    assert all(_looks_generated_docstring(docstring) for docstring in rejected)
    assert not any(_looks_generated_docstring(docstring) for docstring in accepted)


def test_test_module_classifier_is_narrow() -> None:
    assert _looks_like_test_name_inventory("Exercises parses valid input; rejects empty input.")
    assert not _looks_like_test_name_inventory(
        "Exercises OLM parsing across body recovery, address variants, and source-header fallbacks."
    )


def test_direct_production_callables_explain_their_contract() -> None:
    missing: list[str] = []
    for path in _python_files(PRODUCTION_ROOTS):
        for node in _required_production_definitions(_parsed_module(path)):
            if not (ast.get_docstring(node, clean=True) or "").strip():
                missing.append(f"{_location(path, node)} ({getattr(node, 'name', '<anonymous>')})")

    assert not missing, f"Public production definitions without intent docstrings: {missing}"


def test_production_docstrings_avoid_placeholder_language() -> None:
    low_signal: list[str] = []
    for path in _python_files(PRODUCTION_ROOTS):
        for node in _direct_production_definitions(_parsed_module(path)):
            docstring = ast.get_docstring(node, clean=True) or ""
            normalized = docstring.casefold()
            if (
                any(fragment in normalized for fragment in LOW_SIGNAL_DOCSTRING_FRAGMENTS)
                or _name_only_docstring(node, docstring)
                or _looks_generated_docstring(docstring)
            ):
                low_signal.append(f"{_location(path, node)} ({getattr(node, 'name', '<anonymous>')}: {docstring!r})")

    assert not low_signal, f"Production docstrings with placeholder wording: {low_signal}"
