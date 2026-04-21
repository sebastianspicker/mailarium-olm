from __future__ import annotations

import threading

from src.chunker import _split_text, chunk_email
from src.parse_olm import BODY_NORMALIZATION_VERSION


def test_long_header_does_not_break_chunking():
    email = {
        "uid": "123",
        "message_id": "m",
        "subject": "Subject " + ("x" * 2000),
        "sender_name": "Sender",
        "sender_email": "sender@example.com",
        "to": ["to@example.com"],
        "cc": [],
        "date": "2023-01-01",
        "body": "Body paragraph. " * 200,
        "folder": "Inbox",
        "has_attachments": False,
    }

    chunks = chunk_email(email)
    assert len(chunks) >= 1
    assert all(chunk.text for chunk in chunks)


def test_splitter_makes_progress_for_boundary_breaks():
    text = ("x" * 150) + "\n\n" + ("y" * 600)
    result = {"chunks": None}

    def run() -> None:
        result["chunks"] = _split_text(text, max_len=300, overlap=200)

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(0.5)

    assert not worker.is_alive()
    assert result["chunks"] is not None
    assert len(result["chunks"]) >= 2


def test_short_email_stays_single_chunk():
    email = {
        "uid": "1",
        "message_id": "m1",
        "subject": "Short",
        "sender_name": "S",
        "sender_email": "s@example.com",
        "to": [],
        "cc": [],
        "date": "2023-01-01",
        "body": "tiny body",
        "folder": "Inbox",
        "has_attachments": False,
    }

    chunks = chunk_email(email)
    assert len(chunks) == 1
    assert chunks[0].chunk_id == "1__0"


def test_multi_chunk_header_once():
    email = {
        "uid": "hdr1",
        "message_id": "m1",
        "subject": "Important Discussion",
        "sender_name": "Alice",
        "sender_email": "alice@example.com",
        "to": ["bob@example.com"],
        "cc": [],
        "date": "2025-01-01",
        "body": "Paragraph text. " * 300,
        "folder": "Inbox",
        "has_attachments": False,
        "email_type": "original",
    }

    chunks = chunk_email(email)
    assert len(chunks) >= 2
    assert "From:" in chunks[0].text
    assert "Date:" in chunks[0].text
    assert "Subject:" in chunks[0].text
    assert "Date:" not in chunks[1].text or "Date: 2025-01-01" in chunks[1].text
    assert "[Important Discussion - Part 2/" in chunks[1].text
    assert "From: Alice <alice@example.com> | Date:" in chunks[1].text


def test_chunk_metadata_includes_new_fields():
    email = {
        "uid": "meta1",
        "message_id": "m1",
        "subject": "RE: Test",
        "sender_name": "Alice",
        "sender_email": "alice@example.com",
        "to": ["bob@example.com"],
        "cc": ["carol@example.com"],
        "date": "2025-01-01",
        "body": "short body",
        "folder": "Inbox",
        "has_attachments": True,
        "attachment_names": ["report.pdf"],
        "conversation_id": "conv-123",
        "in_reply_to": "msg-456",
        "email_type": "reply",
        "base_subject": "Test",
        "priority": 2,
    }

    chunks = chunk_email(email)
    meta = chunks[0].metadata
    assert meta["conversation_id"] == "conv-123"
    assert meta["in_reply_to"] == "msg-456"
    assert meta["email_type"] == "reply"
    assert meta["base_subject"] == "Test"
    assert meta["priority"] == "2"
    assert meta["attachment_names"] == "report.pdf"


def test_cc_in_embedding_header():
    email = {
        "uid": "cc1",
        "message_id": "m1",
        "subject": "CC Test",
        "sender_name": "Alice",
        "sender_email": "alice@example.com",
        "to": ["bob@example.com"],
        "cc": ["carol@example.com", "dave@example.com"],
        "date": "2025-01-01",
        "body": "Check this out",
        "folder": "Inbox",
        "has_attachments": False,
    }

    chunks = chunk_email(email)
    assert "CC: carol@example.com, dave@example.com" in chunks[0].text


def test_chunk_email_strips_quoted_in_reply():
    email = {
        "uid": "q1",
        "message_id": "m1",
        "subject": "RE: Question",
        "sender_name": "Bob",
        "sender_email": "bob@example.com",
        "to": ["alice@example.com"],
        "cc": [],
        "date": "2025-01-01",
        "body": "Yes, I agree.\n\n----- Original Message -----\nFrom: Alice\n\nDo you agree?",
        "folder": "Inbox",
        "has_attachments": False,
        "email_type": "reply",
    }

    chunks = chunk_email(email)
    assert len(chunks) == 1
    assert "Yes, I agree" in chunks[0].text
    assert "Do you agree" not in chunks[0].text
    assert "[Quoted:" in chunks[0].text


def test_continuation_chunks_have_context_header():
    email = {
        "uid": "ctx1",
        "message_id": "m1",
        "subject": "Budget Review",
        "sender_name": "Alice",
        "sender_email": "alice@example.com",
        "to": ["bob@example.com"],
        "cc": [],
        "date": "2025-03-01",
        "body": "Paragraph text. " * 300,
        "folder": "Inbox",
        "has_attachments": False,
        "email_type": "original",
    }

    chunks = chunk_email(email)
    assert len(chunks) >= 2

    text = chunks[1].text
    assert "From: Alice <alice@example.com>" in text
    assert "Date: 2025-03-01" in text
    assert "Subject: Budget Review" in text
    assert "[Budget Review - Part 2/" in text


def test_continuation_chunks_context_header_partial_fields():
    email = {
        "uid": "ctx2",
        "message_id": "m2",
        "subject": "Test",
        "sender_name": "",
        "sender_email": "anon@example.com",
        "to": [],
        "cc": [],
        "date": "",
        "body": "Word " * 500,
        "folder": "Inbox",
        "has_attachments": False,
    }

    chunks = chunk_email(email)
    assert len(chunks) >= 2

    text = chunks[1].text
    assert "From: anon@example.com" in text
    assert "Date:" not in text


def test_chunk_includes_categories_in_metadata():
    email_dict = {
        "uid": "cat1",
        "message_id": "",
        "subject": "Category test",
        "sender_name": "Alice",
        "sender_email": "alice@example.com",
        "to": [],
        "cc": [],
        "bcc": [],
        "date": "2025-01-01",
        "body": "Test body",
        "folder": "Inbox",
        "has_attachments": False,
        "attachment_names": [],
        "conversation_id": "",
        "in_reply_to": "",
        "email_type": "original",
        "base_subject": "Category test",
        "priority": 0,
        "categories": ["Meeting", "Finance"],
        "is_calendar_message": False,
        "thread_topic": "Budget Q4",
        "inference_classification": "Focused",
    }
    chunks = chunk_email(email_dict)
    assert len(chunks) >= 1
    meta = chunks[0].metadata
    assert meta["categories"] == "Meeting, Finance"
    assert meta["thread_topic"] == "Budget Q4"
    assert meta["inference_classification"] == "Focused"
    assert meta["is_calendar_message"] == "False"


def test_chunk_includes_categories_in_text():
    email_dict = {
        "uid": "cat2",
        "message_id": "",
        "subject": "Cat text test",
        "sender_name": "",
        "sender_email": "a@b.com",
        "to": [],
        "cc": [],
        "bcc": [],
        "date": "",
        "body": "Body content",
        "folder": "Inbox",
        "has_attachments": False,
        "attachment_names": [],
        "conversation_id": "",
        "in_reply_to": "",
        "email_type": "original",
        "base_subject": "Cat text test",
        "priority": 0,
        "categories": ["Project X"],
        "is_calendar_message": True,
        "thread_topic": "",
        "inference_classification": "",
    }
    chunks = chunk_email(email_dict)
    text = chunks[0].text
    assert "Categories: Project X" in text
    assert "[Calendar/Meeting]" in text


def test_chunk_email_no_duplicate_categories():
    email_dict = {
        "uid": "test-uid",
        "subject": "Meeting Notes",
        "sender_name": "Alice",
        "sender_email": "alice@example.com",
        "date": "2024-01-15",
        "folder": "Inbox",
        "body": "Important discussion about Q4 budget and resources.",
        "to": ["Bob <bob@example.com>"],
        "cc": [],
        "bcc": [],
        "has_attachments": True,
        "attachment_names": ["report.pdf"],
        "categories": ["Finance", "Important"],
        "is_calendar_message": True,
        "email_type": "original",
    }
    chunks = chunk_email(email_dict)
    assert len(chunks) >= 1
    text = chunks[0].text
    assert text.count("Categories:") == 1
    assert text.count("[Calendar/Meeting]") == 1
    assert text.count("Attachments:") == 1


def test_body_text_stored_normalization_version_constant_stays_importable():
    assert BODY_NORMALIZATION_VERSION
