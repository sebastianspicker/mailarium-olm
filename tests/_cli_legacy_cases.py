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


class TestCmdLegacy:
    def test_legacy_reset_index_with_yes(self, capsys):
        from src.cli import _cmd_legacy

        retriever = _make_retriever()
        args = argparse.Namespace(
            reset_index=True,
            yes=True,
            stats=False,
            list_senders=0,
            suggest=False,
            generate_report=None,
            export_network=None,
            export_thread=None,
            export_email=None,
            browse=False,
            evidence_list=False,
            evidence_export=None,
            evidence_stats=False,
            evidence_verify=False,
            dossier=None,
            custody_chain=False,
            provenance=None,
            generate_training_data=None,
            fine_tune=None,
            top_contacts=None,
            volume=None,
            entities=None,
            heatmap=False,
            response_times=False,
            query=None,
            export_format="html",
            output=None,
        )
        with pytest.raises(SystemExit) as exc_info:
            _cmd_legacy(args, retriever)
        assert exc_info.value.code == 0
        retriever.reset_index.assert_called_once()

    def test_legacy_reset_index_without_yes(self, capsys):
        from src.cli import _cmd_legacy

        retriever = _make_retriever()
        args = argparse.Namespace(
            reset_index=True,
            yes=False,
            stats=False,
            list_senders=0,
        )
        with pytest.raises(SystemExit) as exc_info:
            _cmd_legacy(args, retriever)
        assert exc_info.value.code == 2
        output = capsys.readouterr().out
        assert "Refusing to reset" in output

    def test_legacy_stats(self, capsys):
        from src.cli import _cmd_legacy

        retriever = _make_retriever()
        args = argparse.Namespace(
            reset_index=False,
            yes=False,
            stats=True,
            list_senders=0,
        )
        with pytest.raises(SystemExit) as exc_info:
            _cmd_legacy(args, retriever)
        assert exc_info.value.code == 0
        output = capsys.readouterr().out
        parsed = json.loads(output)
        assert parsed["total_emails"] == 100

    def test_legacy_list_senders(self, capsys):
        from src.cli import _cmd_legacy

        retriever = _make_retriever()
        args = argparse.Namespace(
            reset_index=False,
            yes=False,
            stats=False,
            list_senders=15,
            suggest=False,
        )
        with pytest.raises(SystemExit) as exc_info:
            _cmd_legacy(args, retriever)
        assert exc_info.value.code == 0
        retriever.list_senders.assert_called_once_with(15)
        output = capsys.readouterr().out
        assert "Alice" in output

    def test_legacy_suggest(self):
        from src.cli import _cmd_legacy

        retriever = _make_retriever()
        args = argparse.Namespace(
            reset_index=False,
            yes=False,
            stats=False,
            list_senders=0,
            suggest=True,
            generate_report=None,
        )
        with patch("src.cli_commands._run_suggest") as mock_fn:
            with pytest.raises(SystemExit) as exc_info:
                _cmd_legacy(args, retriever)
            assert exc_info.value.code == 0
            mock_fn.assert_called_once()

    def test_legacy_browse(self):
        from src.cli import _cmd_legacy

        retriever = _make_retriever()
        args = argparse.Namespace(
            reset_index=False,
            yes=False,
            stats=False,
            list_senders=0,
            suggest=False,
            generate_report=None,
            export_network=None,
            export_thread=None,
            export_email=None,
            browse=True,
            page=2,
            page_size=10,
            folder="inbox",
            sender="bob",
            evidence_list=False,
        )
        with patch("src.cli_commands._run_browse") as mock_fn:
            with pytest.raises(SystemExit) as exc_info:
                _cmd_legacy(args, retriever)
            assert exc_info.value.code == 0
            mock_fn.assert_called_once_with(
                offset=10,
                limit=10,
                folder="inbox",
                sender="bob",
            )

    def test_legacy_evidence_list(self):
        from src.cli import _cmd_legacy

        retriever = _make_retriever()
        args = argparse.Namespace(
            reset_index=False,
            yes=False,
            stats=False,
            list_senders=0,
            suggest=False,
            generate_report=None,
            export_network=None,
            export_thread=None,
            export_email=None,
            browse=False,
            evidence_list=True,
            category="harassment",
            min_relevance=3,
        )
        with patch("src.cli_commands._run_evidence_list") as mock_fn:
            with pytest.raises(SystemExit) as exc_info:
                _cmd_legacy(args, retriever)
            assert exc_info.value.code == 0
            mock_fn.assert_called_once_with("harassment", 3)

    def test_legacy_query(self, capsys):
        from src.cli import _cmd_legacy

        results = [_make_result()]
        retriever = _make_retriever(results)
        args = argparse.Namespace(
            reset_index=False,
            yes=False,
            stats=False,
            list_senders=0,
            suggest=False,
            generate_report=None,
            export_network=None,
            export_thread=None,
            export_email=None,
            export_format="html",
            output=None,
            browse=False,
            evidence_list=False,
            evidence_export=None,
            evidence_stats=False,
            evidence_verify=False,
            dossier=None,
            custody_chain=False,
            provenance=None,
            generate_training_data=None,
            fine_tune=None,
            fine_tune_output=None,
            fine_tune_epochs=3,
            top_contacts=None,
            volume=None,
            entities=None,
            heatmap=False,
            response_times=False,
            query="test query",
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
        # Need to set collection.count for empty-db check
        retriever.collection = MagicMock()
        retriever.collection.count.return_value = 100
        with pytest.raises(SystemExit) as exc_info:
            _cmd_legacy(args, retriever)
        assert exc_info.value.code == 0
        output = capsys.readouterr().out
        assert "Result 1" in output

    def test_legacy_empty_db(self, capsys):
        from src.cli import _cmd_legacy

        retriever = _make_retriever()
        retriever.collection = MagicMock()
        retriever.collection.count.return_value = 0
        args = argparse.Namespace(
            reset_index=False,
            yes=False,
            stats=False,
            list_senders=0,
            suggest=False,
            generate_report=None,
            export_network=None,
            export_thread=None,
            export_email=None,
            browse=False,
            evidence_list=False,
            evidence_export=None,
            evidence_stats=False,
            evidence_verify=False,
            dossier=None,
            custody_chain=False,
            provenance=None,
            generate_training_data=None,
            fine_tune=None,
            top_contacts=None,
            volume=None,
            entities=None,
            heatmap=False,
            response_times=False,
            query=None,
        )
        with pytest.raises(SystemExit) as exc_info:
            _cmd_legacy(args, retriever)
        assert exc_info.value.code == 1
        output = capsys.readouterr().out
        assert "No emails in database" in output
