from __future__ import annotations

from src.chunker import chunk_email, strip_signature


def test_strip_signature_rfc_separator():
    body = "Hello, world!\n\n-- \nJohn Doe\njohn@example.com"
    stripped, had_sig = strip_signature(body)
    assert had_sig is True
    assert "Hello, world!" in stripped
    assert "John Doe" not in stripped


def test_strip_signature_double_dash():
    body = "Hello!\n\n--\nJohn Doe\nCompany Inc."
    stripped, had_sig = strip_signature(body)
    assert had_sig is True
    assert stripped == "Hello!"


def test_strip_signature_sent_from():
    body = "See you tomorrow.\n\nSent from my iPhone"
    stripped, had_sig = strip_signature(body)
    assert had_sig is True
    assert "See you tomorrow" in stripped
    assert "iPhone" not in stripped


def test_strip_signature_sent_from_outlook():
    body = "Done.\n\nSent from my Outlook for Android"
    stripped, had_sig = strip_signature(body)
    assert had_sig is True
    assert stripped == "Done."


def test_strip_signature_closing_phrase():
    body = "I'll handle it.\n\nBest regards,\nAlice Smith\nManager"
    stripped, had_sig = strip_signature(body)
    assert had_sig is True
    assert "I'll handle it" in stripped
    assert "Alice Smith" not in stripped


def test_strip_signature_closing_german():
    body = "Alles erledigt.\n\nMit freundlichen Grüßen,\nHans Müller"
    stripped, had_sig = strip_signature(body)
    assert had_sig is True
    assert "Alles erledigt" in stripped


def test_strip_signature_no_signature():
    body = "Just a regular email without a signature."
    stripped, had_sig = strip_signature(body)
    assert had_sig is False
    assert stripped == body


def test_strip_signature_empty():
    stripped, had_sig = strip_signature("")
    assert had_sig is False
    assert stripped == ""


def test_chunk_email_strips_signature():
    email = {
        "uid": "sig1",
        "message_id": "m1",
        "subject": "Test",
        "sender_name": "Bob",
        "sender_email": "bob@example.com",
        "to": ["alice@example.com"],
        "cc": [],
        "date": "2025-01-01",
        "body": "Important info here.\n\n-- \nBob\nbob@example.com",
        "folder": "Inbox",
        "has_attachments": False,
        "email_type": "original",
    }
    chunks = chunk_email(email)
    assert "[Signature stripped]" in chunks[0].text
    assert "Important info here" in chunks[0].text
    assert chunks[0].metadata["has_signature"] == "True"


def test_chunk_email_no_signature_flag():
    email = {
        "uid": "nosig1",
        "message_id": "m2",
        "subject": "Test",
        "sender_name": "Alice",
        "sender_email": "alice@example.com",
        "to": ["bob@example.com"],
        "cc": [],
        "date": "2025-01-01",
        "body": "Just normal text without a sig.",
        "folder": "Inbox",
        "has_attachments": False,
        "email_type": "original",
    }
    chunks = chunk_email(email)
    assert "[Signature stripped]" not in chunks[0].text
    assert chunks[0].metadata["has_signature"] == "False"


def test_strip_signature_cordialement():
    body = "Veuillez trouver ci-joint le document.\n\nCordialement,\nMarie Dupont"
    stripped, had_sig = strip_signature(body)
    assert had_sig is True
    assert "Veuillez trouver" in stripped
    assert "Marie Dupont" not in stripped


def test_strip_signature_atentamente():
    body = "Le envío el informe.\n\nAtentamente,\nCarlos García"
    stripped, had_sig = strip_signature(body)
    assert had_sig is True
    assert "informe" in stripped


def test_strip_signature_get_outlook_ios():
    body = "Please see the attached file.\n\nGet Outlook for iOS"
    stripped, had_sig = strip_signature(body)
    assert had_sig is True
    assert stripped == "Please see the attached file."


def test_strip_signature_get_outlook_android():
    body = "Done.\n\nGet Outlook for Android"
    stripped, had_sig = strip_signature(body)
    assert had_sig is True
    assert stripped == "Done."
