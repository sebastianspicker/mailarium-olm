"""Bounded analytics reads retain surface order and resume past empty messages."""

from __future__ import annotations

from mailarium.archive import open_archive_database
from mailarium.ingestion.maintenance import reingest_analytics
from mailarium.ingestion.records import ParsedMessage


def _email(index: int, body: str = "The project delivery is ready for the team to review.") -> ParsedMessage:
    return ParsedMessage(
        message_id=f"analytics-{index}@example.test",
        subject="Synthetic analytics",
        sender_name="Sender",
        sender_email="sender@example.test",
        to=[],
        cc=[],
        bcc=[],
        date="2026-09-01T12:00:00",
        body_text=body,
        body_html="",
        folder="Inbox",
        has_attachments=False,
    )


def test_batched_surfaces_match_original_aggregate_order_and_are_bounded(tmp_path) -> None:
    with open_archive_database(str(tmp_path / "archive.db")) as db:
        emails = [_email(index) for index in range(5)]
        db.messages.insert_emails_batch(emails)
        uid = emails[0].uid
        db.conn.execute("DELETE FROM message_segments WHERE email_uid=?", (uid,))
        db.conn.executemany(
            "INSERT INTO message_segments(email_uid,ordinal,segment_type,text,source_surface) VALUES(?,?,?,?,?)",
            [
                (uid, ordinal, kind, text, "body_text")
                for ordinal, kind, text in (
                    (3, "authored_body", "Second authored"),
                    (1, "authored_body", "First authored"),
                    (4, "quoted_reply", "Reply"),
                    (5, "forwarded_message", "Forward"),
                    (2, "header_block", "Header"),
                )
            ],
        )
        db.conn.execute("INSERT INTO attachments(email_uid,name,normalized_text) VALUES(?,?,?)", (uid, "safe.txt", "Attachment"))
        db.conn.commit()
        statements = []
        db.conn.set_trace_callback(statements.append)
        batches = list(db.analytics.iter_analytics_batches(batch_size=2))
        db.conn.set_trace_callback(None)
        assert [len(batch) for batch in batches] == [2, 2, 1]
        assert len({row["uid"] for batch in batches for row in batch}) == 5
        row = next(row for batch in batches for row in batch if row["uid"] == uid)
        assert row["authored_segment_text"] == "First authored\nSecond authored"
        assert row["authored_segment_ordinal"] == 1
        assert row["quoted_segment_text"] == "Reply\nForward"
        assert row["quoted_segment_ordinal"] == 4
        assert row["forwarded_header_text"] == "Header"
        assert row["segment_text"] == "First authored\nHeader\nSecond authored\nReply\nForward"
        assert row["attachment_text"] == "Attachment"
        assert sum("FROM message_segments WHERE" in statement for statement in statements) == 3
        assert sum("FROM attachments WHERE" in statement for statement in statements) == 3


def test_analytics_backfill_crosses_pages_and_repeated_runs_preserve_results(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MAILARIUM_ALLOWED_RUNTIME_ROOTS", str(tmp_path))
    path = str(tmp_path / "archive.db")
    with open_archive_database(path) as db:
        db.messages.insert_emails_batch([_email(index) for index in range(260)])
    first = reingest_analytics(path)
    assert first["updated"] == first["total_missing"] == 260
    assert first["surface_rows_upserted"] >= 260
    second = reingest_analytics(path)
    assert second["updated"] == second["total_missing"] == 0
