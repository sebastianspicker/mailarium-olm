"""Evidence verification and formatting-oriented tests split from RF15."""

from __future__ import annotations

from src.db_evidence import EvidenceMixin
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


def test_verify_evidence_quotes_uses_forensic_body_text():
    db = EmailDatabase(":memory:")
    email = make_email(
        message_id="<m3@x>",
        body_text="Hi Lara,",
        forensic_body_text="Hi Lara,\nPlease document the restriction in writing.\nRegards",
        raw_body_text="Hi Lara,\nPlease document the restriction in writing.\nRegards",
        forensic_body_source="raw_body_text",
    )
    db.insert_email(email)

    item = db.add_evidence(
        email.uid,
        "general",
        "Please document the restriction in writing.",
        "Forwarded content preserved only in forensic body.",
        4,
    )
    db.conn.execute("UPDATE evidence_items SET verified = 0 WHERE id = ?", (item["id"],))
    db.conn.commit()

    result = db.verify_evidence_quotes()
    assert result["verified"] == 1
    assert result["failed"] == 0
    assert result["total"] == 1
    refreshed = db.get_evidence(item["id"])
    assert refreshed is not None
    assert refreshed["verified"] == 1
    db.close()


def test_verify_evidence_quotes_tolerates_smart_quotes_and_dash_drift():
    db = EmailDatabase(":memory:")
    email = make_email(
        message_id="<m4@x>",
        body_text='Sie sagte: "Bitte dokumentieren - sofort."',
    )
    db.insert_email(email)

    item = db.add_evidence(
        email.uid,
        "general",
        "Sie sagte: „Bitte dokumentieren – sofort.“",
        "Punctuation-normalized quote.",
        4,
    )
    db.conn.execute("UPDATE evidence_items SET verified = 0 WHERE id = ?", (item["id"],))
    db.conn.commit()

    result = db.verify_evidence_quotes()
    assert result["verified"] == 1
    assert result["failed"] == 0
    refreshed = db.get_evidence(item["id"])
    assert refreshed is not None
    assert refreshed["verified"] == 1
    db.close()


def test_verify_evidence_quotes_is_artifact_scoped_for_attachments() -> None:
    db = EmailDatabase(":memory:")
    email = make_email(message_id="<m5@x>", body_text="Bitte siehe Anlagen.")
    email.attachments = [
        {
            "name": "anlage-a.txt",
            "mime_type": "text/plain",
            "size": 20,
            "is_inline": False,
            "attachment_id": "sha256:attachment-a",
            "content_sha256": "a" * 64,
            "extracted_text": "Nur allgemeine Hinweise.",
            "text_preview": "Nur allgemeine Hinweise.",
        },
        {
            "name": "anlage-b.txt",
            "mime_type": "text/plain",
            "size": 40,
            "is_inline": False,
            "attachment_id": "sha256:attachment-b",
            "content_sha256": "b" * 64,
            "extracted_text": "Wir bestaetigen die mobile Arbeit fuer medizinisch notwendige Termine.",
            "text_preview": "Wir bestaetigen die mobile Arbeit fuer medizinisch notwendige Termine.",
        },
    ]
    db.insert_email(email)

    item = db.add_evidence(
        email.uid,
        "general",
        "Wir bestaetigen die mobile Arbeit fuer medizinisch notwendige Termine.",
        "Quote exists in attachment B but locator points at A.",
        4,
        candidate_kind="attachment",
        document_locator={
            "attachment_id": "sha256:attachment-a",
            "content_sha256": "a" * 64,
            "attachment_filename": "anlage-a.txt",
        },
    )

    assert item["verified"] == 0
    result = db.verify_evidence_quotes()
    assert result["verified"] == 0
    assert result["failed"] == 1
    assert result["near_exact"] == 0
    db.close()


def test_verify_evidence_quotes_marks_german_transliteration_as_near_exact() -> None:
    db = EmailDatabase(":memory:")
    email = make_email(
        message_id="<m6@x>",
        body_text="Die Maßnahme für Wiedereingliederung bleibt bestehen.",
    )
    db.insert_email(email)

    item = db.add_evidence(
        email.uid,
        "general",
        "Die Massnahme fuer Wiedereingliederung bleibt bestehen.",
        "German transliteration should be near exact, not exact.",
        4,
    )
    assert item["verified"] == 0

    result = db.verify_evidence_quotes()
    assert result["verified"] == 0
    assert result["near_exact"] == 1
    assert result["failed"] == 0
    refreshed = db.get_evidence(item["id"])
    assert refreshed is not None
    assert refreshed["verified"] == 0
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
    names = [category["category"] for category in categories]
    assert len(categories) == len(EvidenceMixin.EVIDENCE_CATEGORIES)
    assert names == EvidenceMixin.EVIDENCE_CATEGORIES
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
