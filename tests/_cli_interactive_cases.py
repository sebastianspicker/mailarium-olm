# ruff: noqa: I001
"""Interactive CLI action selection and compact renderer behavior."""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest

from mailarium.cli import (
    _interactive_action,
    _render_interactive_intro,
    _render_results_table,
    _render_senders,
    _render_stats,
)

# ── Fake SearchResult ────────────────────────────────────────────────

from .helpers.cli_fakes import _make_result, _make_retriever, _search_args


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
        from mailarium.cli import main

        mock_retriever = _make_retriever(results=[_make_result()])
        with patch("mailarium.cli.parse_args") as mock_parse:
            mock_parse.return_value = _search_args()
            with patch("mailarium.cli.configure_logging"):
                with patch("mailarium.cli.EmailRetriever", return_value=mock_retriever, create=True):
                    with patch("mailarium.retriever.EmailRetriever", return_value=mock_retriever):
                        with pytest.raises(SystemExit) as exc_info:
                            main(["search", "test"])
                        assert exc_info.value.code == 0

    def test_main_analytics_dispatch(self, capsys):
        """main() dispatches to _cmd_analytics for 'analytics' subcommand."""
        from mailarium.cli import main

        mock_retriever = _make_retriever()
        with patch("mailarium.cli.parse_args") as mock_parse:
            mock_parse.return_value = argparse.Namespace(
                subcommand="analytics",
                log_level=None,
                vector_index_path=None,
                sqlite_path=None,
                analytics_action="stats",
            )
            with patch("mailarium.cli.configure_logging"):
                with patch("mailarium.retriever.EmailRetriever", return_value=mock_retriever):
                    with pytest.raises(SystemExit) as exc_info:
                        main(["analytics", "stats"])
                    assert exc_info.value.code == 0
        output = capsys.readouterr().out
        assert "total_emails" in output

    def test_main_admin_dispatch(self, capsys):
        """main() dispatches to _cmd_admin for 'admin' subcommand."""
        from mailarium.cli import main

        mock_retriever = _make_retriever()
        with patch("mailarium.cli.parse_args") as mock_parse:
            mock_parse.return_value = argparse.Namespace(
                subcommand="admin",
                log_level=None,
                vector_index_path=None,
                sqlite_path=None,
                admin_action="reset-index",
                yes=True,
            )
            with patch("mailarium.cli.configure_logging"):
                with patch("mailarium.retriever.EmailRetriever", return_value=mock_retriever):
                    with pytest.raises(SystemExit) as exc_info:
                        main(["admin", "reset-index", "--yes"])
                    assert exc_info.value.code == 0
        output = capsys.readouterr().out
        assert "Index has been reset" in output

    def test_main_sets_sqlite_override(self, tmp_path):
        """main() forwards a custom SQLite path to the DB-backed CLI layer."""
        from mailarium.cli import main

        custom_db = str(tmp_path / "custom-email.db")
        mock_retriever = _make_retriever(results=[_make_result()])
        with patch("mailarium.cli.parse_args") as mock_parse:
            mock_parse.return_value = _search_args(sqlite_path=custom_db)
            with (
                patch("mailarium.cli.configure_logging"),
                patch("mailarium.cli.set_cli_sqlite_path_override") as mock_set_sqlite,
                patch("mailarium.cli.EmailRetriever", return_value=mock_retriever, create=True),
                patch("mailarium.retriever.EmailRetriever", return_value=mock_retriever),
                pytest.raises(SystemExit),
            ):
                main(["search", "test"])

        mock_set_sqlite.assert_called_once_with(custom_db)
