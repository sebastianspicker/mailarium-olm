"""Custody mutation and update-rule tests split from RF16."""

from __future__ import annotations

import logging

from src.email_db import EmailDatabase


def test_add_evidence_creates_custody_event(db_with_email: EmailDatabase) -> None:
    """add_evidence should log an evidence_add custody event."""
    result = db_with_email.add_evidence(
        "test-uid-1",
        "harassment",
        "important evidence",
        "test summary",
        4,
    )
    events = db_with_email.get_custody_chain(target_type="evidence", target_id=str(result["id"]))
    assert len(events) >= 1
    event = events[0]
    assert event["action"] == "evidence_add"
    assert event["details"]["category"] == "harassment"
    assert event["details"]["relevance"] == 4


def test_add_evidence_computes_content_hash(db_with_email: EmailDatabase) -> None:
    """add_evidence should compute and store a content_hash."""
    result = db_with_email.add_evidence(
        "test-uid-1",
        "discrimination",
        "evidence text",
        "summary",
        3,
    )
    assert "content_hash" in result
    assert len(result["content_hash"]) == 64

    row = db_with_email.conn.execute("SELECT content_hash FROM evidence_items WHERE id=?", (result["id"],)).fetchone()
    assert row["content_hash"] == result["content_hash"]


def test_add_evidence_content_hash_is_deterministic(db_with_email: EmailDatabase) -> None:
    """Same email_uid, category, and key_quote should produce the same hash."""
    expected = EmailDatabase.compute_content_hash("test-uid-1|harassment|evidence text")
    result = db_with_email.add_evidence(
        "test-uid-1",
        "harassment",
        "evidence text",
        "summary",
        3,
    )
    assert result["content_hash"] == expected


def test_update_evidence_logs_custody_event(db_with_email: EmailDatabase) -> None:
    """update_evidence should log an evidence_update custody event with old values."""
    result = db_with_email.add_evidence(
        "test-uid-1",
        "harassment",
        "important evidence",
        "old summary",
        3,
    )
    evidence_id = result["id"]

    db_with_email.update_evidence(evidence_id, summary="new summary", relevance=5)

    events = db_with_email.get_custody_chain(
        target_type="evidence",
        target_id=str(evidence_id),
        action="evidence_update",
    )
    assert len(events) >= 1
    event = events[0]
    assert event["details"]["old_values"]["summary"] == "old summary"
    assert event["details"]["old_values"]["relevance"] == 3
    assert event["details"]["new_values"]["summary"] == "new summary"
    assert event["details"]["new_values"]["relevance"] == 5


def test_update_evidence_recomputes_content_hash(db_with_email: EmailDatabase) -> None:
    """Updating category or key_quote should recompute content_hash."""
    result = db_with_email.add_evidence(
        "test-uid-1",
        "harassment",
        "old quote",
        "summary",
        3,
    )
    old_hash = result["content_hash"]

    db_with_email.update_evidence(result["id"], key_quote="new quote")

    row = db_with_email.conn.execute("SELECT content_hash FROM evidence_items WHERE id=?", (result["id"],)).fetchone()
    assert row["content_hash"] != old_hash
    assert row["content_hash"] == EmailDatabase.compute_content_hash("test-uid-1|harassment|new quote")


def test_remove_evidence_logs_custody_event(db_with_email: EmailDatabase) -> None:
    """remove_evidence should log an evidence_remove custody event with snapshot."""
    result = db_with_email.add_evidence(
        "test-uid-1",
        "discrimination",
        "the evidence quote",
        "summary",
        4,
    )
    evidence_id = result["id"]

    db_with_email.remove_evidence(evidence_id)

    events = db_with_email.get_custody_chain(
        target_type="evidence",
        target_id=str(evidence_id),
        action="evidence_remove",
    )
    assert len(events) >= 1
    event = events[0]
    assert event["details"]["email_uid"] == "test-uid-1"
    assert event["details"]["category"] == "discrimination"
    assert event["details"]["relevance"] == 4


def test_evidence_categories_match_mcp_tools_doc() -> None:
    """EVIDENCE_CATEGORIES should match the canonical MCP-doc list."""
    expected = {
        "bossing",
        "harassment",
        "discrimination",
        "retaliation",
        "hostile_environment",
        "micromanagement",
        "exclusion",
        "gaslighting",
        "workload",
        "general",
    }
    assert set(EmailDatabase.EVIDENCE_CATEGORIES) == expected


def test_add_evidence_warns_on_nonstandard_category(db_with_email: EmailDatabase, caplog) -> None:
    """add_evidence should log a warning for non-standard categories."""
    with caplog.at_level(logging.WARNING, logger="src.db_evidence"):
        db_with_email.add_evidence(
            "test-uid-1",
            "made_up_category",
            "important evidence",
            "test",
            3,
        )
    assert "Non-standard evidence category" in caplog.text
    assert "made_up_category" in caplog.text


def test_add_evidence_no_warning_for_standard_category(db_with_email: EmailDatabase, caplog) -> None:
    """add_evidence should not warn for standard categories."""
    with caplog.at_level(logging.WARNING, logger="src.db_evidence"):
        db_with_email.add_evidence(
            "test-uid-1",
            "harassment",
            "evidence text",
            "test",
            3,
        )
    assert "Non-standard evidence category" not in caplog.text
