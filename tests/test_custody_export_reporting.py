"""Custody export and reporting tests split from RF16."""

from __future__ import annotations

from src.email_db import EmailDatabase
from tests._custody_cases import FakeEmail


def test_get_custody_chain_filters_by_target_type(db: EmailDatabase) -> None:
    """Should filter events by target_type."""
    db.log_custody_event("add", target_type="evidence", target_id="1")
    db.log_custody_event("add", target_type="email", target_id="uid-1")

    evidence_events = db.get_custody_chain(target_type="evidence")
    email_events = db.get_custody_chain(target_type="email")

    assert all(event["target_type"] == "evidence" for event in evidence_events)
    assert all(event["target_type"] == "email" for event in email_events)


def test_get_custody_chain_filters_by_action(db: EmailDatabase) -> None:
    """Should filter events by action."""
    db.log_custody_event("evidence_add", target_type="evidence")
    db.log_custody_event("evidence_remove", target_type="evidence")

    add_events = db.get_custody_chain(action="evidence_add")
    assert all(event["action"] == "evidence_add" for event in add_events)


def test_get_custody_chain_respects_limit(db: EmailDatabase) -> None:
    """Should limit the number of returned events."""
    for index in range(10):
        db.log_custody_event("test", target_id=str(index))

    events = db.get_custody_chain(limit=3)
    assert len(events) == 3


def test_get_custody_chain_ordered_desc(db: EmailDatabase) -> None:
    """Events should be ordered newest first."""
    db.log_custody_event("first")
    db.log_custody_event("second")
    events = db.get_custody_chain()
    assert events[0]["id"] > events[-1]["id"]


def test_email_provenance_returns_email_data(db_with_email: EmailDatabase) -> None:
    """email_provenance should return the email record."""
    provenance = db_with_email.email_provenance("test-uid-1")
    assert "email" in provenance
    assert provenance["email"]["uid"] == "test-uid-1"
    assert provenance["email"]["sender_email"] == "alice@example.test"


def test_email_provenance_includes_ingestion_run(db_with_email: EmailDatabase) -> None:
    """email_provenance should include the ingestion run."""
    run_id = db_with_email.record_ingestion_start("test.olm", olm_sha256="abcdef", file_size_bytes=1234)
    db_with_email.record_ingestion_complete(run_id, {"emails_parsed": 1, "emails_inserted": 1})

    provenance = db_with_email.email_provenance("test-uid-1")
    assert provenance["ingestion_run"] is not None
    assert provenance["ingestion_run"]["olm_sha256"] == "abcdef"


def test_email_provenance_uses_ingestion_run_id(db: EmailDatabase) -> None:
    """email_provenance should return the correct run via ingestion_run_id."""
    run1 = db.record_ingestion_start("first.olm", olm_sha256="aaa")
    db.record_ingestion_complete(run1, {"emails_parsed": 1, "emails_inserted": 1})

    run2 = db.record_ingestion_start("second.olm", olm_sha256="bbb")
    db.record_ingestion_complete(run2, {"emails_parsed": 1, "emails_inserted": 1})

    fake_email = FakeEmail(
        uid="prov-uid-1",
        message_id="<prov@example.test>",
        subject="Provenance Test",
        sender_name="Alice",
        sender_email="alice@example.test",
        date="2024-01-15",
        conversation_id="",
        base_subject="Provenance Test",
        clean_body="Test body",
        body_html="",
    )
    db.insert_emails_batch([fake_email], ingestion_run_id=run1)

    provenance = db.email_provenance("prov-uid-1")
    assert provenance["ingestion_run"] is not None
    assert provenance["ingestion_run"]["id"] == run1
    assert provenance["ingestion_run"]["olm_sha256"] == "aaa"


def test_evidence_provenance_returns_full_chain(db_with_email: EmailDatabase) -> None:
    """evidence_provenance should return evidence, source email, and custody events."""
    result = db_with_email.add_evidence(
        "test-uid-1",
        "harassment",
        "important evidence",
        "summary",
        5,
    )
    provenance = db_with_email.evidence_provenance(result["id"])

    assert "evidence" in provenance
    assert provenance["evidence"]["category"] == "harassment"
    assert "source_email" in provenance
    assert provenance["source_email"]["email"]["uid"] == "test-uid-1"
    assert "custody_events" in provenance
    assert len(provenance["custody_events"]) >= 1
