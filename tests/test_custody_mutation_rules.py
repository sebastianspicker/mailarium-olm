"""Custody mutation and update-rule tests split from RF16."""

from __future__ import annotations

import pytest

from mailarium.email_db import EmailDatabase


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


def test_default_evidence_categories_are_domain_neutral() -> None:
    """Suggested categories should work across arbitrary retrieval scopes."""
    expected = {
        "general",
        "fact",
        "decision",
        "action_item",
        "commitment",
        "contradiction",
        "chronology",
        "provenance",
        "quote_repair",
        "omission",
        "risk",
        "requirement",
    }
    assert set(EmailDatabase.EVIDENCE_CATEGORIES) == expected


def test_add_evidence_accepts_and_normalizes_user_defined_category(db_with_email: EmailDatabase) -> None:
    """User categories are first-class inputs rather than a fixed domain taxonomy."""
    item = db_with_email.add_evidence(
        "test-uid-1",
        "  migration_blocker  ",
        "important evidence",
        "test",
        3,
    )

    assert item["category"] == "migration_blocker"


@pytest.mark.parametrize("category", ["", "   ", "x" * 81])
def test_add_evidence_rejects_invalid_user_category(db_with_email: EmailDatabase, category: str) -> None:
    with pytest.raises(ValueError, match="Evidence category"):
        db_with_email.add_evidence(
            "test-uid-1",
            category,
            "important evidence",
            "test",
            3,
        )


def test_update_evidence_ignores_unspecified_fields_and_normalizes_category(db_with_email: EmailDatabase) -> None:
    item = db_with_email.add_evidence(
        "test-uid-1",
        "general",
        "important evidence",
        "test",
        3,
    )

    assert db_with_email.update_evidence(
        item["id"],
        category="  migration_blocker  ",
        key_quote=None,
        summary=None,
        relevance=None,
        notes=None,
    )
    updated = db_with_email.get_evidence(item["id"])
    assert updated is not None
    assert updated["category"] == "migration_blocker"
    assert updated["key_quote"] == "important evidence"
