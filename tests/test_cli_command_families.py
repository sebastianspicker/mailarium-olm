"""Structural tests for CLI command-family extraction."""

from __future__ import annotations

from unittest.mock import patch

from src import cli_commands


def test_admin_wrapper_delegates_to_compat_module() -> None:
    args = object()
    retriever = object()
    with patch("src.cli_commands_compat.cmd_admin_impl") as mock_impl:
        cli_commands._cmd_admin(args, retriever)
    mock_impl.assert_called_once_with(args, retriever)


def test_legacy_wrapper_delegates_to_compat_module() -> None:
    args = object()
    retriever = object()
    with patch("src.cli_commands_compat.cmd_legacy_impl") as mock_impl:
        cli_commands._cmd_legacy(args, retriever)
    mock_impl.assert_called_once()


def test_get_email_db_wrapper_delegates_to_compat_module() -> None:
    with patch("src.cli_commands_compat.get_email_db_impl", return_value="db") as mock_impl:
        assert cli_commands._get_email_db() == "db"
    mock_impl.assert_called_once()


def test_legacy_analytics_wrapper_delegates_to_compat_module() -> None:
    args = object()
    with patch("src.cli_commands_compat.run_analytics_command_impl") as mock_impl:
        cli_commands._run_analytics_command(args)
    mock_impl.assert_called_once()


def test_export_wrapper_delegates_to_family_module() -> None:
    with patch("src.cli_commands_export.run_export_thread_impl") as mock_impl:
        cli_commands._run_export_thread("conv-123", "html", "out.html")
    mock_impl.assert_called_once_with(cli_commands._get_email_db, "conv-123", "html", "out.html")


def test_search_wrapper_delegates_to_family_module() -> None:
    retriever = object()
    with patch("src.cli_commands_search.run_single_query_impl", return_value=7) as mock_impl:
        code = cli_commands.run_single_query(retriever, "budget")
    assert code == 7
    mock_impl.assert_called_once()


def test_browse_wrapper_delegates_to_family_module() -> None:
    with patch("src.cli_commands_search.run_browse_impl") as mock_impl:
        cli_commands._run_browse(offset=40, limit=10, folder="Inbox", sender="employee@example.test")
    mock_impl.assert_called_once_with(
        cli_commands._get_email_db,
        cli_commands.sanitize_untrusted_text,
        offset=40,
        limit=10,
        folder="Inbox",
        sender="employee@example.test",
    )


def test_evidence_wrapper_delegates_to_family_module() -> None:
    with patch("src.cli_commands_evidence.run_evidence_stats_impl") as mock_impl:
        cli_commands._run_evidence_stats()
    mock_impl.assert_called_once_with(cli_commands._get_email_db, cli_commands._print_rich_or_plain)


def test_analytics_wrapper_delegates_to_family_module() -> None:
    with patch("src.cli_commands_analytics.run_suggest_impl") as mock_impl:
        cli_commands._run_suggest()
    mock_impl.assert_called_once_with(cli_commands._get_email_db)


def test_training_wrapper_delegates_to_family_module() -> None:
    with patch("src.cli_commands_training.run_fine_tune_impl") as mock_impl:
        cli_commands._run_fine_tune("data.jsonl", "models/out", 4)
    mock_impl.assert_called_once_with("data.jsonl", "models/out", 4)
