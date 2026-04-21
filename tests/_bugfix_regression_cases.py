from __future__ import annotations

from src.parse_olm import Email
from src.retriever import EmailRetriever, SearchResult


def make_email(**overrides) -> Email:
    defaults = {
        "message_id": "<msg1@example.com>",
        "subject": "Hello",
        "sender_name": "Alice",
        "sender_email": "alice@example.com",
        "to": ["Bob <bob@example.com>"],
        "cc": [],
        "bcc": [],
        "date": "2024-01-15T10:30:00",
        "body_text": "Test body",
        "body_html": "",
        "folder": "Inbox",
        "has_attachments": False,
    }
    defaults.update(overrides)
    return Email(**defaults)


def make_result(
    chunk_id: str = "c1",
    text: str = "body text",
    uid: str = "u1",
    date: str = "2024-01-01",
    distance: float = 0.1,
    **extra_meta,
) -> SearchResult:
    meta = {"uid": uid, "date": date, **extra_meta}
    return SearchResult(chunk_id=chunk_id, text=text, metadata=meta, distance=distance)


def bare_retriever(**attrs) -> EmailRetriever:
    retriever = EmailRetriever.__new__(EmailRetriever)
    retriever._email_db = None
    retriever._email_db_checked = True
    retriever.settings = None
    for key, value in attrs.items():
        setattr(retriever, key, value)
    return retriever
