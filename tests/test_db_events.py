"""Tests for EventMixin in db_events.py (coverage track)."""

from __future__ import annotations

import hashlib
import os
import tempfile

import pytest

from src.email_db import EmailDatabase

_BODY = "event test email body"


@pytest.fixture()
def db() -> EmailDatabase:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        database = EmailDatabase(db_path)
        yield database
        database.close()


def _insert_email(db: EmailDatabase, uid: str = "uid1") -> None:
    """Insert a minimal email row so FK constraints are satisfied."""
    db.conn.execute(
        """INSERT OR IGNORE INTO emails
           (uid, message_id, subject, sender_name, sender_email,
            date, folder, body_text, body_html, has_attachments, attachment_count,
            priority, is_read, body_length, content_sha256)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            uid,
            f"<{uid}@test>",
            "Subject",
            "Sender",
            f"{uid}@test.invalid",
            "2024-01-01",
            "Inbox",
            _BODY,
            "",
            0,
            0,
            0,
            1,
            len(_BODY),
            hashlib.sha256(_BODY.encode()).hexdigest(),
        ),
    )
    db.conn.commit()


def _row(
    key: str = "key1",
    uid: str = "uid1",
    kind: str = "absence",
    source_scope: str = "email",
    surface_scope: str = "body",
    segment_ordinal: int | None = 0,
    char_start: int | None = 10,
    char_end: int | None = 30,
    trigger_text: str = "was excluded",
    event_date: str = "2024-03-01",
    surface_hash: str = "aaa",
    lang: str = "en",
    confidence: float = 0.9,
    extractor_version: str = "1.0",
    provenance_json: str | None = None,
) -> tuple[object, ...]:
    return (
        key,
        uid,
        kind,
        source_scope,
        surface_scope,
        segment_ordinal,
        char_start,
        char_end,
        trigger_text,
        event_date,
        surface_hash,
        lang,
        confidence,
        extractor_version,
        provenance_json,
    )


class TestUpsertEventRecords:
    def test_empty_rows_returns_zero(self, db: EmailDatabase) -> None:
        assert db.upsert_event_records([]) == 0

    def test_single_row_inserted(self, db: EmailDatabase) -> None:
        _insert_email(db, "uid1")
        count = db.upsert_event_records([_row()])
        assert count == 1

    def test_multiple_rows_inserted(self, db: EmailDatabase) -> None:
        _insert_email(db, "u1")
        _insert_email(db, "u2")
        rows = [_row("k1", "u1"), _row("k2", "u2")]
        assert db.upsert_event_records(rows) == 2

    def test_upsert_on_conflict_updates_fields(self, db: EmailDatabase) -> None:
        _insert_email(db, "uid1")
        db.upsert_event_records([_row("key1", trigger_text="original")])
        db.upsert_event_records([_row("key1", trigger_text="updated")])
        result = db.event_records_for_email("uid1")
        assert len(result) == 1
        assert result[0]["trigger_text"] == "updated"

    def test_commit_false_does_not_persist(self, db: EmailDatabase) -> None:
        _insert_email(db, "uid1")
        db.upsert_event_records([_row("k-nocommit")], commit=False)
        # Without commit, row is still in the connection's transaction
        rows = db.conn.execute("SELECT * FROM event_records WHERE event_key='k-nocommit'").fetchall()
        assert len(rows) == 1  # visible in same connection before commit
        db.conn.rollback()
        rows_after = db.conn.execute("SELECT * FROM event_records WHERE event_key='k-nocommit'").fetchall()
        assert len(rows_after) == 0

    def test_returns_inserted_count(self, db: EmailDatabase) -> None:
        _insert_email(db, "uid1")
        assert db.upsert_event_records([_row("a"), _row("b"), _row("c")]) == 3


class TestEventRecordsForEmail:
    def test_returns_empty_for_unknown_uid(self, db: EmailDatabase) -> None:
        assert db.event_records_for_email("unknown") == []

    def test_returns_events_for_uid(self, db: EmailDatabase) -> None:
        _insert_email(db, "uid_a")
        _insert_email(db, "uid_b")
        db.upsert_event_records([_row("k1", "uid_a"), _row("k2", "uid_b")])
        result = db.event_records_for_email("uid_a")
        assert len(result) == 1
        assert result[0]["event_key"] == "k1"

    def test_ordered_by_segment_then_char_start(self, db: EmailDatabase) -> None:
        _insert_email(db, "u1")
        db.upsert_event_records(
            [
                _row("k1", "u1", segment_ordinal=2, char_start=5),
                _row("k2", "u1", segment_ordinal=1, char_start=99),
            ]
        )
        result = db.event_records_for_email("u1")
        assert result[0]["event_key"] == "k2"  # segment 1 first
        assert result[1]["event_key"] == "k1"

    def test_limit_applied(self, db: EmailDatabase) -> None:
        _insert_email(db, "u1")
        for i in range(5):
            db.upsert_event_records([_row(f"k{i}", "u1")])
        result = db.event_records_for_email("u1", limit=2)
        assert len(result) == 2

    def test_limit_floor_at_one(self, db: EmailDatabase) -> None:
        _insert_email(db, "u1")
        db.upsert_event_records([_row("k1", "u1"), _row("k2", "u1")])
        result = db.event_records_for_email("u1", limit=0)
        assert len(result) >= 1

    def test_returns_dict(self, db: EmailDatabase) -> None:
        _insert_email(db, "uid1")
        db.upsert_event_records([_row()])
        result = db.event_records_for_email("uid1")
        assert isinstance(result[0], dict)
        assert "event_key" in result[0]
        assert "event_kind" in result[0]


class TestEventRecordsForUids:
    def test_empty_uids_returns_empty(self, db: EmailDatabase) -> None:
        assert db.event_records_for_uids([]) == {}

    def test_groups_by_uid(self, db: EmailDatabase) -> None:
        _insert_email(db, "uid_a")
        _insert_email(db, "uid_b")
        db.upsert_event_records([_row("k1", "uid_a"), _row("k2", "uid_b"), _row("k3", "uid_a")])
        result = db.event_records_for_uids(["uid_a", "uid_b"])
        assert len(result["uid_a"]) == 2
        assert len(result["uid_b"]) == 1

    def test_unknown_uid_returns_empty_list(self, db: EmailDatabase) -> None:
        result = db.event_records_for_uids(["nonexistent"])
        assert result == {"nonexistent": []}

    def test_limit_per_uid(self, db: EmailDatabase) -> None:
        _insert_email(db, "u1")
        for i in range(10):
            db.upsert_event_records([_row(f"k{i}", "u1")])
        result = db.event_records_for_uids(["u1"], limit_per_uid=3)
        assert len(result["u1"]) == 3

    def test_limit_per_uid_floor_at_one(self, db: EmailDatabase) -> None:
        _insert_email(db, "u1")
        db.upsert_event_records([_row("k1", "u1"), _row("k2", "u1")])
        result = db.event_records_for_uids(["u1"], limit_per_uid=0)
        assert len(result["u1"]) >= 1

    def test_mixed_uids_with_no_events(self, db: EmailDatabase) -> None:
        _insert_email(db, "u_has_events")
        db.upsert_event_records([_row("k1", "u_has_events")])
        result = db.event_records_for_uids(["u_has_events", "u_empty"])
        assert len(result["u_has_events"]) == 1
        assert result["u_empty"] == []
