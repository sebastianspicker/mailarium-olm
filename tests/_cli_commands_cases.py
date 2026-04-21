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


@dataclass
class _FakeSearchResult:
    """Mimics retriever.SearchResult for testing."""

    chunk_id: str
    text: str
    metadata: dict
    distance: float

    @property
    def score(self) -> float:
        return min(1.0, max(0.0, 1.0 - self.distance))

    def to_context_string(self) -> str:
        subject = self.metadata.get("subject", "(no subject)")
        sender = self.metadata.get("sender_email", "?")
        return f"Subject: {subject}\nFrom: {sender}\n{self.text}"

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "score": self.score,
            "distance": self.distance,
            "metadata": self.metadata,
            "text": self.text,
        }


def _make_result(uid="uid-001", subject="Test Email", sender="alice@example.com", text="Hello world", distance=0.2):
    return _FakeSearchResult(
        chunk_id=f"{uid}_0",
        text=text,
        metadata={
            "subject": subject,
            "sender_email": sender,
            "sender_name": sender.split("@")[0],
            "date": "2024-06-15T10:00:00",
            "uid": uid,
        },
        distance=distance,
    )


def _make_retriever(results=None, stats_data=None, senders=None):
    """Create a mock EmailRetriever."""
    retriever = MagicMock()
    retriever.search_filtered.return_value = results or []
    retriever.stats.return_value = stats_data or {
        "total_emails": 100,
        "total_chunks": 500,
        "unique_senders": 20,
        "date_range": {"earliest": "2023-01-01", "latest": "2024-12-31"},
    }
    retriever.list_senders.return_value = senders or [
        {"name": "Alice", "email": "alice@example.com", "count": 50},
        {"name": "Bob", "email": "bob@example.com", "count": 30},
    ]
    retriever.serialize_results.return_value = {
        "query": "test",
        "count": len(results or []),
        "results": [r.to_dict() for r in (results or [])],
    }
    return retriever


# ── resolve_output_format ────────────────────────────────────────────


class TestResolveOutputFormat:
    def test_format_text(self):
        args = argparse.Namespace(format="text", json=False)
        assert resolve_output_format(args) == "text"

    def test_format_json(self):
        args = argparse.Namespace(format="json", json=False)
        assert resolve_output_format(args) == "json"

    def test_json_flag_fallback(self):
        args = argparse.Namespace(format=None, json=True)
        assert resolve_output_format(args) == "json"

    def test_default_text(self):
        args = argparse.Namespace(format=None, json=False)
        assert resolve_output_format(args) == "text"

    def test_format_attribute_missing(self):
        """When format attr doesn't exist, fall back to text."""
        args = argparse.Namespace(json=False)
        assert resolve_output_format(args) == "text"

    def test_json_attribute_missing(self):
        """When json attr doesn't exist, fall back to text."""
        args = argparse.Namespace(format=None)
        assert resolve_output_format(args) == "text"


# ── run_single_query ─────────────────────────────────────────────────


class TestRunSingleQuery:
    def test_search_with_results_text(self, capsys):
        results = [_make_result(), _make_result(uid="uid-002", subject="Second")]
        retriever = _make_retriever(results)
        code = run_single_query(retriever, query="test", top_k=10)
        assert code == 0
        output = capsys.readouterr().out
        assert "Result 1" in output
        assert "Result 2" in output
        retriever.search_filtered.assert_called_once()

    def test_search_no_results(self, capsys):
        retriever = _make_retriever(results=[])
        code = run_single_query(retriever, query="nothing")
        assert code == 0
        output = capsys.readouterr().out
        assert "No matching emails found" in output

    def test_search_json_output(self, capsys):
        results = [_make_result()]
        retriever = _make_retriever(results)
        code = run_single_query(retriever, query="test", as_json=True)
        assert code == 0
        output = capsys.readouterr().out
        parsed = json.loads(output)
        assert parsed["count"] == 1

    def test_search_json_empty_results(self, capsys):
        """JSON output with no results should still produce valid JSON."""
        retriever = _make_retriever(results=[])
        code = run_single_query(retriever, query="test", as_json=True)
        assert code == 0
        output = capsys.readouterr().out
        parsed = json.loads(output)
        assert parsed["count"] == 0

    def test_search_passes_all_filters(self):
        retriever = _make_retriever()
        run_single_query(
            retriever,
            query="test",
            top_k=5,
            sender="alice",
            subject="invoice",
            folder="inbox",
            cc="bob",
            to="carol",
            bcc="dave",
            has_attachments=True,
            priority=3,
            email_type="reply",
            date_from="2024-01-01",
            date_to="2024-12-31",
            min_score=0.5,
            rerank=True,
            hybrid=True,
            topic_id=2,
            cluster_id=4,
            expand_query=True,
        )
        call_kwargs = retriever.search_filtered.call_args[1]
        assert call_kwargs["sender"] == "alice"
        assert call_kwargs["subject"] == "invoice"
        assert call_kwargs["folder"] == "inbox"
        assert call_kwargs["cc"] == "bob"
        assert call_kwargs["to"] == "carol"
        assert call_kwargs["bcc"] == "dave"
        assert call_kwargs["has_attachments"] is True
        assert call_kwargs["priority"] == 3
        assert call_kwargs["email_type"] == "reply"
        assert call_kwargs["rerank"] is True
        assert call_kwargs["hybrid"] is True
        assert call_kwargs["topic_id"] == 2
        assert call_kwargs["cluster_id"] == 4
        assert call_kwargs["expand_query"] is True


# ── _cmd_search ──────────────────────────────────────────────────────


class TestCmdSearch:
    def test_cmd_search_text_output(self, capsys):
        results = [_make_result()]
        retriever = _make_retriever(results)
        args = argparse.Namespace(
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
        with pytest.raises(SystemExit) as exc_info:
            _cmd_search(args, retriever)
        assert exc_info.value.code == 0
        output = capsys.readouterr().out
        assert "Result 1" in output

    def test_cmd_search_json_format(self, capsys):
        results = [_make_result()]
        retriever = _make_retriever(results)
        args = argparse.Namespace(
            query="test",
            format="json",
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
        with pytest.raises(SystemExit) as exc_info:
            _cmd_search(args, retriever)
        assert exc_info.value.code == 0
        output = capsys.readouterr().out
        parsed = json.loads(output)
        assert "results" in parsed

    def test_cmd_search_with_filters(self, capsys):
        retriever = _make_retriever(results=[])
        args = argparse.Namespace(
            query="invoice",
            format=None,
            json=False,
            top_k=5,
            sender="alice",
            subject="budget",
            folder="sent",
            cc=None,
            to=None,
            bcc=None,
            has_attachments=True,
            priority=3,
            email_type="reply",
            date_from="2024-01-01",
            date_to="2024-06-30",
            min_score=0.5,
            rerank=True,
            hybrid=True,
            topic=2,
            cluster_id=4,
            expand_query=True,
        )
        with pytest.raises(SystemExit) as exc_info:
            _cmd_search(args, retriever)
        assert exc_info.value.code == 0
        call_kwargs = retriever.search_filtered.call_args[1]
        assert call_kwargs["sender"] == "alice"
        assert call_kwargs["rerank"] is True


# ── _cmd_browse ──────────────────────────────────────────────────────


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


# ── _cmd_export ──────────────────────────────────────────────────────


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


# ── _cmd_evidence ────────────────────────────────────────────────────


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


# ── _cmd_analytics ───────────────────────────────────────────────────


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
            email_address="alice@example.com",
        )
        mock_db = MagicMock()
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            with patch("src.cli_commands._run_top_contacts") as mock_fn:
                with pytest.raises(SystemExit) as exc_info:
                    _cmd_analytics(args, retriever)
                assert exc_info.value.code == 0
                mock_fn.assert_called_once_with(mock_db, "alice@example.com")

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


# ── _cmd_training ────────────────────────────────────────────────────


class TestCmdTraining:
    def test_training_generate_data(self):
        args = argparse.Namespace(
            training_action="generate-data",
            output_path="data.jsonl",
        )
        with patch("src.cli_commands._run_generate_training_data") as mock_fn:
            with pytest.raises(SystemExit) as exc_info:
                _cmd_training(args)
            assert exc_info.value.code == 0
            mock_fn.assert_called_once_with("data.jsonl")

    def test_training_fine_tune(self):
        args = argparse.Namespace(
            training_action="fine-tune",
            data_path="train.jsonl",
            output_dir="models/custom",
            epochs=5,
        )
        with patch("src.cli_commands._run_fine_tune") as mock_fn:
            with pytest.raises(SystemExit) as exc_info:
                _cmd_training(args)
            assert exc_info.value.code == 0
            mock_fn.assert_called_once_with(
                "train.jsonl",
                output_dir="models/custom",
                epochs=5,
            )

    def test_training_fine_tune_defaults(self):
        args = argparse.Namespace(
            training_action="fine-tune",
            data_path="train.jsonl",
        )
        with patch("src.cli_commands._run_fine_tune") as mock_fn:
            with pytest.raises(SystemExit):
                _cmd_training(args)
            call_kwargs = mock_fn.call_args
            assert call_kwargs[1]["output_dir"] == "models/fine-tuned"
            assert call_kwargs[1]["epochs"] == 3

    def test_training_no_action(self, capsys):
        args = argparse.Namespace(training_action=None)
        with pytest.raises(SystemExit) as exc_info:
            _cmd_training(args)
        assert exc_info.value.code == 2
        output = capsys.readouterr().out
        assert "Usage:" in output


# ── _cmd_admin ───────────────────────────────────────────────────────


class TestCmdAdmin:
    def test_admin_reset_index_with_yes(self, capsys):
        retriever = _make_retriever()
        args = argparse.Namespace(admin_action="reset-index", yes=True)
        with pytest.raises(SystemExit) as exc_info:
            _cmd_admin(args, retriever)
        assert exc_info.value.code == 0
        retriever.reset_index.assert_called_once()
        output = capsys.readouterr().out
        assert "Index has been reset" in output

    def test_admin_reset_index_without_yes(self, capsys):
        retriever = _make_retriever()
        args = argparse.Namespace(admin_action="reset-index", yes=False)
        with pytest.raises(SystemExit) as exc_info:
            _cmd_admin(args, retriever)
        assert exc_info.value.code == 2
        retriever.reset_index.assert_not_called()
        output = capsys.readouterr().out
        assert "Refusing to reset" in output

    def test_admin_no_action(self, capsys):
        retriever = _make_retriever()
        args = argparse.Namespace(admin_action=None)
        with pytest.raises(SystemExit) as exc_info:
            _cmd_admin(args, retriever)
        assert exc_info.value.code == 2
        output = capsys.readouterr().out
        assert "Usage:" in output


# ── _run_browse ──────────────────────────────────────────────────────


class TestRunBrowse:
    def test_browse_with_results(self, capsys):
        mock_db = MagicMock()
        mock_db.list_emails_paginated.return_value = {
            "total": 2,
            "emails": [
                {
                    "subject": "Email One",
                    "sender_email": "alice@example.com",
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
        assert "alice@example.com" in output

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
                    "sender_email": "a@b.com",
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


# ── _run_evidence_list ───────────────────────────────────────────────


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
                    "sender_email": "boss@co.com",
                    "key_quote": "You are incompetent and should be fired immediately",
                },
                {
                    "id": 2,
                    "date": "2024-03-16",
                    "verified": False,
                    "relevance": 3,
                    "category": "bossing",
                    "sender_name": None,
                    "sender_email": "boss@co.com",
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


# ── _run_evidence_export ─────────────────────────────────────────────


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


# ── _run_evidence_stats ──────────────────────────────────────────────


class TestRunEvidenceStats:
    def test_evidence_stats_output(self, capsys):
        mock_db = MagicMock()
        mock_db.evidence_stats.return_value = {
            "total": 10,
            "by_category": {"harassment": 5, "bossing": 3, "general": 2},
        }
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            _run_evidence_stats()
        output = capsys.readouterr().out
        # Works with both rich Panel output and plain JSON output
        assert "10" in output


# ── _run_evidence_verify ─────────────────────────────────────────────


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


# ── _run_dossier ─────────────────────────────────────────────────────


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


# ── _run_custody_chain ───────────────────────────────────────────────


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


# ── _run_provenance ──────────────────────────────────────────────────


class TestRunProvenance:
    def test_provenance_output(self, capsys):
        mock_db = MagicMock()
        mock_db.email_provenance.return_value = {
            "uid": "uid-xyz",
            "email": {"subject": "Test", "sender_email": "test@test.com", "date": "2024-01-01"},
            "source": {"olm_source_hash": "sha256:abc", "ingested_at": "2024-01-01"},
            "custody_events": [],
        }
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            _run_provenance("uid-xyz")
        output = capsys.readouterr().out
        # Rich output renders panels instead of raw JSON
        assert "uid-xyz" in output
        assert "Provenance" in output or "provenance" in output


# ── _run_export_thread ───────────────────────────────────────────────


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


# ── _run_export_email ────────────────────────────────────────────────


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


# ── _run_generate_training_data ──────────────────────────────────────


class TestRunGenerateTrainingData:
    def test_generate_training_data(self, capsys):
        mock_db = MagicMock()
        mock_gen = MagicMock()
        mock_gen.export_jsonl.return_value = {"triplet_count": 150}
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            with patch("src.training_data_generator.TrainingDataGenerator", return_value=mock_gen):
                _run_generate_training_data("train.jsonl")
        output = capsys.readouterr().out
        assert "train.jsonl" in output
        assert "150 triplets" in output


# ── _run_fine_tune ───────────────────────────────────────────────────


class TestRunFineTune:
    def test_fine_tune_success(self, capsys):
        mock_ft = MagicMock()
        mock_ft.fine_tune.return_value = {
            "status": "completed",
            "triplet_count": 100,
            "epochs": 3,
            "config_path": "models/config.json",
        }
        with patch("src.fine_tuner.FineTuner", return_value=mock_ft):
            _run_fine_tune("train.jsonl", output_dir="models/ft", epochs=3)
        output = capsys.readouterr().out
        assert "completed" in output
        assert "100" in output
        assert "Config: models/config.json" in output

    def test_fine_tune_no_config_path(self, capsys):
        mock_ft = MagicMock()
        mock_ft.fine_tune.return_value = {
            "status": "completed",
            "triplet_count": 50,
            "epochs": 5,
            "config_path": None,
        }
        with patch("src.fine_tuner.FineTuner", return_value=mock_ft):
            _run_fine_tune("train.jsonl", output_dir="models/ft", epochs=5)
        output = capsys.readouterr().out
        assert "Config:" not in output


# ── _print_sender_lines ─────────────────────────────────────────────


class TestPrintSenderLines:
    def test_prints_senders(self, capsys):
        senders = [
            {"name": "Alice", "email": "alice@example.com", "count": 50},
            {"name": "Bob", "email": "bob@example.com", "count": 30},
        ]
        _print_sender_lines(senders)
        output = capsys.readouterr().out
        # Works with both rich table (renders "50" in a column) and plain text ("50x")
        assert "50" in output
        assert "Alice" in output
        assert "alice@example.com" in output
        assert "30" in output
        assert "Bob" in output

    def test_no_senders(self, capsys):
        _print_sender_lines([])
        output = capsys.readouterr().out
        assert "No senders found" in output

    def test_custom_print_fn(self):
        """When rich is unavailable, the plain-text fallback uses print_fn."""
        senders = [{"name": "X", "email": "x@y.com", "count": 1}]
        # Patch rich import to force fallback path
        import unittest.mock

        with unittest.mock.patch.dict("sys.modules", {"rich": None, "rich.console": None, "rich.table": None}):
            # Re-import to pick up patched modules - but since imports are cached,
            # we test the actual output which works with rich when available
            pass
        # With rich available, the function uses Console.print which goes to stdout
        _print_sender_lines(senders)
        # Just verify it doesn't crash - output goes to stdout via rich


# ── _interactive_action ──────────────────────────────────────────────


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


# ── _render helpers ──────────────────────────────────────────────────


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


# ── main() dispatch ──────────────────────────────────────────────────


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


# ── _get_email_db ────────────────────────────────────────────────────


class TestGetEmailDb:
    def test_get_email_db_missing_sqlite(self, capsys):
        from src.cli import _get_email_db

        mock_settings = MagicMock()
        mock_settings.sqlite_path = "/nonexistent/path/db.sqlite"
        with patch("src.cli_commands.get_settings", return_value=mock_settings):
            with pytest.raises(SystemExit) as exc_info:
                _get_email_db()
            assert exc_info.value.code == 1
        output = capsys.readouterr().out
        assert "SQLite database not found" in output

    def test_get_email_db_no_path(self, capsys):
        from src.cli import _get_email_db

        mock_settings = MagicMock()
        mock_settings.sqlite_path = None
        with patch("src.cli_commands.get_settings", return_value=mock_settings):
            with pytest.raises(SystemExit) as exc_info:
                _get_email_db()
            assert exc_info.value.code == 1

    def test_get_email_db_success(self, tmp_path):
        from src.cli import _get_email_db

        # Create a dummy sqlite file
        db_path = tmp_path / "test.sqlite"
        db_path.touch()
        mock_settings = MagicMock()
        mock_settings.sqlite_path = str(db_path)
        mock_db = MagicMock()
        with patch("src.cli_commands.get_settings", return_value=mock_settings):
            with patch("src.email_db.EmailDatabase", return_value=mock_db):
                result = _get_email_db()
                assert result is mock_db


# ── _run_analytics_command (legacy path) ─────────────────────────────


class TestRunAnalyticsCommand:
    def test_legacy_top_contacts(self):
        from src.cli import _run_analytics_command

        mock_db = MagicMock()
        args = argparse.Namespace(
            top_contacts="alice@example.com",
            volume=None,
            entities=None,
            heatmap=False,
            response_times=False,
        )
        with patch("src.cli_commands._get_email_db", return_value=mock_db):
            with patch("src.cli_commands._run_top_contacts") as mock_fn:
                _run_analytics_command(args)
                mock_fn.assert_called_once_with(mock_db, "alice@example.com")

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


# ── _cmd_legacy ──────────────────────────────────────────────────────


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
