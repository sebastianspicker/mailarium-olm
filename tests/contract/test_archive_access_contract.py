"""Archive access stays behind typed ArchiveDatabase methods outside the archive package."""

from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "mailarium"

RAW_CONNECTION_USE = re.compile(r"\.conn\.(?:execute|executemany|executescript|cursor|commit|rollback)\(|BEGIN IMMEDIATE")
ARCHIVE_CAPABILITY_PROBE = re.compile(r"\b(?:hasattr|getattr)\(\s*(?:self\.)?_?(?:db|email_db|database|archive_database)\s*,")

# All SQLite persistence, including mailbox state, lives in the archive package.
ALLOWED_RAW_CONNECTION_USE: Counter[tuple[str, str]] = Counter()


def _consumer_modules() -> list[Path]:
    """Return modules outside archive-owned persistence that must use typed archive methods."""
    return sorted(path for path in PACKAGE.rglob("*.py") if "archive" not in path.relative_to(PACKAGE).parts[:1])


def _raw_connection_uses() -> Counter[tuple[str, str]]:
    uses: Counter[tuple[str, str]] = Counter()
    for path in _consumer_modules():
        relative = path.relative_to(ROOT).as_posix()
        for line in path.read_text(encoding="utf-8").splitlines():
            for match in RAW_CONNECTION_USE.finditer(line):
                receiver = re.search(r"[\w.]*$", line[: match.start()])
                prefix = receiver.group(0) if receiver else ""
                uses[(relative, f"{prefix}{match.group(0)}")] += 1
    return uses


def test_consumers_do_not_execute_sql_or_control_archive_transactions_directly() -> None:
    """SQL and transaction control belong to named archive repository methods."""
    uses = _raw_connection_uses()

    unexpected = sorted(key for key, count in uses.items() if count > ALLOWED_RAW_CONNECTION_USE.get(key, 0))
    assert unexpected == []


def test_consumers_do_not_probe_archive_capabilities_by_name() -> None:
    """Typed archive access cannot silently skip work after a repository method moves."""
    probes = [
        f"{path.relative_to(ROOT).as_posix()}:{number}: {line.strip()}"
        for path in _consumer_modules()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if ARCHIVE_CAPABILITY_PROBE.search(line)
    ]

    assert probes == []


def test_consumers_do_not_reach_archive_connections() -> None:
    """No module outside the archive package reads a ``conn`` attribute from any object."""
    hits = [
        f"{path.relative_to(ROOT).as_posix()}:{node.lineno}: {ast.unparse(node)}"
        for path in _consumer_modules()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        if isinstance(node, ast.Attribute) and node.attr == "conn"
    ]

    assert hits == []
