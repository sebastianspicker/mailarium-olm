"""Custody edge and failure tests split from RF16."""

from __future__ import annotations

from src.email_db import EmailDatabase


def test_remove_nonexistent_evidence_no_custody_event(db_with_email: EmailDatabase) -> None:
    """Removing a nonexistent evidence ID should not create a custody event."""
    initial_events = db_with_email.get_custody_chain(action="evidence_remove")
    db_with_email.remove_evidence(99999)
    after_events = db_with_email.get_custody_chain(action="evidence_remove")
    assert len(after_events) == len(initial_events)


def test_email_provenance_not_found(db: EmailDatabase) -> None:
    """email_provenance should return error for missing email."""
    provenance = db.email_provenance("nonexistent-uid")
    assert "error" in provenance


def test_evidence_provenance_not_found(db: EmailDatabase) -> None:
    """evidence_provenance should return error for missing evidence."""
    provenance = db.evidence_provenance(99999)
    assert "error" in provenance
