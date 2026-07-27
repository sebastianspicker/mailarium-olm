"""CLI email and thread export dispatch, paths, notes, and failure handling."""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest

from mailarium.cli import (
    _cmd_export,
    _run_export_email,
    _run_export_thread,
)

# ── Fake SearchResult ────────────────────────────────────────────────


class TestCmdExport:
    def test_export_thread(self):
        args = argparse.Namespace(
            export_action="thread",
            conversation_id="conv-123",
            format="html",
            output=None,
        )
        with patch("mailarium.cli_commands._run_export_thread") as mock_fn:
            with pytest.raises(SystemExit) as exc_info:
                _cmd_export(args)
            assert exc_info.value.code == 0
            mock_fn.assert_called_once_with("conv-123", "html", None)

    def test_export_email(self, tmp_path):
        args = argparse.Namespace(
            export_action="email",
            uid="uid-abc",
            format="pdf",
            output=str(tmp_path / "out.pdf"),
        )
        with patch("mailarium.cli_commands._run_export_email") as mock_fn:
            with pytest.raises(SystemExit) as exc_info:
                _cmd_export(args)
            assert exc_info.value.code == 0
            mock_fn.assert_called_once_with("uid-abc", "pdf", str(tmp_path / "out.pdf"))

    def test_export_report(self):
        args = argparse.Namespace(
            export_action="report",
            output="my_report.html",
        )
        with patch("mailarium.cli_commands._run_generate_report") as mock_fn:
            with pytest.raises(SystemExit) as exc_info:
                _cmd_export(args)
            assert exc_info.value.code == 0
            mock_fn.assert_called_once_with("my_report.html")

    def test_export_network(self):
        args = argparse.Namespace(
            export_action="network",
            output="net.graphml",
        )
        with patch("mailarium.cli_commands._run_export_network") as mock_fn:
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
    def test_export_thread_with_output_path(self, tmp_path, capsys):
        mock_db = MagicMock()
        mock_exporter = MagicMock()
        thread_path = str(tmp_path / "thread.html")
        mock_exporter.export_thread_file.return_value = {
            "output_path": thread_path,
            "email_count": 5,
        }
        with patch("mailarium.cli_commands._get_email_db", return_value=mock_db):
            with patch("mailarium.email_exporter.EmailExporter", return_value=mock_exporter):
                _run_export_thread("conv-123", "html", thread_path)
        output = capsys.readouterr().out
        assert thread_path in output
        assert "5 emails" in output
        mock_exporter.export_thread_file.assert_called_once_with(
            "conv-123",
            thread_path,
            fmt="html",
        )

    def test_export_thread_default_path(self, capsys):
        mock_db = MagicMock()
        mock_exporter = MagicMock()
        mock_exporter.export_thread_file.return_value = {
            "output_path": "thread_conv-123.html",
            "email_count": 3,
        }
        with patch("mailarium.cli_commands._get_email_db", return_value=mock_db):
            with patch("mailarium.email_exporter.EmailExporter", return_value=mock_exporter):
                _run_export_thread("conv-123", "html", None)
        output = capsys.readouterr().out
        assert "3 emails" in output

    def test_export_thread_error(self, capsys):
        mock_db = MagicMock()
        mock_exporter = MagicMock()
        mock_exporter.export_thread_file.return_value = {
            "error": "Thread not found",
        }
        with patch("mailarium.cli_commands._get_email_db", return_value=mock_db):
            with patch("mailarium.email_exporter.EmailExporter", return_value=mock_exporter):
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
        with patch("mailarium.cli_commands._get_email_db", return_value=mock_db):
            with patch("mailarium.email_exporter.EmailExporter", return_value=mock_exporter):
                _run_export_thread("conv-123", "pdf", "thread.pdf")
        output = capsys.readouterr().out
        assert "Note: PDF generated via fallback" in output


class TestRunExportEmail:
    def test_export_email_with_output_path(self, tmp_path, capsys):
        mock_db = MagicMock()
        mock_exporter = MagicMock()
        email_path = str(tmp_path / "email.html")
        mock_exporter.export_single_file.return_value = {
            "output_path": email_path,
        }
        with patch("mailarium.cli_commands._get_email_db", return_value=mock_db):
            with patch("mailarium.email_exporter.EmailExporter", return_value=mock_exporter):
                _run_export_email("uid-abc", "html", email_path)
        output = capsys.readouterr().out
        assert email_path in output

    def test_export_email_default_path(self, capsys):
        mock_db = MagicMock()
        mock_exporter = MagicMock()
        mock_exporter.export_single_file.return_value = {
            "output_path": "email_uid-abc-long.html",
        }
        with patch("mailarium.cli_commands._get_email_db", return_value=mock_db):
            with patch("mailarium.email_exporter.EmailExporter", return_value=mock_exporter):
                _run_export_email("uid-abc-long-id", "html", None)
        output = capsys.readouterr().out
        assert "email_uid-abc-long.html" in output
        # Verify default path logic - uid[:12]
        call_args = mock_exporter.export_single_file.call_args
        assert call_args[0][1] == "email_uid-abc-long.html"

    def test_export_email_error(self, capsys):
        mock_db = MagicMock()
        mock_exporter = MagicMock()
        mock_exporter.export_single_file.return_value = {
            "error": "Email not found",
        }
        with patch("mailarium.cli_commands._get_email_db", return_value=mock_db):
            with patch("mailarium.email_exporter.EmailExporter", return_value=mock_exporter):
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
        with patch("mailarium.cli_commands._get_email_db", return_value=mock_db):
            with patch("mailarium.email_exporter.EmailExporter", return_value=mock_exporter):
                _run_export_email("uid-abc", "pdf", "email.pdf")
        output = capsys.readouterr().out
        assert "Note: Converted from HTML" in output
