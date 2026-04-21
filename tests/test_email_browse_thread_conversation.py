"""Thread and conversation browse tests split from the RF10 catch-all."""

from __future__ import annotations

from src.email_db import EmailDatabase
from tests._email_browse_cases import make_email


def test_get_thread_emails_ordered_by_date():
    db = EmailDatabase(":memory:")
    db.insert_email(
        make_email(
            message_id="<m1@ex.com>",
            date="2024-01-10T10:00:00",
            conversation_id="conv_A",
            body_text="First",
        )
    )
    db.insert_email(
        make_email(
            message_id="<m2@ex.com>",
            date="2024-01-12T10:00:00",
            conversation_id="conv_A",
            body_text="Third",
        )
    )
    db.insert_email(
        make_email(
            message_id="<m3@ex.com>",
            date="2024-01-11T10:00:00",
            conversation_id="conv_A",
            body_text="Second",
        )
    )

    thread = db.get_thread_emails("conv_A")
    assert len(thread) == 3
    assert thread[0]["body_text"] == "First"
    assert thread[1]["body_text"] == "Second"
    assert thread[2]["body_text"] == "Third"
    db.close()


def test_get_thread_emails_includes_recipients():
    db = EmailDatabase(":memory:")
    db.insert_email(
        make_email(
            conversation_id="conv_B",
            to=["Bob <bob@example.com>"],
            cc=["Carol <carol@example.com>"],
        )
    )
    thread = db.get_thread_emails("conv_B")
    assert len(thread) == 1
    assert len(thread[0]["to"]) == 1
    assert len(thread[0]["cc"]) == 1
    db.close()


def test_get_thread_emails_empty_conversation_id():
    db = EmailDatabase(":memory:")
    assert db.get_thread_emails("") == []
    assert db.get_thread_emails("nonexistent_conv") == []
    db.close()


def test_get_thread_emails_only_matching_conversation():
    db = EmailDatabase(":memory:")
    db.insert_email(make_email(message_id="<m1@ex.com>", conversation_id="conv_A"))
    db.insert_email(make_email(message_id="<m2@ex.com>", conversation_id="conv_B"))

    thread_a = db.get_thread_emails("conv_A")
    assert len(thread_a) == 1
    db.close()
