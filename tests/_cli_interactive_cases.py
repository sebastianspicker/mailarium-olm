# ruff: noqa: F401,I001
"""Tests for CLI command handler functions (_cmd_* and helpers).

These tests exercise the uncovered handler logic in src/cli.py by:
- Constructing argparse.Namespace objects directly
- Mocking EmailRetriever and EmailDatabase
- Capturing stdout/stderr with capsys
- Verifying that the correct branches execute and produce output
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from src.cli import (
    _cmd_admin,
    _cmd_analytics,
    _cmd_browse,
    _cmd_evidence,
    _cmd_export,
    _cmd_search,
    _cmd_training,
    _interactive_action,
    _print_sender_lines,
    _render_interactive_intro,
    _render_results_table,
    _render_senders,
    _render_stats,
    _run_browse,
    _run_custody_chain,
    _run_dossier,
    _run_evidence_export,
    _run_evidence_list,
    _run_evidence_stats,
    _run_evidence_verify,
    _run_export_email,
    _run_export_thread,
    _run_fine_tune,
    _run_generate_training_data,
    _run_provenance,
    resolve_output_format,
    run_single_query,
)

# ── Fake SearchResult ────────────────────────────────────────────────

from .helpers.cli_fakes import _FakeSearchResult, _make_result, _make_retriever


class TestInteractiveAction:
    def test_empty_string(self):
        assert _interactive_action("") == "empty"
        assert _interactive_action("   ") == "empty"

    def test_quit_variants(self):
        assert _interactive_action("quit") == "quit"
        assert _interactive_action("exit") == "quit"
        assert _interactive_action("q") == "quit"
        assert _interactive_action("  QUIT  ") == "quit"

    def test_stats(self):
        assert _interactive_action("stats") == "stats"
        assert _interactive_action("  Stats  ") == "stats"

    def test_senders(self):
        assert _interactive_action("senders") == "senders"
        assert _interactive_action("  SENDERS  ") == "senders"

    def test_regular_query(self):
        assert _interactive_action("find invoices") == "search"
        assert _interactive_action("hello world") == "search"


class TestRenderHelpers:
    def test_render_stats(self):
        console = MagicMock()
        retriever = _make_retriever()
        _render_stats(console, retriever)
        retriever.stats.assert_called_once()
        # Now uses Panel + Table instead of print_json
        assert console.print.call_count >= 1

    def test_render_senders(self):
        console = MagicMock()
        retriever = _make_retriever()
        _render_senders(console, retriever)
        retriever.list_senders.assert_called_once_with(30)
        # _print_sender_lines is called (uses its own Console when rich is available)

    def test_render_interactive_intro(self):
        console = MagicMock()
        panel_cls = MagicMock()
        retriever = _make_retriever()
        _render_interactive_intro(console, panel_cls, retriever)
        retriever.stats.assert_called_once()
        panel_cls.assert_called_once()
        console.print.assert_called_once()

    def test_render_results_table(self):
        console = MagicMock()
        table_cls = MagicMock()
        results = [_make_result(), _make_result(uid="uid-002", subject="Second")]
        _render_results_table(console, table_cls, results)
        table_instance = table_cls.return_value
        assert table_instance.add_column.call_count == 6  # #, Score, Date, Sender, Subject, Folder
        assert table_instance.add_row.call_count == 2
        console.print.assert_called_once_with(table_instance)

    def test_render_results_table_truncates_at_10(self):
        console = MagicMock()
        table_cls = MagicMock()
        results = [_make_result(uid=f"uid-{i:03d}") for i in range(15)]
        _render_results_table(console, table_cls, results)
        table_instance = table_cls.return_value
        # Should only render first 10
        assert table_instance.add_row.call_count == 10


class TestMainDispatch:
    def test_main_search_dispatch(self):
        """main() dispatches to _cmd_search for 'search' subcommand."""
        from src.cli import main

        mock_retriever = _make_retriever(results=[_make_result()])
        with patch("src.cli.parse_args") as mock_parse:
            mock_parse.return_value = argparse.Namespace(
                subcommand="search",
                log_level=None,
                chromadb_path=None,
                sqlite_path=None,
                query="test",
                format=None,
                json=False,
                top_k=10,
                sender=None,
                subject=None,
                folder=None,
                cc=None,
                to=None,
                bcc=None,
                has_attachments=None,
                priority=None,
                email_type=None,
                date_from=None,
                date_to=None,
                min_score=None,
                rerank=False,
                hybrid=False,
                topic=None,
                cluster_id=None,
                expand_query=False,
            )
            with patch("src.cli.configure_logging"):
                with patch("src.cli.EmailRetriever", return_value=mock_retriever, create=True):
                    with patch("src.retriever.EmailRetriever", return_value=mock_retriever):
                        with pytest.raises(SystemExit) as exc_info:
                            main(["search", "test"])
                        assert exc_info.value.code == 0

    def test_main_analytics_dispatch(self, capsys):
        """main() dispatches to _cmd_analytics for 'analytics' subcommand."""
        from src.cli import main

        mock_retriever = _make_retriever()
        with patch("src.cli.parse_args") as mock_parse:
            mock_parse.return_value = argparse.Namespace(
                subcommand="analytics",
                log_level=None,
                chromadb_path=None,
                sqlite_path=None,
                analytics_action="stats",
            )
            with patch("src.cli.configure_logging"):
                with patch("src.retriever.EmailRetriever", return_value=mock_retriever):
                    with pytest.raises(SystemExit) as exc_info:
                        main(["analytics", "stats"])
                    assert exc_info.value.code == 0
        output = capsys.readouterr().out
        assert "total_emails" in output

    def test_main_admin_dispatch(self, capsys):
        """main() dispatches to _cmd_admin for 'admin' subcommand."""
        from src.cli import main

        mock_retriever = _make_retriever()
        with patch("src.cli.parse_args") as mock_parse:
            mock_parse.return_value = argparse.Namespace(
                subcommand="admin",
                log_level=None,
                chromadb_path=None,
                sqlite_path=None,
                admin_action="reset-index",
                yes=True,
            )
            with patch("src.cli.configure_logging"):
                with patch("src.retriever.EmailRetriever", return_value=mock_retriever):
                    with pytest.raises(SystemExit) as exc_info:
                        main(["admin", "reset-index", "--yes"])
                    assert exc_info.value.code == 0
        output = capsys.readouterr().out
        assert "Index has been reset" in output

    def test_main_sets_sqlite_override(self):
        """main() forwards a custom SQLite path to the DB-backed CLI layer."""
        from src.cli import main

        mock_retriever = _make_retriever(results=[_make_result()])
        with patch("src.cli.parse_args") as mock_parse:
            mock_parse.return_value = argparse.Namespace(
                subcommand="search",
                log_level=None,
                chromadb_path=None,
                sqlite_path="/tmp/custom-email.db",
                query="test",
                format=None,
                json=False,
                top_k=10,
                sender=None,
                subject=None,
                folder=None,
                cc=None,
                to=None,
                bcc=None,
                has_attachments=None,
                priority=None,
                email_type=None,
                date_from=None,
                date_to=None,
                min_score=None,
                rerank=False,
                hybrid=False,
                topic=None,
                cluster_id=None,
                expand_query=False,
            )
            with (
                patch("src.cli.configure_logging"),
                patch("src.cli.set_cli_sqlite_path_override") as mock_set_sqlite,
                patch("src.cli.EmailRetriever", return_value=mock_retriever, create=True),
                patch("src.retriever.EmailRetriever", return_value=mock_retriever),
                pytest.raises(SystemExit),
            ):
                main(["search", "test"])

        mock_set_sqlite.assert_called_once_with("/tmp/custom-email.db")
