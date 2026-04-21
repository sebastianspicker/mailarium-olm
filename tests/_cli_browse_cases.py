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


class TestCmdBrowse:
    def test_cmd_browse_calls_run_browse(self):
        args = argparse.Namespace(
            page=1,
            page_size=20,
            folder=None,
            sender=None,
        )
        with patch("src.cli_commands._run_browse") as mock_browse:
            with pytest.raises(SystemExit) as exc_info:
                _cmd_browse(args)
            assert exc_info.value.code == 0
            mock_browse.assert_called_once_with(
                offset=0,
                limit=20,
                folder=None,
                sender=None,
            )

    def test_cmd_browse_page_2(self):
        args = argparse.Namespace(
            page=2,
            page_size=10,
            folder="inbox",
            sender="alice",
        )
        with patch("src.cli_commands._run_browse") as mock_browse:
            with pytest.raises(SystemExit):
                _cmd_browse(args)
            mock_browse.assert_called_once_with(
                offset=10,
                limit=10,
                folder="inbox",
                sender="alice",
            )

    def test_cmd_browse_caps_page_size_at_50(self):
        args = argparse.Namespace(
            page=1,
            page_size=100,
            folder=None,
            sender=None,
        )
        with patch("src.cli_commands._run_browse") as mock_browse:
            with pytest.raises(SystemExit):
                _cmd_browse(args)
            mock_browse.assert_called_once_with(
                offset=0,
                limit=50,
                folder=None,
                sender=None,
            )


class TestRunBrowse:
    def test_browse_with_results(self, capsys):
        mock_db = MagicMock()
        mock_db.list_emails_paginated.return_value = {
            "total": 2,
            "emails": [
                {
                    "subject": "Email One",
                    "sender_email": "employee@example.test",
                    "date": "2024-06-15T10:00:00",
                    "uid": "uid-001-abcdef",
                    "conversation_id": "conv-001-abcdefgh",
                },
                {
                    "subject": "Email Two",
                    "sender_email": "bob@example.com",
                    "date": "2024-06-14T09:00:00",
                    "uid": "uid-002-abcdef",
                    "conversation_id": "conv-002-abcdefgh",
                },
            ],
        }
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            _run_browse(offset=0, limit=20)
        output = capsys.readouterr().out
        assert "page 1" in output
        assert "Email One" in output
        assert "Email Two" in output
        assert "employee@example.test" in output

    def test_browse_empty(self, capsys):
        mock_db = MagicMock()
        mock_db.list_emails_paginated.return_value = {
            "total": 0,
            "emails": [],
        }
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            _run_browse(offset=0, limit=20)
        output = capsys.readouterr().out
        assert "No emails found" in output

    def test_browse_shows_next_page_hint(self, capsys):
        mock_db = MagicMock()
        mock_db.list_emails_paginated.return_value = {
            "total": 50,
            "emails": [
                {
                    "subject": f"Email {i}",
                    "sender_email": "a@example.test",
                    "date": "2024-01-01",
                    "uid": f"uid-{i:03d}-abcdef",
                    "conversation_id": f"conv-{i:03d}",
                }
                for i in range(20)
            ],
        }
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            _run_browse(offset=0, limit=20)
        output = capsys.readouterr().out
        assert "Next page:" in output

    def test_browse_with_folder_and_sender(self):
        mock_db = MagicMock()
        mock_db.list_emails_paginated.return_value = {
            "total": 0,
            "emails": [],
        }
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            _run_browse(offset=0, limit=10, folder="inbox", sender="alice")
        mock_db.list_emails_paginated.assert_called_once_with(
            offset=0,
            limit=10,
            folder="inbox",
            sender="alice",
        )
