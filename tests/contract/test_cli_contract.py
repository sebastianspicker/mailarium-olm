"""Stable public CLI parsing and package-entrypoint contracts."""

from __future__ import annotations

import subprocess
import sys

import pytest

from mailarium import __version__
from mailarium.cli import parse_args


def test_cli_search_parser_normalizes_public_options() -> None:
    args = parse_args(
        [
            "--sqlite-path",
            "private/archive.db",
            "search",
            "monthly invoice",
            "--top-k",
            "25",
            "--scope",
            "Finance",
            "--date-from",
            "2026-01-01",
            "--format",
            "json",
        ]
    )

    assert args.subcommand == "search"
    assert args.query == "monthly invoice"
    assert args.top_k == 25
    assert args.scope == "finance"
    assert args.date_from == "2026-01-01"
    assert args.format == "json"
    assert args.sqlite_path == "private/archive.db"


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["search"], "search requires a query"),
        (["search", "one", "--query", "two"], "positional argument or --query"),
        (["search", "one", "--top-k", "1001"], "Value must be <= 1000"),
        (["search", "one", "--date-from", "2026-02-01", "--date-to", "2026-01-01"], "--date-from cannot be later"),
        (["search", "one", "--json", "--format", "json"], "--json cannot be combined with --format"),
    ],
)
def test_cli_parser_rejects_invalid_public_requests(argv: list[str], message: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit, match="2"):
        parse_args(argv)

    assert message in capsys.readouterr().err


def test_package_entrypoint_reports_the_package_version() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "mailarium", "--version"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() == __version__
    assert completed.stderr == ""


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["export", "report"], "private/exports/report.html"),
        (["export", "network"], "private/exports/network.graphml"),
    ],
)
def test_cli_export_defaults_stay_inside_the_private_output_root(argv: list[str], expected: str) -> None:
    assert parse_args(argv).output == expected
