"""Database and schema regression tests split out from the RF8 catch-all."""

from __future__ import annotations

import sqlite3

import pytest

from src.email_db import EmailDatabase

from ._bugfix_regression_cases import make_email


class TestP0ContactUpsertNullDates:
    """P0 fix #1: MIN/MAX with NULL/empty dates in contact upserts."""

    def test_first_insert_with_empty_date_then_real_date(self):
        db = EmailDatabase(":memory:")
        db.insert_email(make_email(message_id="<m1@ex>", date=""))
        db.insert_email(make_email(message_id="<m2@ex>", date="2024-06-01T10:00:00"))

        contact = db.conn.execute(
            "SELECT first_seen, last_seen FROM contacts WHERE email_address = 'employee@example.test'"
        ).fetchone()
        assert contact["first_seen"] == "2024-06-01T10:00:00"
        assert contact["last_seen"] == "2024-06-01T10:00:00"
        db.close()

    def test_first_insert_with_real_date_then_empty(self):
        db = EmailDatabase(":memory:")
        db.insert_email(make_email(message_id="<m1@ex>", date="2024-03-01T08:00:00"))
        db.insert_email(make_email(message_id="<m2@ex>", date=""))

        contact = db.conn.execute(
            "SELECT first_seen, last_seen FROM contacts WHERE email_address = 'employee@example.test'"
        ).fetchone()
        assert contact["first_seen"] == "2024-03-01T08:00:00"
        assert contact["last_seen"] == "2024-03-01T08:00:00"
        db.close()

    def test_min_max_with_two_valid_dates(self):
        db = EmailDatabase(":memory:")
        db.insert_email(make_email(message_id="<m1@ex>", date="2024-06-01T10:00:00"))
        db.insert_email(make_email(message_id="<m2@ex>", date="2024-01-01T08:00:00"))

        contact = db.conn.execute(
            "SELECT first_seen, last_seen FROM contacts WHERE email_address = 'employee@example.test'"
        ).fetchone()
        assert contact["first_seen"] == "2024-01-01T08:00:00"
        assert contact["last_seen"] == "2024-06-01T10:00:00"
        db.close()

    def test_communication_edge_null_dates(self):
        db = EmailDatabase(":memory:")
        db.insert_email(make_email(message_id="<m1@ex>", date=""))
        db.insert_email(make_email(message_id="<m2@ex>", date="2024-05-15T12:00:00"))

        edge = db.conn.execute(
            "SELECT first_date, last_date FROM communication_edges WHERE sender_email = 'employee@example.test'"
        ).fetchone()
        assert edge["first_date"] == "2024-05-15T12:00:00"
        assert edge["last_date"] == "2024-05-15T12:00:00"
        db.close()


class TestP1AtomicCustodyLogging:
    """P1 fix #4: atomic custody logging (rollback on failure)."""

    def test_add_evidence_rolls_back_on_custody_failure(self):
        db = EmailDatabase(":memory:")
        email = make_email(body_text="Important evidence text")
        db.insert_email(email)

        original_log = db.log_custody_event

        def failing_log(*args, **kwargs):
            raise RuntimeError("Simulated custody log failure")

        db.log_custody_event = failing_log

        with pytest.raises(RuntimeError, match="Simulated"):
            db.add_evidence(
                email.uid,
                "harassment",
                "Important evidence text",
                "summary",
                5,
            )

        count = db.conn.execute("SELECT COUNT(*) FROM evidence_items").fetchone()[0]
        assert count == 0

        db.log_custody_event = original_log
        result = db.add_evidence(email.uid, "harassment", "Important evidence text", "summary", 5)
        assert result["id"] is not None
        db.close()


class TestP1VerifyEvidenceOrphaned:
    """P1 fix #5: verify_evidence_quotes LEFT JOIN for orphaned items."""

    def test_orphaned_evidence_detected(self):
        db = EmailDatabase(":memory:")
        email = make_email(body_text="The evidence quote")
        db.insert_email(email)
        db.add_evidence(email.uid, "harassment", "The evidence quote", "summary", 4)

        db.conn.execute("PRAGMA foreign_keys=OFF")
        db.conn.execute("DELETE FROM recipients WHERE email_uid = ?", (email.uid,))
        db.conn.execute("DELETE FROM emails WHERE uid = ?", (email.uid,))
        db.conn.commit()
        db.conn.execute("PRAGMA foreign_keys=ON")

        verification = db.verify_evidence_quotes()
        assert verification["orphaned"] == 1
        assert verification["total"] == 1
        assert any(f.get("orphaned") for f in verification["failures"])
        db.close()

    def test_mixed_orphaned_and_valid(self):
        db = EmailDatabase(":memory:")
        first = make_email(message_id="<m1@ex>", body_text="Quote one text")
        second = make_email(message_id="<m2@ex>", body_text="Quote two text")
        db.insert_email(first)
        db.insert_email(second)
        db.add_evidence(first.uid, "harassment", "Quote one text", "summary", 4)
        db.add_evidence(second.uid, "harassment", "Quote two text", "summary", 3)

        db.conn.execute("PRAGMA foreign_keys=OFF")
        db.conn.execute("DELETE FROM recipients WHERE email_uid = ?", (second.uid,))
        db.conn.execute("DELETE FROM emails WHERE uid = ?", (second.uid,))
        db.conn.commit()
        db.conn.execute("PRAGMA foreign_keys=ON")

        verification = db.verify_evidence_quotes()
        assert verification["verified"] == 1
        assert verification["orphaned"] == 1
        assert verification["total"] == 2
        db.close()


class TestP3DateRangeExcludesEmptyStrings:
    """P3: date_range() must use NULLIF to exclude empty date strings."""

    def test_empty_dates_excluded_from_range(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE emails (date TEXT, sender_email TEXT, sender_name TEXT, folder TEXT)")
        conn.execute("INSERT INTO emails VALUES ('', 'a@example.test', 'A', 'Inbox')")
        conn.execute("INSERT INTO emails VALUES ('2024-03-15', 'b@example.test', 'B', 'Inbox')")
        conn.execute("INSERT INTO emails VALUES ('2024-06-20', 'c@example.test', 'C', 'Inbox')")
        conn.commit()

        row = conn.execute("SELECT MIN(NULLIF(date, '')) AS min_d, MAX(NULLIF(date, '')) AS max_d FROM emails").fetchone()
        assert row["min_d"] == "2024-03-15"
        assert row["max_d"] == "2024-06-20"
        conn.close()
