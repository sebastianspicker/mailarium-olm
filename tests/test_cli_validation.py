import pytest


def test_cli_rejects_non_positive_top_k():
    from src.cli import parse_args

    with pytest.raises(SystemExit):
        parse_args(["--query", "budget", "--top-k", "0"])


def test_cli_rejects_negative_list_senders():
    from src.cli import parse_args

    with pytest.raises(SystemExit):
        parse_args(["--list-senders", "-1"])


def test_cli_rejects_zero_list_senders():
    from src.cli import parse_args

    with pytest.raises(SystemExit):
        parse_args(["--list-senders", "0"])


def test_cli_rejects_too_large_top_k():
    from src.cli import parse_args

    with pytest.raises(SystemExit):
        parse_args(["--query", "budget", "--top-k", "1001"])


def test_cli_rejects_multiple_operational_modes():
    from src.cli import parse_args

    with pytest.raises(SystemExit):
        parse_args(["--stats", "--list-senders", "10"])


def test_cli_rejects_query_with_operational_mode():
    from src.cli import parse_args

    with pytest.raises(SystemExit):
        parse_args(["--query", "budget", "--stats"])


def test_cli_rejects_format_without_query():
    from src.cli import parse_args

    with pytest.raises(SystemExit):
        parse_args(["--format", "json"])


def test_cli_rejects_json_without_query():
    from src.cli import parse_args

    with pytest.raises(SystemExit):
        parse_args(["--json"])


def test_cli_rejects_combining_json_and_format():
    from src.cli import parse_args

    with pytest.raises(SystemExit):
        parse_args(["--query", "budget", "--json", "--format", "text"])


def test_cli_rejects_subject_without_query():
    from src.cli import parse_args

    with pytest.raises(SystemExit):
        parse_args(["--subject", "approval"])


def test_cli_rejects_folder_without_query():
    from src.cli import parse_args

    with pytest.raises(SystemExit):
        parse_args(["--folder", "inbox"])


def test_cli_rejects_min_score_without_query():
    from src.cli import parse_args

    with pytest.raises(SystemExit):
        parse_args(["--min-score", "0.8"])


def test_cli_rejects_invalid_min_score_range():
    from src.cli import parse_args

    with pytest.raises(SystemExit):
        parse_args(["--query", "budget", "--min-score", "1.5"])
