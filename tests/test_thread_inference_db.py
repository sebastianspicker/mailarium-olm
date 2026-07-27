"""Persistence tests for inferred thread candidates."""

from mailarium.email_db import EmailDatabase

from .helpers.email_db_builders import make_inferred_parent_email, make_inferred_reply_email


def test_insert_email_persists_inferred_parent_and_edge():
    db = EmailDatabase(":memory:")
    parent = make_inferred_parent_email(conversation_id="conv-1")
    child = make_inferred_reply_email()

    db.insert_email(parent)
    db.insert_email(child)

    row = db.conn.execute(
        (
            "SELECT inferred_parent_uid, inferred_thread_id, inferred_match_reason, "
            "inferred_match_confidence FROM emails WHERE uid = ?"
        ),
        (child.uid,),
    ).fetchone()
    assert row["inferred_parent_uid"] == parent.uid
    assert row["inferred_thread_id"] == "conv-1"
    assert row["inferred_match_confidence"] >= 0.8
    assert "reply_context_from" in row["inferred_match_reason"]

    edge = db.conn.execute(
        "SELECT child_uid, parent_uid, edge_type, confidence FROM conversation_edges WHERE child_uid = ?",
        (child.uid,),
    ).fetchone()
    assert edge is not None
    assert edge["parent_uid"] == parent.uid
    assert edge["edge_type"] == "inferred"
    assert edge["confidence"] >= 0.8
    db.close()


def test_insert_emails_batch_does_not_duplicate_inferred_edges() -> None:
    db = EmailDatabase(":memory:")
    parent = make_inferred_parent_email(
        message_id="<parent-batch@example.com>",
        conversation_id="conv-batch-1",
    )
    child = make_inferred_reply_email(
        message_id="<child-batch@example.com>",
    )

    db.insert_emails_batch([parent, child])

    row = db.conn.execute(
        """SELECT COUNT(*) AS c
           FROM conversation_edges
           WHERE child_uid = ? AND parent_uid = ? AND edge_type = 'inferred'""",
        (child.uid, parent.uid),
    ).fetchone()
    assert row is not None
    assert row["c"] == 1
    db.close()
