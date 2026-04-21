"""Evidence verification and formatting-oriented tests split from RF15."""

from __future__ import annotations

from src.email_db import EmailDatabase
from tests._evidence_cases import make_email, seed_evidence


def test_verify_evidence_quotes():
    db = EmailDatabase(":memory:")
    email_one = make_email(message_id="<m1@x>", body_text="Real quote here.")
    email_two = make_email(message_id="<m2@x>", body_text="Different text.")
    db.insert_email(email_one)
    db.insert_email(email_two)

    db.add_evidence(email_one.uid, "harassment", "Real quote here", "Test.", 3)
    db.add_evidence(email_two.uid, "gaslighting", "Fabricated quote", "Test.", 2)

    result = db.verify_evidence_quotes()
    assert result["verified"] == 1
    assert result["failed"] == 1
    assert result["total"] == 2
    assert len(result["failures"]) == 1
    assert result["failures"][0]["key_quote_preview"].startswith("Fabricated")
    db.close()


def test_verify_evidence_quotes_empty():
    db = EmailDatabase(":memory:")
    result = db.verify_evidence_quotes()
    assert result["verified"] == 0
    assert result["failed"] == 0
    assert result["total"] == 0
    db.close()


def test_evidence_categories_all_canonical():
    db = EmailDatabase(":memory:")
    categories = db.evidence_categories()
    assert len(categories) == 10
    names = [category["category"] for category in categories]
    assert "discrimination" in names
    assert "harassment" in names
    assert "gaslighting" in names
    assert "general" in names
    db.close()


def test_evidence_categories_with_counts():
    db = EmailDatabase(":memory:")
    seed_evidence(db)

    categories = db.evidence_categories()
    cat_map = {category["category"]: category["count"] for category in categories}
    assert cat_map["gaslighting"] == 1
    assert cat_map["bossing"] == 1
    assert cat_map["harassment"] == 1
    assert cat_map["discrimination"] == 1
    assert cat_map["micromanagement"] == 0
    db.close()


def test_evidence_categories_empty():
    db = EmailDatabase(":memory:")
    categories = db.evidence_categories()
    assert all(category["count"] == 0 for category in categories)
    db.close()
