"""Modern CLI search-filter coverage."""

from __future__ import annotations

import pytest

from mailarium.cli import parse_args, resolve_output_format


def test_search_accepts_filter_flags() -> None:
    args = parse_args(
        [
            "search",
            "--query",
            "budget",
            "--sender",
            "john",
            "--subject",
            "approval",
            "--folder",
            "inbox",
            "--cc",
            "finance-team",
            "--min-score",
            "0.75",
            "--date-from",
            "2023-01-01",
            "--date-to",
            "2023-12-31",
            "--json",
            "--top-k",
            "5",
        ]
    )
    assert args.query == "budget"
    assert args.sender == "john"
    assert args.min_score == 0.75
    assert args.json is True
    assert args.top_k == 5


def test_search_rejects_invalid_date() -> None:
    with pytest.raises(SystemExit):
        parse_args(["search", "--query", "test", "--date-from", "2023/01/01"])


def test_explicit_format_takes_precedence() -> None:
    args = parse_args(["search", "security review", "--format", "text"])
    assert resolve_output_format(args) == "text"
