import warnings

import pytest


def _parse_legacy_args(argv: list[str]):
    from src.cli import parse_args

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        args = parse_args(argv)
    assert any(issubclass(item.category, DeprecationWarning) for item in caught)
    return args


def test_parse_args_supports_filter_flags():
    args = _parse_legacy_args(
        [
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
    assert args.subject == "approval"
    assert args.folder == "inbox"
    assert args.cc == "finance-team"
    assert args.min_score == 0.75
    assert args.date_from == "2023-01-01"
    assert args.date_to == "2023-12-31"
    assert args.json is True
    assert args.top_k == 5


def test_parse_args_rejects_invalid_dates():
    from src.cli import parse_args

    with warnings.catch_warnings():
        warnings.simplefilter("always")
        with pytest.raises(SystemExit):
            parse_args(["--query", "test", "--date-from", "2023/01/01"])


def test_parse_args_supports_format_json():
    args = _parse_legacy_args(
        [
            "--query",
            "security review",
            "--format",
            "json",
        ]
    )

    assert args.query == "security review"
    assert args.format == "json"


def test_resolve_output_format_prefers_explicit_format():
    from src.cli import resolve_output_format

    args = _parse_legacy_args(["--query", "security review", "--format", "text"])

    assert resolve_output_format(args) == "text"


def test_resolve_output_format_supports_legacy_json_flag():
    from src.cli import resolve_output_format

    args = _parse_legacy_args(["--query", "security review", "--json"])

    assert resolve_output_format(args) == "json"


def test_parse_args_cc_requires_query():
    from src.cli import parse_args

    with warnings.catch_warnings():
        warnings.simplefilter("always")
        with pytest.raises(SystemExit):
            parse_args(["--cc", "finance-team"])
