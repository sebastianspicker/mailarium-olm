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


class TestCmdAnalytics:
    def test_analytics_stats(self, capsys):
        retriever = _make_retriever()
        args = argparse.Namespace(analytics_action="stats")
        with pytest.raises(SystemExit) as exc_info:
            _cmd_analytics(args, retriever)
        assert exc_info.value.code == 0
        output = capsys.readouterr().out
        parsed = json.loads(output)
        assert parsed["total_emails"] == 100

    def test_analytics_senders(self, capsys):
        retriever = _make_retriever()
        args = argparse.Namespace(analytics_action="senders", limit=10)
        with pytest.raises(SystemExit) as exc_info:
            _cmd_analytics(args, retriever)
        assert exc_info.value.code == 0
        output = capsys.readouterr().out
        assert "Alice" in output
        assert "Bob" in output
        retriever.list_senders.assert_called_once_with(10)

    def test_analytics_senders_default_limit(self, capsys):
        retriever = _make_retriever()
        args = argparse.Namespace(analytics_action="senders")
        # No 'limit' attribute -> getattr defaults to 30
        with pytest.raises(SystemExit) as exc_info:
            _cmd_analytics(args, retriever)
        assert exc_info.value.code == 0
        retriever.list_senders.assert_called_once_with(30)

    def test_analytics_suggest(self):
        retriever = _make_retriever()
        args = argparse.Namespace(analytics_action="suggest")
        with patch("src.cli_commands._run_suggest") as mock_fn:
            with pytest.raises(SystemExit) as exc_info:
                _cmd_analytics(args, retriever)
            assert exc_info.value.code == 0
            mock_fn.assert_called_once()

    def test_analytics_contacts(self):
        retriever = _make_retriever()
        args = argparse.Namespace(
            analytics_action="contacts",
            email_address="employee@example.test",
        )
        mock_db = MagicMock()
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            with patch("src.cli_commands._run_top_contacts") as mock_fn:
                with pytest.raises(SystemExit) as exc_info:
                    _cmd_analytics(args, retriever)
                assert exc_info.value.code == 0
                mock_fn.assert_called_once_with(mock_db, "employee@example.test")

    def test_analytics_volume(self):
        retriever = _make_retriever()
        args = argparse.Namespace(
            analytics_action="volume",
            period="week",
        )
        mock_db = MagicMock()
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            with patch("src.cli_commands._run_volume") as mock_fn:
                with pytest.raises(SystemExit) as exc_info:
                    _cmd_analytics(args, retriever)
                assert exc_info.value.code == 0
                mock_fn.assert_called_once_with(mock_db, "week")

    def test_analytics_entities(self):
        retriever = _make_retriever()
        args = argparse.Namespace(
            analytics_action="entities",
            entity_type="organization",
        )
        mock_db = MagicMock()
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            with patch("src.cli_commands._run_entities") as mock_fn:
                with pytest.raises(SystemExit) as exc_info:
                    _cmd_analytics(args, retriever)
                assert exc_info.value.code == 0
                mock_fn.assert_called_once_with(mock_db, "organization")

    def test_analytics_heatmap(self):
        retriever = _make_retriever()
        args = argparse.Namespace(analytics_action="heatmap")
        mock_db = MagicMock()
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            with patch("src.cli_commands._run_heatmap") as mock_fn:
                with pytest.raises(SystemExit) as exc_info:
                    _cmd_analytics(args, retriever)
                assert exc_info.value.code == 0
                mock_fn.assert_called_once_with(mock_db)

    def test_analytics_response_times(self):
        retriever = _make_retriever()
        args = argparse.Namespace(analytics_action="response-times")
        mock_db = MagicMock()
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            with patch("src.cli_commands._run_response_times") as mock_fn:
                with pytest.raises(SystemExit) as exc_info:
                    _cmd_analytics(args, retriever)
                assert exc_info.value.code == 0
                mock_fn.assert_called_once_with(mock_db)

    def test_analytics_no_action(self, capsys):
        retriever = _make_retriever()
        args = argparse.Namespace(analytics_action=None)
        with pytest.raises(SystemExit) as exc_info:
            _cmd_analytics(args, retriever)
        assert exc_info.value.code == 2
        output = capsys.readouterr().out
        assert "Usage:" in output


class TestRunAnalyticsCommand:
    def test_legacy_top_contacts(self):
        from src.cli import _run_analytics_command

        mock_db = MagicMock()
        args = argparse.Namespace(
            top_contacts="employee@example.test",
            volume=None,
            entities=None,
            heatmap=False,
            response_times=False,
        )
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            with patch("src.cli_commands._run_top_contacts") as mock_fn:
                _run_analytics_command(args)
                mock_fn.assert_called_once_with(mock_db, "employee@example.test")

    def test_legacy_volume(self):
        from src.cli import _run_analytics_command

        mock_db = MagicMock()
        args = argparse.Namespace(
            top_contacts=None,
            volume="week",
            entities=None,
            heatmap=False,
            response_times=False,
        )
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            with patch("src.cli_commands._run_volume") as mock_fn:
                _run_analytics_command(args)
                mock_fn.assert_called_once_with(mock_db, "week")

    def test_legacy_entities_all(self):
        from src.cli import _run_analytics_command

        mock_db = MagicMock()
        args = argparse.Namespace(
            top_contacts=None,
            volume=None,
            entities="all",
            heatmap=False,
            response_times=False,
        )
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            with patch("src.cli_commands._run_entities") as mock_fn:
                _run_analytics_command(args)
                mock_fn.assert_called_once_with(mock_db, None)

    def test_legacy_entities_with_type(self):
        from src.cli import _run_analytics_command

        mock_db = MagicMock()
        args = argparse.Namespace(
            top_contacts=None,
            volume=None,
            entities="organization",
            heatmap=False,
            response_times=False,
        )
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            with patch("src.cli_commands._run_entities") as mock_fn:
                _run_analytics_command(args)
                mock_fn.assert_called_once_with(mock_db, "organization")

    def test_legacy_heatmap(self):
        from src.cli import _run_analytics_command

        mock_db = MagicMock()
        args = argparse.Namespace(
            top_contacts=None,
            volume=None,
            entities=None,
            heatmap=True,
            response_times=False,
        )
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            with patch("src.cli_commands._run_heatmap") as mock_fn:
                _run_analytics_command(args)
                mock_fn.assert_called_once_with(mock_db)

    def test_legacy_response_times(self):
        from src.cli import _run_analytics_command

        mock_db = MagicMock()
        args = argparse.Namespace(
            top_contacts=None,
            volume=None,
            entities=None,
            heatmap=False,
            response_times=True,
        )
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            with patch("src.cli_commands._run_response_times") as mock_fn:
                _run_analytics_command(args)
                mock_fn.assert_called_once_with(mock_db)
