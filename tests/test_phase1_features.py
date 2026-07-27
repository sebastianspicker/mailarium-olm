"""Verifies retrieval filters, CLI analytics, and incremental ingestion work together."""

import pytest

from mailarium.result_filters import STRING_FILTERS, _matches_string
from mailarium.retriever import SearchResult
from mailarium.web_ui import build_active_filter_labels

# --------------------------------------------------------------------------
# Phase 1A: email_type filter in retriever
# --------------------------------------------------------------------------


def _make_result(email_type: str = "original", uid: str = "u1") -> SearchResult:
    return SearchResult(
        chunk_id=f"c-{uid}",
        text="body",
        metadata={"email_type": email_type, "uid": uid, "date": "2024-01-01"},
        distance=0.2,
    )


def _match_email_type(result: SearchResult, needle: str | None) -> bool:
    """Helper: call _matches_string with the email_type filter config."""
    keys, mtype = STRING_FILTERS["email_type"]
    return _matches_string(result, needle, keys, mtype)


def test_matches_email_type_exact():
    assert _match_email_type(_make_result("reply"), "reply")
    assert _match_email_type(_make_result("forward"), "forward")
    assert _match_email_type(_make_result("original"), "original")


def test_matches_email_type_case_insensitive():
    assert _match_email_type(_make_result("Reply"), "reply")


def test_matches_email_type_none_matches_all():
    assert _match_email_type(_make_result("reply"), None)
    assert _match_email_type(_make_result("forward"), None)


def test_matches_email_type_rejects_mismatch():
    assert not _match_email_type(_make_result("reply"), "forward")
    assert not _match_email_type(_make_result("original"), "reply")


# --------------------------------------------------------------------------
# Phase 1A: CLI flags for bcc/priority/email_type
# --------------------------------------------------------------------------


def test_parse_args_supports_bcc_flag():
    from mailarium.cli import parse_args

    args = parse_args(["search", "--query", "test", "--bcc", "secret@example.com"])
    assert args.bcc == "secret@example.com"


def test_parse_args_supports_priority_flag():
    from mailarium.cli import parse_args

    args = parse_args(["search", "--query", "test", "--priority", "3"])
    assert args.priority == 3


def test_parse_args_supports_email_type_flag():
    from mailarium.cli import parse_args

    args = parse_args(["search", "--query", "test", "--email-type", "reply"])
    assert args.email_type == "reply"


def test_parse_args_bcc_requires_query():
    from mailarium.cli import parse_args

    with pytest.raises(SystemExit):
        parse_args(["search", "--bcc", "secret@example.com"])


def test_parse_args_priority_requires_query():
    from mailarium.cli import parse_args

    with pytest.raises(SystemExit):
        parse_args(["search", "--priority", "3"])


def test_parse_args_email_type_requires_query():
    from mailarium.cli import parse_args

    with pytest.raises(SystemExit):
        parse_args(["search", "--email-type", "reply"])


# --------------------------------------------------------------------------
# Phase 1A: web_ui filter labels include new filters
# --------------------------------------------------------------------------


def test_filter_labels_include_bcc():
    labels = build_active_filter_labels({"bcc": "hidden@example.com"})
    assert "BCC: hidden@example.com" in labels


def test_filter_labels_include_priority():
    labels = build_active_filter_labels({"priority": 3})
    assert "Priority ≥ 3" in labels


def test_filter_labels_include_email_type():
    labels = build_active_filter_labels({"email_type": "reply"})
    assert "Type: reply" in labels


def test_filter_labels_priority_zero_not_shown():
    labels = build_active_filter_labels({"priority": None})
    assert not any("Priority" in lbl for lbl in labels)


def test_filter_labels_email_type_none_not_shown():
    labels = build_active_filter_labels({"email_type": None})
    assert not any("Type" in lbl for lbl in labels)


# --------------------------------------------------------------------------
# Phase 1B: CLI analytics args parse
# --------------------------------------------------------------------------


def test_parse_args_top_contacts():
    from mailarium.cli import parse_args

    args = parse_args(["analytics", "contacts", "me@example.com"])
    assert args.analytics_action == "contacts"
    assert args.email_address == "me@example.com"


def test_parse_args_volume():
    from mailarium.cli import parse_args

    args = parse_args(["analytics", "volume", "month"])
    assert args.analytics_action == "volume"
    assert args.period == "month"


def test_parse_args_entities():
    from mailarium.cli import parse_args

    args = parse_args(["analytics", "entities", "--type", "organization"])
    assert args.analytics_action == "entities"
    assert args.entity_type == "organization"


def test_parse_args_entities_no_type():
    from mailarium.cli import parse_args

    args = parse_args(["analytics", "entities"])
    assert args.analytics_action == "entities"
    assert args.entity_type is None


def test_parse_args_heatmap():
    from mailarium.cli import parse_args

    args = parse_args(["analytics", "heatmap"])
    assert args.analytics_action == "heatmap"


def test_parse_args_response_times():
    from mailarium.cli import parse_args

    args = parse_args(["analytics", "response-times"])
    assert args.analytics_action == "response-times"


def test_flat_query_flag_is_rejected():
    from mailarium.cli import parse_args

    with pytest.raises(SystemExit):
        parse_args(["--query", "test"])


def test_flat_analytics_flag_is_rejected():
    from mailarium.cli import parse_args

    with pytest.raises(SystemExit):
        parse_args(["--top-contacts", "me@example.com"])


# --------------------------------------------------------------------------
# Phase 1C: Incremental ingestion & tracking
# --------------------------------------------------------------------------


def test_ingestion_runs_table_created():
    from mailarium.email_db import EmailDatabase

    db = EmailDatabase(":memory:")
    # Table should exist
    row = db.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ingestion_runs'").fetchone()
    assert row is not None


def test_record_ingestion_start_and_complete(tmp_path):
    from mailarium.email_db import EmailDatabase

    db = EmailDatabase(":memory:")
    run_id = db.record_ingestion_start(str(tmp_path / "test.olm"))
    assert run_id is not None
    assert run_id > 0

    db.record_ingestion_complete(run_id, {"emails_parsed": 100, "emails_inserted": 95})

    last = db.last_ingestion(str(tmp_path / "test.olm"))
    assert last is not None
    assert last["status"] == "completed"
    assert last["emails_parsed"] == 100
    assert last["emails_inserted"] == 95


def test_last_ingestion_returns_none_when_empty(tmp_path):
    from mailarium.email_db import EmailDatabase

    db = EmailDatabase(":memory:")
    assert db.last_ingestion() is None
    assert db.last_ingestion(str(tmp_path / "nonexistent.olm")) is None


def test_last_ingestion_returns_most_recent(tmp_path):
    from mailarium.email_db import EmailDatabase

    db = EmailDatabase(":memory:")
    run1 = db.record_ingestion_start(str(tmp_path / "test.olm"))
    db.record_ingestion_complete(run1, {"emails_parsed": 50, "emails_inserted": 50})

    run2 = db.record_ingestion_start(str(tmp_path / "test.olm"))
    db.record_ingestion_complete(run2, {"emails_parsed": 100, "emails_inserted": 100})

    last = db.last_ingestion(str(tmp_path / "test.olm"))
    assert last["emails_parsed"] == 100


def test_ingest_incremental_flag_parsed():
    from mailarium.ingest import parse_args

    args = parse_args(["test.olm", "--incremental"])
    assert args.incremental is True
