"""Validation failures for the modern CLI syntax."""

import pytest

from mailarium.cli import parse_args


@pytest.mark.parametrize(
    "argv",
    [
        ["search", "budget", "--top-k", "0"],
        ["search", "budget", "--top-k", "1001"],
        ["search", "budget", "--min-score", "1.5"],
        ["search", "budget", "--json", "--format", "text"],
        ["--format", "json"],
    ],
)
def test_invalid_modern_arguments_are_rejected(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse_args(argv)
