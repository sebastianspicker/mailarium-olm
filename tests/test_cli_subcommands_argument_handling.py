"""CLI argument handling for the required modern command surface."""

from __future__ import annotations

import pytest

from mailarium.cli import parse_args


def test_search_rejects_both_positional_and_flag_query() -> None:
    with pytest.raises(SystemExit):
        parse_args(["search", "positional query", "--query", "flag query"])


def test_search_requires_query() -> None:
    with pytest.raises(SystemExit):
        parse_args(["search"])


def test_subcommand_is_required() -> None:
    with pytest.raises(SystemExit):
        parse_args([])


@pytest.mark.parametrize(
    "argv",
    [
        ["--query", "budget"],
        ["--stats"],
        ["--browse"],
        ["--export-thread", "conv-123"],
        ["--evidence-list"],
        ["--reset-index"],
        ["--generate-training-data", "out.jsonl"],
    ],
)
def test_legacy_flat_flags_are_rejected(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse_args(argv)


def test_legal_case_command_is_rejected() -> None:
    with pytest.raises(SystemExit):
        parse_args(["case", "analyze", "--input", "case.json"])


def test_search_accepts_subcommand_scoped_runtime_paths(tmp_path) -> None:
    args = parse_args(["search", "--query", "test", "--sqlite-path", str(tmp_path / "email.db")])
    assert args.subcommand == "search"
    assert args.sqlite_path == str(tmp_path / "email.db")
