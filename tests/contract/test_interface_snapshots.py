"""Snapshot contracts for Mailarium's externally observable interfaces.

The snapshots were recorded from the pre-reconstruction implementation and pin
the MCP tool catalog (names, input schemas, safety annotations), the complete
CLI and ingest command trees, and the canonical SQLite schema. An intentional
interface change regenerates them with ``MAILARIUM_UPDATE_SNAPSHOTS=1`` and is
reviewed as a contract diff.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import os
import re
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

SNAPSHOTS = Path(__file__).parent / "snapshots"
_UPDATE = os.environ.get("MAILARIUM_UPDATE_SNAPSHOTS") == "1"


def _assert_snapshot(name: str, actual: Any) -> None:
    path = SNAPSHOTS / name
    rendered = json.dumps(actual, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    if _UPDATE:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        return
    assert path.is_file(), f"missing snapshot {path}; run with MAILARIUM_UPDATE_SNAPSHOTS=1"
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert actual == expected


def test_mcp_tool_catalog_matches_snapshot() -> None:
    from mailarium.interfaces.mcp.runtime_state import McpRuntimeState
    from mailarium.interfaces.mcp.server import create_mcp_server

    state = McpRuntimeState()
    try:
        tools = asyncio.run(create_mcp_server(state).list_tools())
    finally:
        state.close()
    catalog = {
        tool.name: {
            "description": tool.description,
            "inputSchema": tool.inputSchema,
            "annotations": tool.annotations.model_dump() if tool.annotations else None,
        }
        for tool in tools
    }
    _assert_snapshot("mcp_tools.json", catalog)


_CHOICES = re.compile(r"^  \{([a-z0-9_,-]+)\}", re.MULTILINE)


def _help_text(main: Callable[[list[str]], Any], argv: list[str]) -> str:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), pytest.raises(SystemExit) as exited:
        main([*argv, "--help"])
    assert exited.value.code == 0
    return buffer.getvalue()


def _normalized(text: str) -> str:
    # Parsers without an explicit ``prog`` derive it from the launching
    # interpreter (``python`` vs ``python3 -m pytest``), which also shifts line
    # wrapping. Neither is a contract, so compare normalized tokens.
    return " ".join(text.replace(argparse.ArgumentParser().prog, "<default-prog>").split())


def _command_tree(main: Callable[[list[str]], Any]) -> dict[str, str]:
    tree: dict[str, str] = {}
    pending: list[tuple[list[str], str]] = [([], "")]
    while pending:
        path, parent_text = pending.pop()
        text = _help_text(main, path)
        if text == parent_text:
            # A positional value with choices, not a nested subcommand.
            continue
        tree[" ".join(path) or "<root>"] = _normalized(text)
        if match := _CHOICES.search(text):
            pending.extend(([*path, choice], text) for choice in match.group(1).split(","))
    return tree


@pytest.fixture
def fixed_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLUMNS", "120")
    monkeypatch.setenv("LINES", "50")


@pytest.mark.usefixtures("fixed_terminal")
def test_cli_command_tree_matches_snapshot() -> None:
    from mailarium.interfaces.cli.main import parse_args

    _assert_snapshot("cli_help.json", _command_tree(parse_args))


@pytest.mark.usefixtures("fixed_terminal")
def test_ingest_command_matches_snapshot() -> None:
    from mailarium.ingest import main

    _assert_snapshot("ingest_help.json", {"<root>": _normalized(_help_text(main, []))})


def _schema(connection: sqlite3.Connection) -> dict[str, Any]:
    objects = connection.execute(
        "SELECT type, name, tbl_name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
    ).fetchall()
    schema: dict[str, Any] = {"tables": {}, "indexes": {}, "triggers": [], "views": []}
    for kind, name, table in objects:
        if kind == "table":
            columns = connection.execute(f'PRAGMA table_info("{name}")').fetchall()
            schema["tables"][name] = [
                {"name": column[1], "type": column[2], "notnull": column[3], "default": column[4], "pk": column[5]}
                for column in columns
            ]
        elif kind == "index":
            schema["indexes"][name] = table
        elif kind == "trigger":
            schema["triggers"].append(name)
        elif kind == "view":
            schema["views"].append(name)
    schema["schema_version"] = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    return schema


def test_archive_schema_matches_snapshot(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from mailarium.interfaces.runtime import ApplicationRuntime

    monkeypatch.setenv("MAILARIUM_RUNTIME_HOME", str(tmp_path / "runtime"))
    monkeypatch.delenv("MAILARIUM_ALLOWED_RUNTIME_ROOTS", raising=False)
    with ApplicationRuntime(sqlite_path="archive/archive.db", vector_index_path="vectors") as runtime:
        assert runtime.mailbox_service(create_archive=True) is not None
        sqlite_path = runtime.sqlite_path
    with contextlib.closing(sqlite3.connect(sqlite_path)) as connection:
        _assert_snapshot("archive_schema.json", _schema(connection))
