"""Custody creation and schema tests split from RF16."""

from __future__ import annotations

import hashlib
import os
import tempfile

from src.email_db import EmailDatabase
from tests._custody_cases import FakeEmail


def test_schema_v4_creates_custody_chain_table(db: EmailDatabase) -> None:
    """Schema v4 should create custody_chain table."""
    row = db.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='custody_chain'").fetchone()
    assert row is not None


def test_schema_v4_adds_olm_sha256_column(db: EmailDatabase) -> None:
    """Schema v4 should add olm_sha256 column to ingestion_runs."""
    run_id = db.record_ingestion_start("test.olm", olm_sha256="abc123")
    row = db.conn.execute("SELECT olm_sha256 FROM ingestion_runs WHERE id=?", (run_id,)).fetchone()
    assert row["olm_sha256"] == "abc123"


def test_schema_v4_adds_file_size_bytes_column(db: EmailDatabase) -> None:
    """Schema v4 should add file_size_bytes column to ingestion_runs."""
    run_id = db.record_ingestion_start("test.olm", file_size_bytes=12345)
    row = db.conn.execute("SELECT file_size_bytes FROM ingestion_runs WHERE id=?", (run_id,)).fetchone()
    assert row["file_size_bytes"] == 12345


def test_schema_v4_adds_custodian_column(db: EmailDatabase) -> None:
    """Schema v4 should add custodian column to ingestion_runs."""
    run_id = db.record_ingestion_start("test.olm", custodian="admin")
    row = db.conn.execute("SELECT custodian FROM ingestion_runs WHERE id=?", (run_id,)).fetchone()
    assert row["custodian"] == "admin"


def test_schema_v4_adds_content_sha256_to_emails(db: EmailDatabase) -> None:
    """Schema v4 should add content_sha256 column to emails."""
    cols = [row[1] for row in db.conn.execute("PRAGMA table_info(emails)").fetchall()]
    assert "content_sha256" in cols


def test_schema_v4_adds_content_hash_to_evidence(db: EmailDatabase) -> None:
    """Schema v4 should add content_hash column to evidence_items."""
    cols = [row[1] for row in db.conn.execute("PRAGMA table_info(evidence_items)").fetchall()]
    assert "content_hash" in cols


def test_compute_content_hash_deterministic() -> None:
    """Same input should always produce the same hash."""
    h1 = EmailDatabase.compute_content_hash("hello world")
    h2 = EmailDatabase.compute_content_hash("hello world")
    assert h1 == h2
    assert len(h1) == 64


def test_compute_content_hash_different_inputs() -> None:
    """Different inputs should produce different hashes."""
    h1 = EmailDatabase.compute_content_hash("input A")
    h2 = EmailDatabase.compute_content_hash("input B")
    assert h1 != h2


def test_log_custody_event_returns_id(db: EmailDatabase) -> None:
    """log_custody_event should return an auto-increment ID."""
    event_id = db.log_custody_event("test_action")
    assert isinstance(event_id, int)
    assert event_id >= 1


def test_log_custody_event_stores_all_fields(db: EmailDatabase) -> None:
    """All custody fields should be persisted correctly."""
    event_id = db.log_custody_event(
        "evidence_add",
        target_type="evidence",
        target_id="42",
        details={"category": "harassment", "relevance": 5},
        content_hash="abcdef1234567890",
        actor="admin",
    )
    events = db.get_custody_chain()
    event = next(e for e in events if e["id"] == event_id)
    assert event["action"] == "evidence_add"
    assert event["target_type"] == "evidence"
    assert event["target_id"] == "42"
    assert event["details"]["category"] == "harassment"
    assert event["content_hash"] == "abcdef1234567890"
    assert event["actor"] == "admin"


def test_record_ingestion_start_logs_custody_event(db: EmailDatabase) -> None:
    """record_ingestion_start should auto-log a custody event."""
    run_id = db.record_ingestion_start(
        "test.olm",
        olm_sha256="deadbeef",
        file_size_bytes=9999,
        custodian="tester",
    )

    events = db.get_custody_chain(target_type="ingestion_run", target_id=str(run_id))
    assert len(events) >= 1
    event = events[0]
    assert event["action"] == "ingest_start"
    assert event["details"]["olm_sha256"] == "deadbeef"
    assert event["details"]["file_size_bytes"] == 9999
    assert event["actor"] == "tester"
    assert event["content_hash"] == "deadbeef"


def test_record_ingestion_start_default_custodian(db: EmailDatabase) -> None:
    """Default custodian should be system."""
    run_id = db.record_ingestion_start("test.olm")
    row = db.conn.execute("SELECT custodian FROM ingestion_runs WHERE id=?", (run_id,)).fetchone()
    assert row["custodian"] == "system"


def test_insert_emails_batch_computes_content_sha256(db: EmailDatabase) -> None:
    """insert_emails_batch should compute content_sha256 per email."""
    inserted = db.insert_emails_batch([FakeEmail()])
    assert len(inserted) == 1

    row = db.conn.execute("SELECT content_sha256 FROM emails WHERE uid='fake-uid'").fetchone()
    assert row["content_sha256"] is not None
    assert row["content_sha256"] == hashlib.sha256(b"Hello world email content").hexdigest()


def test_hash_file_sha256() -> None:
    """_hash_file_sha256 should compute correct SHA-256 of a file."""
    from src.ingest import _hash_file_sha256

    with tempfile.NamedTemporaryFile(delete=False, suffix=".olm") as file_obj:
        file_obj.write(b"test file content for hashing")
        file_obj.flush()
        path = file_obj.name

    try:
        result = _hash_file_sha256(path)
        expected = hashlib.sha256(b"test file content for hashing").hexdigest()
        assert result == expected
    finally:
        os.unlink(path)


def test_hash_file_sha256_large_file() -> None:
    """_hash_file_sha256 should handle files larger than one read chunk."""
    from src.ingest import _hash_file_sha256

    data = b"x" * 20000
    with tempfile.NamedTemporaryFile(delete=False, suffix=".olm") as file_obj:
        file_obj.write(data)
        file_obj.flush()
        path = file_obj.name

    try:
        result = _hash_file_sha256(path)
        expected = hashlib.sha256(data).hexdigest()
        assert result == expected
    finally:
        os.unlink(path)
