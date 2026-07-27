"""Regression coverage for shared-connection transaction serialization."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from mailarium import email_db_persistence
from mailarium.email_db import EmailDatabase

from .helpers.email_db_builders import _make_email


def test_failed_write_cannot_rollback_concurrent_successful_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed transaction releases the operation lock before the next write begins."""
    db = EmailDatabase(":memory:")
    failing = _make_email(message_id="<failing@example.test>")
    succeeding = _make_email(message_id="<succeeding@example.test>")
    failure_entered = Event()
    release_failure = Event()
    success_entered = Event()
    original = email_db_persistence.persist_single_related_rows

    def fail_after_begin(cur, database, email) -> None:
        if email.uid == failing.uid:
            failure_entered.set()
            assert release_failure.wait(timeout=2)
            raise RuntimeError("forced persistence failure")
        success_entered.set()
        original(cur, database, email)

    monkeypatch.setattr(email_db_persistence, "persist_single_related_rows", fail_after_begin)

    with ThreadPoolExecutor(max_workers=2) as executor:
        failed_write = executor.submit(db.insert_email, failing)
        assert failure_entered.wait(timeout=2)
        successful_write = executor.submit(db.insert_email, succeeding)
        assert not success_entered.wait(timeout=0.1)
        release_failure.set()
        with pytest.raises(RuntimeError, match="forced persistence failure"):
            failed_write.result(timeout=2)
        assert successful_write.result(timeout=2) is True

    rows = db.conn.execute("SELECT uid FROM emails ORDER BY uid").fetchall()
    assert [row["uid"] for row in rows] == [succeeding.uid]
    db.close()


def test_operation_lock_is_reentrant() -> None:
    db = EmailDatabase(":memory:")

    with db.operation():
        assert db.email_count() == 0

    db.close()


def test_sparse_batch_does_not_commit_an_outer_transaction() -> None:
    db = EmailDatabase(":memory:")
    db.conn.execute("BEGIN IMMEDIATE")

    assert db.insert_sparse_batch(["chunk-1"], [{7: 0.75}]) == 1
    assert db.conn.in_transaction is True

    db.conn.rollback()
    assert db.sparse_vector_count() == 0
    db.close()
