"""Tests for email_triage and email_deep_context tools."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.formatting import format_triage_results
from src.mcp_models import EmailDeepContextInput, EmailTriageInput
from src.tools.browse import _thread_date_range, _unique_participants

# ── EmailTriageInput model tests ──────────────────────────────


class TestEmailTriageInputDefaults:
    def test_defaults(self):
        m = EmailTriageInput(query="test query")
        assert m.top_k == 50
        assert m.preview_chars == 200
        assert m.sender is None
        assert m.folder is None
        assert m.has_attachments is None
        assert m.hybrid is False
        assert m.date_from is None
        assert m.date_to is None

    def test_top_k_max_rejected(self):
        with pytest.raises(ValidationError):
            EmailTriageInput(query="test", top_k=101)

    def test_top_k_min_rejected(self):
        with pytest.raises(ValidationError):
            EmailTriageInput(query="test", top_k=0)

    def test_preview_chars_max_rejected(self):
        with pytest.raises(ValidationError):
            EmailTriageInput(query="test", preview_chars=501)

    def test_preview_chars_zero_allowed(self):
        m = EmailTriageInput(query="test", preview_chars=0)
        assert m.preview_chars == 0

    def test_date_validation(self):
        m = EmailTriageInput(query="test", date_from="2024-01-01", date_to="2024-12-31")
        assert m.date_from == "2024-01-01"
        assert m.date_to == "2024-12-31"

    def test_date_validation_bad_format(self):
        with pytest.raises(ValidationError):
            EmailTriageInput(query="test", date_from="not-a-date")

    def test_date_validation_inverted_range(self):
        with pytest.raises(ValidationError):
            EmailTriageInput(query="test", date_from="2024-12-31", date_to="2024-01-01")

    def test_empty_query_rejected(self):
        with pytest.raises(ValidationError):
            EmailTriageInput(query="")

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            EmailTriageInput(query="test", nonexistent_field="value")


# ── EmailDeepContextInput model tests ─────────────────────────


class TestEmailDeepContextInputDefaults:
    def test_defaults(self):
        m = EmailDeepContextInput(uid="abc123")
        assert m.include_thread is True
        assert m.include_evidence is True
        assert m.include_sender_stats is True
        assert m.max_body_chars is None

    def test_all_flags_false(self):
        m = EmailDeepContextInput(
            uid="abc",
            include_thread=False,
            include_evidence=False,
            include_sender_stats=False,
        )
        assert m.include_thread is False
        assert m.include_evidence is False
        assert m.include_sender_stats is False

    def test_max_body_chars_zero_unlimited(self):
        m = EmailDeepContextInput(uid="abc", max_body_chars=0)
        assert m.max_body_chars == 0

    def test_empty_uid_rejected(self):
        with pytest.raises(ValidationError):
            EmailDeepContextInput(uid="")

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            EmailDeepContextInput(uid="abc", bogus=True)


# ── format_triage_results tests ───────────────────────────────


def _make_result(uid="u1", sender="a@b.com", date="2024-03-15T10:30:00", subject="Hello", score=0.87654, text="Body text here"):
    """Create a fake search result with .metadata, .score, .text."""
    return SimpleNamespace(
        metadata={"uid": uid, "sender_email": sender, "date": date, "subject": subject},
        score=score,
        text=text,
    )


class TestFormatTriageResults:
    def test_compact_keys(self):
        results = format_triage_results([_make_result()], preview_chars=200)
        assert len(results) == 1
        entry = results[0]
        assert set(entry.keys()) == {"uid", "sender", "date", "subject", "score", "preview"}

    def test_no_preview_when_zero(self):
        results = format_triage_results([_make_result()], preview_chars=0)
        entry = results[0]
        assert "preview" not in entry
        assert set(entry.keys()) == {"uid", "sender", "date", "subject", "score"}

    def test_date_truncation(self):
        results = format_triage_results([_make_result(date="2024-03-15T10:30:00")])
        assert results[0]["date"] == "2024-03-15"

    def test_score_rounding(self):
        results = format_triage_results([_make_result(score=0.87654321)])
        assert results[0]["score"] == 0.877

    def test_preview_truncation(self):
        long_body = "x" * 300
        results = format_triage_results([_make_result(text=long_body)], preview_chars=200)
        assert results[0]["preview"] == "x" * 200 + "..."

    def test_short_body_no_ellipsis(self):
        results = format_triage_results([_make_result(text="short")], preview_chars=200)
        assert results[0]["preview"] == "short"

    def test_empty_results(self):
        assert format_triage_results([]) == []

    def test_multiple_results_order(self):
        r1 = _make_result(uid="u1", score=0.9)
        r2 = _make_result(uid="u2", score=0.8)
        results = format_triage_results([r1, r2])
        assert results[0]["uid"] == "u1"
        assert results[1]["uid"] == "u2"

    def test_missing_metadata_fields(self):
        """Gracefully handles missing metadata keys."""
        r = SimpleNamespace(metadata={}, score=0.5, text="body")
        results = format_triage_results([r], preview_chars=100)
        assert results[0]["uid"] == ""
        assert results[0]["sender"] == ""

    def test_none_text_no_preview_crash(self):
        """None text should produce empty preview, not crash."""
        r = SimpleNamespace(metadata={"uid": "u1", "sender_email": "", "date": "", "subject": ""}, score=0.5, text=None)
        results = format_triage_results([r], preview_chars=200)
        assert results[0]["preview"] == ""


# ── _archive_stats_hint tests ─────────────────────────────────


class TestArchiveStatsHint:
    def test_returns_dict_with_keys(self):
        from src.tools.search import _archive_stats_hint

        class FakeRetriever:
            def stats(self):
                return {
                    "total_emails": 500,
                    "date_range": {"earliest": "2023-01-01", "latest": "2024-12-31"},
                    "unique_senders": 42,
                }

        result = _archive_stats_hint(FakeRetriever())
        assert result["total_emails"] == 500
        assert "2023-01-01" in result["date_range"]
        assert result["unique_senders"] == 42

    def test_returns_empty_on_exception(self):
        from src.tools.search import _archive_stats_hint

        class BrokenRetriever:
            def stats(self):
                raise RuntimeError("boom")

        assert _archive_stats_hint(BrokenRetriever()) == {}


# ── _unique_participants tests ────────────────────────────────


class TestUniqueParticipants:
    def test_deduplicates_case_insensitive(self):
        emails = [
            {"sender_email": "Alice@Example.COM"},
            {"sender_email": "alice@example.com"},
            {"sender_email": "Bob@example.com"},
        ]
        result = _unique_participants(emails)
        assert len(result) == 2
        assert result[0] == "alice@example.com"
        assert result[1] == "bob@example.com"

    def test_handles_empty(self):
        assert _unique_participants([]) == []

    def test_handles_none_sender(self):
        emails = [{"sender_email": None}, {"sender_email": "a@b.com"}]
        result = _unique_participants(emails)
        assert result == ["a@b.com"]

    def test_handles_missing_key(self):
        emails = [{}, {"sender_email": "a@b.com"}]
        result = _unique_participants(emails)
        assert result == ["a@b.com"]

    def test_preserves_order(self):
        emails = [
            {"sender_email": "c@d.com"},
            {"sender_email": "a@b.com"},
            {"sender_email": "c@d.com"},
        ]
        result = _unique_participants(emails)
        assert result == ["c@d.com", "a@b.com"]


# ── _thread_date_range tests ─────────────────────────────────


class TestThreadDateRange:
    def test_handles_empty(self):
        assert _thread_date_range([]) == {}

    def test_extracts_min_max(self):
        emails = [
            {"date": "2024-03-15T10:00:00"},
            {"date": "2024-01-01T08:00:00"},
            {"date": "2024-06-30T12:00:00"},
        ]
        result = _thread_date_range(emails)
        assert result["first"] == "2024-01-01"
        assert result["last"] == "2024-06-30"

    def test_single_email(self):
        result = _thread_date_range([{"date": "2024-05-10"}])
        assert result["first"] == "2024-05-10"
        assert result["last"] == "2024-05-10"

    def test_skips_empty_dates(self):
        emails = [{"date": ""}, {"date": "2024-03-15"}, {"date": None}]
        result = _thread_date_range(emails)
        assert result["first"] == "2024-03-15"
        assert result["last"] == "2024-03-15"
