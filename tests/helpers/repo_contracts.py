"""Provides constrained repository reads, Git queries, and MCP registration inspection for contract
tests.
"""

from __future__ import annotations

import inspect
import subprocess  # nosec B404
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, get_type_hints

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_repo_contract_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run only Git or the active Python interpreter inside the repository, capturing output."""
    if not command:
        raise ValueError("empty command")
    if command[0] not in {"git", sys.executable}:
        raise ValueError(f"unsupported repo-contract command: {command[0]!r}")
    return subprocess.run(  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit.dangerous-subprocess-use-audit
        command,
        check=True,
        capture_output=True,
        cwd=REPO_ROOT,
        text=True,
    )


def _read(relative_path: str) -> str:
    """Read a UTF-8 repository file relative to the checked contract root."""
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _git_ls(relative_path: str) -> list[str]:
    """List tracked paths below a repository-relative location without consulting the worktree."""
    completed = _run_repo_contract_command(
        ["git", "ls-files", "--", relative_path],
    )
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def _is_tracked(relative_path: str) -> bool:
    """Check whether Git's index contains the repository-relative path."""
    return bool(_git_ls(relative_path))


class _ToolCollector:
    """Dependency-light stand-in for FastMCP registration contract checks."""

    def __init__(self) -> None:
        """Initialize the registration table inspected by MCP contract tests."""
        self.tools: dict[str, SimpleNamespace] = {}

    def tool(self, *, name: str | None = None, description: str | None = None, **_kwargs: Any):
        """Capture a tool's resolved name, documentation, and first Pydantic input schema."""

        def _register(function: Any) -> Any:
            parameters: dict[str, Any] = {}
            hints = get_type_hints(function)
            for parameter in inspect.signature(function).parameters.values():
                annotation = hints.get(parameter.name)
                schema_builder = getattr(annotation, "model_json_schema", None)
                if callable(schema_builder):
                    parameters = schema_builder()
                    break
            tool_name = name or function.__name__
            self.tools[tool_name] = SimpleNamespace(
                description=description or inspect.getdoc(function) or "",
                parameters=parameters,
            )
            return function

        return _register


def _mcp_tools() -> dict[str, SimpleNamespace]:
    """Register the production MCP surface against the dependency-light collector."""
    from mailarium.mcp_server import ToolDeps
    from mailarium.tools import register_all

    collector = _ToolCollector()
    register_all(collector, ToolDeps())
    return collector.tools


def _mcp_tool_count() -> int:
    """Count the tools exposed by the production registration path."""
    return len(_mcp_tools())
