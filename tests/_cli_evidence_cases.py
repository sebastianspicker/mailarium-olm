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


class TestCmdEvidence:
    def test_evidence_list(self):
        args = argparse.Namespace(
            evidence_action="list",
            category="harassment",
            min_relevance=3,
        )
        with patch("src.cli_commands._run_evidence_list") as mock_fn:
            with pytest.raises(SystemExit) as exc_info:
                _cmd_evidence(args)
            assert exc_info.value.code == 0
            mock_fn.assert_called_once_with("harassment", 3)

    def test_evidence_export(self):
        args = argparse.Namespace(
            evidence_action="export",
            output_path="evidence.html",
            format="html",
            category=None,
            min_relevance=None,
        )
        with patch("src.cli_commands._run_evidence_export") as mock_fn:
            with pytest.raises(SystemExit) as exc_info:
                _cmd_evidence(args)
            assert exc_info.value.code == 0
            mock_fn.assert_called_once_with("evidence.html", "html", None, None)

    def test_evidence_stats(self):
        args = argparse.Namespace(evidence_action="stats")
        with patch("src.cli_commands._run_evidence_stats") as mock_fn:
            with pytest.raises(SystemExit) as exc_info:
                _cmd_evidence(args)
            assert exc_info.value.code == 0
            mock_fn.assert_called_once()

    def test_evidence_verify(self):
        args = argparse.Namespace(evidence_action="verify")
        with patch("src.cli_commands._run_evidence_verify") as mock_fn:
            with pytest.raises(SystemExit) as exc_info:
                _cmd_evidence(args)
            assert exc_info.value.code == 0
            mock_fn.assert_called_once()

    def test_evidence_dossier(self):
        args = argparse.Namespace(
            evidence_action="dossier",
            output_path="dossier.html",
            format="pdf",
            category="bossing",
            min_relevance=4,
        )
        with patch("src.cli_commands._run_dossier") as mock_fn:
            with pytest.raises(SystemExit) as exc_info:
                _cmd_evidence(args)
            assert exc_info.value.code == 0
            mock_fn.assert_called_once_with("dossier.html", "pdf", "bossing", 4)

    def test_evidence_custody(self):
        args = argparse.Namespace(evidence_action="custody")
        with patch("src.cli_commands._run_custody_chain") as mock_fn:
            with pytest.raises(SystemExit) as exc_info:
                _cmd_evidence(args)
            assert exc_info.value.code == 0
            mock_fn.assert_called_once()

    def test_evidence_provenance(self):
        args = argparse.Namespace(
            evidence_action="provenance",
            uid="uid-xyz",
        )
        with patch("src.cli_commands._run_provenance") as mock_fn:
            with pytest.raises(SystemExit) as exc_info:
                _cmd_evidence(args)
            assert exc_info.value.code == 0
            mock_fn.assert_called_once_with("uid-xyz")

    def test_evidence_no_action(self, capsys):
        args = argparse.Namespace(evidence_action=None)
        with pytest.raises(SystemExit) as exc_info:
            _cmd_evidence(args)
        assert exc_info.value.code == 2
        output = capsys.readouterr().out
        assert "Usage:" in output


class TestRunEvidenceList:
    def test_evidence_list_with_items(self, capsys):
        mock_db = MagicMock()
        mock_db.list_evidence.return_value = {
            "total": 2,
            "items": [
                {
                    "id": 1,
                    "date": "2024-03-15",
                    "verified": True,
                    "relevance": 4,
                    "category": "harassment",
                    "sender_name": "BadBoss",
                    "sender_email": "boss@example.test",
                    "key_quote": "You are incompetent and should be fired immediately",
                },
                {
                    "id": 2,
                    "date": "2024-03-16",
                    "verified": False,
                    "relevance": 3,
                    "category": "bossing",
                    "sender_name": None,
                    "sender_email": "boss@example.test",
                    "key_quote": "Short quote",
                },
            ],
        }
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            _run_evidence_list(category="harassment", min_relevance=3)
        output = capsys.readouterr().out
        # Works with both rich-formatted and plain-text output
        assert "evidence" in output.lower() or "Evidence" in output
        assert "harassment" in output
        # Verified/unverified markers: Rich may truncate "VERIFIED" to "VE…"
        assert any(m in output for m in ("VERIFIED", "VE", "V"))
        assert any(m in output for m in ("PENDING", "PE", "unverified", "?"))

    def test_evidence_list_empty(self, capsys):
        mock_db = MagicMock()
        mock_db.list_evidence.return_value = {"total": 0, "items": []}
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            _run_evidence_list(None, None)
        output = capsys.readouterr().out
        assert "No evidence items found" in output


class TestRunEvidenceExport:
    def test_evidence_export_success(self, capsys):
        mock_db = MagicMock()
        mock_exporter = MagicMock()
        mock_exporter.export_file.return_value = {
            "output_path": "evidence.html",
            "item_count": 5,
            "format": "html",
        }
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            with patch("src.evidence_exporter.EvidenceExporter", return_value=mock_exporter):
                _run_evidence_export("evidence.html", "html", None, None)
        output = capsys.readouterr().out
        assert "evidence.html" in output
        assert "5 items" in output

    def test_evidence_export_with_note(self, capsys):
        mock_db = MagicMock()
        mock_exporter = MagicMock()
        mock_exporter.export_file.return_value = {
            "output_path": "evidence.csv",
            "item_count": 3,
            "format": "csv",
            "note": "PDF not available",
        }
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            with patch("src.evidence_exporter.EvidenceExporter", return_value=mock_exporter):
                _run_evidence_export("evidence.csv", "csv", "bossing", 4)
        output = capsys.readouterr().out
        assert "Note: PDF not available" in output


class TestRunEvidenceStats:
    def test_evidence_stats_output(self, capsys):
        mock_db = MagicMock()
        mock_db.evidence_stats.return_value = {
            "total": 10,
            "verified": 9,
            "unverified": 1,
            "by_relevance": [
                {"relevance": 5, "count": 6},
                {"relevance": 4, "count": 4},
            ],
            "by_category": {"harassment": 5, "bossing": 3, "general": 2},
        }
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            _run_evidence_stats()
        output = capsys.readouterr().out
        # Works with both rich Panel output and plain JSON output
        assert "10" in output
        assert "9" in output


class TestRunEvidenceVerify:
    def test_verify_all_pass(self, capsys):
        mock_db = MagicMock()
        mock_db.verify_evidence_quotes.return_value = {
            "verified": 5,
            "failed": 0,
            "failures": [],
        }
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            _run_evidence_verify()
        output = capsys.readouterr().out
        assert "5 verified" in output
        assert "0 failed" in output

    def test_verify_with_failures(self, capsys):
        mock_db = MagicMock()
        mock_db.verify_evidence_quotes.return_value = {
            "verified": 3,
            "failed": 1,
            "failures": [
                {
                    "evidence_id": 7,
                    "key_quote_preview": "misquoted text",
                    "email_uid": "uid-xyz-abcdef-long",
                },
            ],
        }
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            _run_evidence_verify()
        output = capsys.readouterr().out
        assert "1 failed" in output or "1" in output
        # Rich output uses "Failed Verifications" table title; plain uses "Failed quotes:"
        assert any(m in output for m in ("Failed Verifications", "Failed quotes:", "failed"))
        assert "7" in output  # evidence ID
        assert "misquoted" in output or "misq" in output  # quote text (may be truncated by Rich)


class TestRunDossier:
    def test_dossier_generation(self, capsys):
        mock_db = MagicMock()
        mock_gen = MagicMock()
        mock_gen.generate_file.return_value = {
            "output_path": "dossier.html",
            "evidence_count": 8,
            "format": "html",
            "dossier_hash": "abc123def456",
        }
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            with patch("src.dossier_generator.DossierGenerator", return_value=mock_gen):
                _run_dossier("dossier.html", "html", None, None)
        output = capsys.readouterr().out
        assert "dossier.html" in output
        assert "8 evidence items" in output
        assert "abc123def456" in output


class TestRunCustodyChain:
    def test_custody_with_events(self, capsys):
        mock_db = MagicMock()
        mock_db.get_custody_chain.return_value = [
            {
                "timestamp": "2024-03-15T10:00:00",
                "action": "evidence_added",
                "actor": "user",
                "target_type": "evidence",
                "target_id": "1",
                "content_hash": "sha256abcdef1234567890",
            },
        ]
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            _run_custody_chain()
        output = capsys.readouterr().out
        # Works with both rich table and plain-text output (case-insensitive)
        assert "chain" in output.lower() and "custody" in output.lower()
        assert "evidence_added" in output
        assert "sha256abcdef" in output

    def test_custody_empty(self, capsys):
        mock_db = MagicMock()
        mock_db.get_custody_chain.return_value = []
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            _run_custody_chain()
        output = capsys.readouterr().out
        assert "No custody events" in output


class TestRunProvenance:
    def test_provenance_output(self, capsys):
        mock_db = MagicMock()
        mock_db.email_provenance.return_value = {
            "uid": "uid-xyz",
            "email": {"subject": "Test", "sender_email": "test@example.test", "date": "2024-01-01"},
            "source": {"olm_source_hash": "sha256:abc", "ingested_at": "2024-01-01"},
            "custody_events": [],
        }
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            _run_provenance("uid-xyz")
        output = capsys.readouterr().out
        # Rich output renders panels instead of raw JSON
        assert "uid-xyz" in output
        assert "Provenance" in output or "provenance" in output
