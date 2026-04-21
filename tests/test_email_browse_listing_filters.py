"""Listing and filter tests split from the RF10 browse catch-all."""

from __future__ import annotations

from src.email_db import EmailDatabase
from tests._email_browse_cases import make_email, seed_db


def test_paginated_returns_correct_structure():
    db = EmailDatabase(":memory:")
    seed_db(db, 5)

    page = db.list_emails_paginated(offset=0, limit=20)
    assert "emails" in page
    assert "total" in page
    assert "offset" in page
    assert "limit" in page
    assert page["total"] == 5
    assert len(page["emails"]) == 5
    db.close()


def test_paginated_respects_limit():
    db = EmailDatabase(":memory:")
    seed_db(db, 10)

    page = db.list_emails_paginated(offset=0, limit=3)
    assert len(page["emails"]) == 3
    assert page["total"] == 10
    db.close()


def test_paginated_respects_offset():
    db = EmailDatabase(":memory:")
    seed_db(db, 5)

    page1 = db.list_emails_paginated(offset=0, limit=2, sort_order="ASC")
    page2 = db.list_emails_paginated(offset=2, limit=2, sort_order="ASC")

    uids1 = {email["uid"] for email in page1["emails"]}
    uids2 = {email["uid"] for email in page2["emails"]}
    assert uids1.isdisjoint(uids2)
    db.close()


def test_paginated_sort_order_desc():
    db = EmailDatabase(":memory:")
    seed_db(db, 5)

    page = db.list_emails_paginated(sort_order="DESC")
    dates = [email["date"] for email in page["emails"]]
    assert dates == sorted(dates, reverse=True)
    db.close()


def test_paginated_sort_order_asc():
    db = EmailDatabase(":memory:")
    seed_db(db, 5)

    page = db.list_emails_paginated(sort_order="ASC")
    dates = [email["date"] for email in page["emails"]]
    assert dates == sorted(dates)
    db.close()


def test_paginated_filter_by_folder():
    db = EmailDatabase(":memory:")
    seed_db(db, 6)

    page = db.list_emails_paginated(folder="Inbox")
    assert page["total"] == 3
    for email in page["emails"]:
        assert email["folder"] == "Inbox"
    db.close()


def test_paginated_filter_by_sender():
    db = EmailDatabase(":memory:")
    seed_db(db, 5)

    page = db.list_emails_paginated(sender="sender2@example.com")
    assert page["total"] == 1
    assert page["emails"][0]["sender_email"] == "sender2@example.com"
    db.close()


def test_paginated_empty_result():
    db = EmailDatabase(":memory:")
    page = db.list_emails_paginated()
    assert page["total"] == 0
    assert page["emails"] == []
    db.close()


def test_paginated_invalid_sort_by_defaults_to_date():
    db = EmailDatabase(":memory:")
    seed_db(db, 3)

    page = db.list_emails_paginated(sort_by="nonexistent_column")
    assert page["total"] == 3
    db.close()


def test_paginated_includes_conversation_id():
    db = EmailDatabase(":memory:")
    db.insert_email(make_email(conversation_id="conv_XYZ"))

    page = db.list_emails_paginated()
    assert page["emails"][0]["conversation_id"] == "conv_XYZ"
    db.close()


def test_paginated_date_from_filter():
    db = EmailDatabase(":memory:")
    db.insert_email(make_email(message_id="<old@ex.com>", date="2024-01-10T08:00:00"))
    db.insert_email(make_email(message_id="<new@ex.com>", date="2024-01-20T08:00:00"))

    page = db.list_emails_paginated(date_from="2024-01-15")
    assert page["total"] == 1
    assert page["emails"][0]["date"] == "2024-01-20T08:00:00"
    db.close()


def test_paginated_date_to_filter():
    db = EmailDatabase(":memory:")
    db.insert_email(make_email(message_id="<old@ex.com>", date="2024-01-10T08:00:00"))
    db.insert_email(make_email(message_id="<new@ex.com>", date="2024-01-20T08:00:00"))

    page = db.list_emails_paginated(date_to="2024-01-10")
    assert page["total"] == 1
    assert page["emails"][0]["date"] == "2024-01-10T08:00:00"
    db.close()


def test_paginated_date_range_filter():
    db = EmailDatabase(":memory:")
    db.insert_email(make_email(message_id="<e1@ex.com>", date="2024-01-05T08:00:00"))
    db.insert_email(make_email(message_id="<e2@ex.com>", date="2024-01-15T08:00:00"))
    db.insert_email(make_email(message_id="<e3@ex.com>", date="2024-01-25T08:00:00"))

    page = db.list_emails_paginated(date_from="2024-01-10", date_to="2024-01-20")
    assert page["total"] == 1
    assert page["emails"][0]["date"] == "2024-01-15T08:00:00"
    db.close()
