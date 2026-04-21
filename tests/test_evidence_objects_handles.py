"""Core evidence object and handle tests split from RF15."""

from __future__ import annotations

import pytest

from src.email_db import EmailDatabase
from tests._evidence_cases import make_email


def test_evidence_table_exists():
    db = EmailDatabase(":memory:")
    tables = {row[0] for row in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "evidence_items" in tables
    db.close()


def test_evidence_table_columns():
    db = EmailDatabase(":memory:")
    cols = {row[1] for row in db.conn.execute("PRAGMA table_info(evidence_items)").fetchall()}
    expected = {
        "id",
        "email_uid",
        "category",
        "key_quote",
        "summary",
        "relevance",
        "sender_name",
        "sender_email",
        "date",
        "recipients",
        "subject",
        "notes",
        "created_at",
        "updated_at",
        "verified",
    }
    assert expected.issubset(cols)
    db.close()


def test_add_evidence_valid():
    db = EmailDatabase(":memory:")
    email = make_email()
    db.insert_email(email)

    result = db.add_evidence(
        email_uid=email.uid,
        category="discrimination",
        key_quote="We don't need people like you.",
        summary="Exclusionary language targeting the recipient.",
        relevance=5,
    )

    assert result["id"] is not None
    assert result["category"] == "discrimination"
    assert result["relevance"] == 5
    assert result["sender_email"] == "alice@company.com"
    assert result["sender_name"] == "Alice Manager"
    assert result["subject"] == "Meeting notes"
    assert result["date"] == "2024-03-15T10:30:00"
    assert result["verified"] == 1
    db.close()


def test_add_evidence_auto_populates_recipients():
    db = EmailDatabase(":memory:")
    email = make_email(to=["Bob <bob@company.com>", "Carol <carol@company.com>"])
    db.insert_email(email)

    result = db.add_evidence(
        email_uid=email.uid,
        category="harassment",
        key_quote="You are not welcome here.",
        summary="Hostile statement.",
        relevance=4,
    )

    assert "bob@company.com" in result["recipients"]
    assert "carol@company.com" in result["recipients"]
    db.close()


def test_add_evidence_invalid_uid():
    db = EmailDatabase(":memory:")
    with pytest.raises(ValueError, match="Email not found"):
        db.add_evidence(
            email_uid="nonexistent_uid",
            category="discrimination",
            key_quote="test quote",
            summary="test",
            relevance=3,
        )
    db.close()


def test_add_evidence_quote_verified_when_present():
    db = EmailDatabase(":memory:")
    email = make_email(body_text="This is clearly inappropriate behavior.")
    db.insert_email(email)

    result = db.add_evidence(
        email_uid=email.uid,
        category="harassment",
        key_quote="clearly inappropriate behavior",
        summary="Test.",
        relevance=3,
    )
    assert result["verified"] == 1
    db.close()


def test_add_evidence_quote_not_verified_when_missing():
    db = EmailDatabase(":memory:")
    email = make_email(body_text="Normal email text.")
    db.insert_email(email)

    result = db.add_evidence(
        email_uid=email.uid,
        category="general",
        key_quote="This quote does not exist in the email",
        summary="Test.",
        relevance=1,
    )
    assert result["verified"] == 0
    db.close()


def test_add_evidence_quote_verified_case_insensitive():
    db = EmailDatabase(":memory:")
    email = make_email(body_text="You are NOT welcome here.")
    db.insert_email(email)

    result = db.add_evidence(
        email_uid=email.uid,
        category="bossing",
        key_quote="you are not welcome here",
        summary="Hostile statement.",
        relevance=4,
    )
    assert result["verified"] == 1
    db.close()


def test_add_evidence_with_notes():
    db = EmailDatabase(":memory:")
    email = make_email()
    db.insert_email(email)

    result = db.add_evidence(
        email_uid=email.uid,
        category="gaslighting",
        key_quote="don't need people like you",
        summary="Derogatory language.",
        relevance=4,
        notes="Pattern of repeated insults since 2022.",
    )
    assert result["notes"] == "Pattern of repeated insults since 2022."
    db.close()


def test_get_evidence_valid():
    db = EmailDatabase(":memory:")
    email = make_email()
    db.insert_email(email)
    added = db.add_evidence(email.uid, "bossing", "not welcome", "Test.", 3)

    item = db.get_evidence(added["id"])
    assert item is not None
    assert item["id"] == added["id"]
    assert item["category"] == "bossing"
    db.close()


def test_get_evidence_invalid():
    db = EmailDatabase(":memory:")
    assert db.get_evidence(999) is None
    db.close()


def test_update_evidence_fields():
    db = EmailDatabase(":memory:")
    email = make_email()
    db.insert_email(email)
    added = db.add_evidence(email.uid, "general", "not welcome", "Initial.", 2)

    updated = db.update_evidence(added["id"], category="bossing", relevance=4, notes="Updated note")
    assert updated is True

    item = db.get_evidence(added["id"])
    assert item["category"] == "bossing"
    assert item["relevance"] == 4
    assert item["notes"] == "Updated note"
    db.close()


def test_update_evidence_invalid_id():
    db = EmailDatabase(":memory:")
    assert db.update_evidence(999, category="test") is False
    db.close()


def test_update_evidence_reverifies_quote():
    db = EmailDatabase(":memory:")
    email = make_email(body_text="Original text here. New quote in body.")
    db.insert_email(email)
    added = db.add_evidence(email.uid, "general", "Original text here", "Test.", 2)
    assert db.get_evidence(added["id"])["verified"] == 1

    db.update_evidence(added["id"], key_quote="This quote is fabricated")
    item = db.get_evidence(added["id"])
    assert item["verified"] == 0

    db.update_evidence(added["id"], key_quote="New quote in body")
    item = db.get_evidence(added["id"])
    assert item["verified"] == 1
    db.close()


def test_update_evidence_no_valid_fields():
    db = EmailDatabase(":memory:")
    email = make_email()
    db.insert_email(email)
    added = db.add_evidence(email.uid, "general", "not welcome", "Test.", 2)

    assert db.update_evidence(added["id"], bogus_field="value") is False
    db.close()


def test_remove_evidence_valid():
    db = EmailDatabase(":memory:")
    email = make_email()
    db.insert_email(email)
    added = db.add_evidence(email.uid, "gaslighting", "not welcome", "Test.", 3)

    assert db.remove_evidence(added["id"]) is True
    assert db.get_evidence(added["id"]) is None
    db.close()


def test_remove_evidence_invalid():
    db = EmailDatabase(":memory:")
    assert db.remove_evidence(999) is False
    db.close()
