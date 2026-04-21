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


class TestCmdExport:
    def test_export_thread(self):
        args = argparse.Namespace(
            export_action="thread",
            conversation_id="conv-123",
            format="html",
            output=None,
        )
        with patch("src.cli_commands._run_export_thread") as mock_fn:
            with pytest.raises(SystemExit) as exc_info:
                _cmd_export(args)
            assert exc_info.value.code == 0
            mock_fn.assert_called_once_with("conv-123", "html", None)

    def test_export_email(self):
        args = argparse.Namespace(
            export_action="email",
            uid="uid-abc",
            format="pdf",
            output="/tmp/out.pdf",
        )
        with patch("src.cli_commands._run_export_email") as mock_fn:
            with pytest.raises(SystemExit) as exc_info:
                _cmd_export(args)
            assert exc_info.value.code == 0
            mock_fn.assert_called_once_with("uid-abc", "pdf", "/tmp/out.pdf")

    def test_export_report(self):
        args = argparse.Namespace(
            export_action="report",
            output="my_report.html",
        )
        with patch("src.cli_commands._run_generate_report") as mock_fn:
            with pytest.raises(SystemExit) as exc_info:
                _cmd_export(args)
            assert exc_info.value.code == 0
            mock_fn.assert_called_once_with("my_report.html")

    def test_export_network(self):
        args = argparse.Namespace(
            export_action="network",
            output="net.graphml",
        )
        with patch("src.cli_commands._run_export_network") as mock_fn:
            with pytest.raises(SystemExit) as exc_info:
                _cmd_export(args)
            assert exc_info.value.code == 0
            mock_fn.assert_called_once_with("net.graphml")

    def test_export_no_action(self, capsys):
        args = argparse.Namespace(export_action=None)
        with pytest.raises(SystemExit) as exc_info:
            _cmd_export(args)
        assert exc_info.value.code == 2
        output = capsys.readouterr().out
        assert "Usage:" in output


class TestRunExportThread:
    def test_export_thread_with_output_path(self, capsys):
        mock_db = MagicMock()
        mock_exporter = MagicMock()
        mock_exporter.export_thread_file.return_value = {
            "output_path": "/tmp/thread.html",
            "email_count": 5,
        }
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            with patch("src.email_exporter.EmailExporter", return_value=mock_exporter):
                _run_export_thread("conv-123", "html", "/tmp/thread.html")
        output = capsys.readouterr().out
        assert "/tmp/thread.html" in output
        assert "5 emails" in output
        mock_exporter.export_thread_file.assert_called_once_with(
            "conv-123",
            "/tmp/thread.html",
            fmt="html",
        )

    def test_export_thread_default_path(self, capsys):
        mock_db = MagicMock()
        mock_exporter = MagicMock()
        mock_exporter.export_thread_file.return_value = {
            "output_path": "thread_conv-123.html",
            "email_count": 3,
        }
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            with patch("src.email_exporter.EmailExporter", return_value=mock_exporter):
                _run_export_thread("conv-123", "html", None)
        output = capsys.readouterr().out
        assert "3 emails" in output

    def test_export_thread_error(self, capsys):
        mock_db = MagicMock()
        mock_exporter = MagicMock()
        mock_exporter.export_thread_file.return_value = {
            "error": "Thread not found",
        }
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            with patch("src.email_exporter.EmailExporter", return_value=mock_exporter):
                with pytest.raises(SystemExit) as exc_info:
                    _run_export_thread("conv-999", "html", None)
                assert exc_info.value.code == 1
        output = capsys.readouterr().out
        assert "Error: Thread not found" in output

    def test_export_thread_with_note(self, capsys):
        mock_db = MagicMock()
        mock_exporter = MagicMock()
        mock_exporter.export_thread_file.return_value = {
            "output_path": "thread.pdf",
            "email_count": 2,
            "note": "PDF generated via fallback",
        }
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            with patch("src.email_exporter.EmailExporter", return_value=mock_exporter):
                _run_export_thread("conv-123", "pdf", "thread.pdf")
        output = capsys.readouterr().out
        assert "Note: PDF generated via fallback" in output


class TestRunExportEmail:
    def test_export_email_with_output_path(self, capsys):
        mock_db = MagicMock()
        mock_exporter = MagicMock()
        mock_exporter.export_single_file.return_value = {
            "output_path": "/tmp/email.html",
        }
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            with patch("src.email_exporter.EmailExporter", return_value=mock_exporter):
                _run_export_email("uid-abc", "html", "/tmp/email.html")
        output = capsys.readouterr().out
        assert "/tmp/email.html" in output

    def test_export_email_default_path(self, capsys):
        mock_db = MagicMock()
        mock_exporter = MagicMock()
        mock_exporter.export_single_file.return_value = {
            "output_path": "email_uid-abc-long.html",
        }
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            with patch("src.email_exporter.EmailExporter", return_value=mock_exporter):
                _run_export_email("uid-abc-long-id", "html", None)
        output = capsys.readouterr().out
        assert "email_uid-abc-long.html" in output
        # Verify default path logic — uid[:12]
        call_args = mock_exporter.export_single_file.call_args
        assert call_args[0][1] == "email_uid-abc-long.html"

    def test_export_email_error(self, capsys):
        mock_db = MagicMock()
        mock_exporter = MagicMock()
        mock_exporter.export_single_file.return_value = {
            "error": "Email not found",
        }
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            with patch("src.email_exporter.EmailExporter", return_value=mock_exporter):
                with pytest.raises(SystemExit) as exc_info:
                    _run_export_email("uid-999", "html", None)
                assert exc_info.value.code == 1
        output = capsys.readouterr().out
        assert "Error: Email not found" in output

    def test_export_email_with_note(self, capsys):
        mock_db = MagicMock()
        mock_exporter = MagicMock()
        mock_exporter.export_single_file.return_value = {
            "output_path": "email.pdf",
            "note": "Converted from HTML",
        }
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            with patch("src.email_exporter.EmailExporter", return_value=mock_exporter):
                _run_export_email("uid-abc", "pdf", "email.pdf")
        output = capsys.readouterr().out
        assert "Note: Converted from HTML" in output
