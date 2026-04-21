import queue
import threading
import time

import pytest

from src.ingest import _SENTINEL, _EmbedPipeline, main, parse_args


def test_parse_args_rejects_non_positive_batch_size():
    with pytest.raises(SystemExit):
        parse_args(["data/file.olm", "--batch-size", "0"])


def test_parse_args_rejects_non_positive_max_emails():
    with pytest.raises(SystemExit):
        parse_args(["data/file.olm", "--max-emails", "0"])


def test_main_handles_invalid_archive_path_gracefully(tmp_path, capsys):
    invalid_archive = tmp_path / "invalid.olm"
    invalid_archive.write_text("not-a-zip", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        main([str(invalid_archive), "--dry-run"])

    assert excinfo.value.code == 2
    out = capsys.readouterr().out
    assert "Invalid OLM archive" in out


def test_main_handles_missing_archive_gracefully(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["/tmp/does-not-exist.olm", "--dry-run"])

    assert excinfo.value.code == 2
    out = capsys.readouterr().out
    assert "OLM file not found" in out


def test_main_handles_generic_oserror_gracefully(monkeypatch, capsys):
    import src.ingest as ingest_mod

    def _raise_oserror(*args, **kwargs):
        raise PermissionError("permission denied")

    monkeypatch.setattr(ingest_mod, "ingest", _raise_oserror)

    with pytest.raises(SystemExit) as excinfo:
        main(["data/file.olm", "--dry-run"])

    assert excinfo.value.code == 2
    out = capsys.readouterr().out
    assert "Could not read OLM archive" in out


def test_ingest_dry_run_reports_qol_stats(monkeypatch):
    import src.ingest as ingest_mod

    class _Email:
        def __init__(self, idx):
            self.idx = idx

        def to_dict(self):
            return {"id": self.idx}

    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [_Email(1), _Email(2), _Email(3)])
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email: [{"chunk_id": f"{email['id']}-a"}, {"chunk_id": f"{email['id']}-b"}],
    )

    stats = ingest_mod.ingest("data/mock.olm", dry_run=True, batch_size=2)

    assert stats["emails_parsed"] == 3
    assert stats["chunks_created"] == 6
    assert stats["chunks_added"] == 0
    assert stats["chunks_skipped"] == 0
    assert stats["batches_written"] == 0


def _make_mock_email(idx):
    from src.parse_olm import Email

    return Email(
        message_id=f"<msg{idx}@test.com>",
        subject=f"Subject {idx}",
        sender_name="Sender",
        sender_email="sender@test.com",
        to=["recipient@test.com"],
        cc=[],
        bcc=[],
        date=f"2024-01-0{idx}T10:00:00",
        body_text=f"Body {idx}",
        body_html="",
        folder="Inbox",
        has_attachments=False,
    )


class _MockEmbedder:
    def __init__(self, **_kw):
        self.chromadb_path = "mock"
        self.model_name = "mock"
        self._count = 0

    def count(self):
        return self._count

    def add_chunks(self, chunks, **_kw):
        self._count += len(chunks)
        return len(chunks)

    def set_sparse_db(self, db):
        pass

    def warmup(self):
        pass


def test_ingest_populates_sqlite(monkeypatch, tmp_path):
    import src.ingest as ingest_mod

    emails = [_make_mock_email(i) for i in range(1, 4)]
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: emails)
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email: [{"chunk_id": f"{email.get('uid', 'x')}-a"}],
    )

    import src.embedder as embedder_mod

    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    sqlite_file = str(tmp_path / "test.db")
    stats = ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file)

    assert stats["sqlite_inserted"] == 3

    from src.email_db import EmailDatabase

    db = EmailDatabase(sqlite_file)
    assert db.email_count() == 3
    db.close()


def test_ingest_persists_attachment_evidence_metadata(monkeypatch, tmp_path):
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod
    from src.email_db import EmailDatabase

    email = _make_mock_email(1)
    email.has_attachments = True
    email.attachment_names = ["notes.txt"]
    email.attachments = [
        {
            "name": "notes.txt",
            "mime_type": "text/plain",
            "size": 18,
            "content_id": "",
            "is_inline": False,
        }
    ]
    email.attachment_contents = [("notes.txt", b"hello from attachment")]

    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [email])
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email_dict: [{"chunk_id": f"{email_dict.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    sqlite_file = str(tmp_path / "test.db")
    stats = ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file, extract_attachments=True)

    assert stats["sqlite_inserted"] == 1

    db = EmailDatabase(sqlite_file)
    attachments = db.attachments_for_email(email.uid)
    assert len(attachments) == 1
    assert attachments[0]["extraction_state"] == "text_extracted"
    assert attachments[0]["evidence_strength"] == "strong_text"
    assert attachments[0]["ocr_used"] == 0
    assert attachments[0]["failure_reason"] in (None, "")
    assert attachments[0]["text_preview"] == "hello from attachment"
    db.close()


def test_ingest_dry_run_skips_sqlite(monkeypatch, tmp_path):
    import src.ingest as ingest_mod

    emails = [_make_mock_email(1)]
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: emails)
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email: [{"chunk_id": "x"}],
    )

    sqlite_file = str(tmp_path / "test.db")
    stats = ingest_mod.ingest("mock.olm", dry_run=True, sqlite_path=sqlite_file)

    assert stats["sqlite_inserted"] == 0
    import os

    assert not os.path.exists(sqlite_file)


def test_reingest_is_idempotent(monkeypatch, tmp_path):
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod

    emails = [_make_mock_email(i) for i in range(1, 3)]
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: emails)
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email: [{"chunk_id": f"{email.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    sqlite_file = str(tmp_path / "test.db")
    stats1 = ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file)
    assert stats1["sqlite_inserted"] == 2

    stats2 = ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file)
    assert stats2["sqlite_inserted"] == 0

    from src.email_db import EmailDatabase

    db = EmailDatabase(sqlite_file)
    assert db.email_count() == 2
    db.close()


def test_reingest_force_updates_headers(monkeypatch, tmp_path):
    """--reingest-bodies --force should update subject, sender_name, sender_email."""
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod
    from src.email_db import EmailDatabase
    from src.parse_olm import Email

    # First ingest: store emails with MIME-encoded subject and sender name.
    encoded_emails = [
        Email(
            message_id="<msg1@test.com>",
            subject="=?iso-8859-1?Q?Caf=E9?=",
            sender_name="=?utf-8?B?TMO8ZGVy?=",
            sender_email="old@test.com",
            to=["r@test.com"],
            cc=[],
            bcc=[],
            date="2024-01-01T10:00:00",
            body_text="Old body",
            body_html="",
            folder="Inbox",
            has_attachments=False,
        )
    ]
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: encoded_emails)
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email: [{"chunk_id": f"{email.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    sqlite_file = str(tmp_path / "test.db")
    ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file)

    # Verify encoded values were stored as-is (simulating old parser without decode).
    db = EmailDatabase(sqlite_file)
    row = db.conn.execute("SELECT subject, sender_name, sender_email FROM emails").fetchone()
    assert row["subject"] == "=?iso-8859-1?Q?Caf=E9?="
    db.close()

    # Now simulate re-parse with decoded values (as the fixed parser would produce).
    decoded_emails = [
        Email(
            message_id="<msg1@test.com>",
            subject="Café",
            sender_name="Lüder",
            sender_email="new@test.com",
            to=["r@test.com"],
            cc=[],
            bcc=[],
            date="2024-01-01T10:00:00",
            body_text="New body",
            body_html="",
            folder="Inbox",
            has_attachments=False,
        )
    ]
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: decoded_emails)

    result = ingest_mod.reingest_bodies("mock.olm", sqlite_path=sqlite_file, force=True)
    assert result["updated"] == 1

    db = EmailDatabase(sqlite_file)
    row = db.conn.execute("SELECT subject, sender_name, sender_email, base_subject, email_type FROM emails").fetchone()
    assert row["subject"] == "Café"
    assert row["sender_name"] == "Lüder"
    assert row["sender_email"] == "new@test.com"
    assert row["base_subject"] == "Café"
    assert row["email_type"] == "original"
    db.close()


def test_reingest_no_force_skips_headers(monkeypatch, tmp_path):
    """Without --force, reingest should NOT update headers (only missing bodies)."""
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod
    from src.email_db import EmailDatabase
    from src.parse_olm import Email

    emails = [
        Email(
            message_id="<msg1@test.com>",
            subject="=?utf-8?Q?encoded?=",
            sender_name="Old Name",
            sender_email="old@test.com",
            to=["r@test.com"],
            cc=[],
            bcc=[],
            date="2024-01-01T10:00:00",
            body_text="Body text",
            body_html="",
            folder="Inbox",
            has_attachments=False,
        )
    ]
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: emails)
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email: [{"chunk_id": f"{email.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    sqlite_file = str(tmp_path / "test.db")
    ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file)

    # Non-force reingest: all bodies present → nothing to do, headers untouched.
    decoded_emails = [
        Email(
            message_id="<msg1@test.com>",
            subject="decoded",
            sender_name="New Name",
            sender_email="new@test.com",
            to=["r@test.com"],
            cc=[],
            bcc=[],
            date="2024-01-01T10:00:00",
            body_text="New body",
            body_html="",
            folder="Inbox",
            has_attachments=False,
        )
    ]
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: decoded_emails)

    result = ingest_mod.reingest_bodies("mock.olm", sqlite_path=sqlite_file, force=False)
    assert result["updated"] == 0  # nothing missing

    db = EmailDatabase(sqlite_file)
    row = db.conn.execute("SELECT subject, sender_name FROM emails").fetchone()
    assert row["subject"] == "=?utf-8?Q?encoded?="  # unchanged
    assert row["sender_name"] == "Old Name"  # unchanged
    db.close()


def test_reembed_rechunks_and_upserts(monkeypatch, tmp_path):
    """reembed() should read body text from SQLite, re-chunk, and upsert embeddings."""
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod

    # Initial ingest to populate SQLite
    emails = [_make_mock_email(i) for i in range(1, 3)]
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: emails)
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email: [{"chunk_id": f"{email.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    sqlite_file = str(tmp_path / "test.db")
    chromadb_dir = str(tmp_path / "chroma")
    ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file)

    # Track what reembed does
    upserted_chunks = []

    class _MockEmbedderForReembed:
        def __init__(self, **_kw):
            pass

        def set_sparse_db(self, db):
            pass

        def close(self):
            pass

        def get_existing_ids(self, refresh=False):
            return set()

        def delete_chunks_by_uid(self, uid):
            return 0

        def upsert_chunks(self, chunks, batch_size=100):
            upserted_chunks.extend(chunks)
            return len(chunks)

    # Patch EmailEmbedder used inside reembed()
    monkeypatch.setattr(
        "src.embedder.EmailEmbedder",
        _MockEmbedderForReembed,
    )

    result = ingest_mod.reembed(chromadb_path=chromadb_dir, sqlite_path=sqlite_file)
    assert result["reembedded"] == 2
    assert result["chunks_added"] == len(upserted_chunks)
    assert result["skipped_no_body"] == 0
    assert len(upserted_chunks) >= 2  # At least 1 chunk per email


def test_reembed_skips_emails_without_body(monkeypatch, tmp_path):
    """reembed() should skip emails with empty body text."""
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod
    from src.email_db import EmailDatabase

    emails = [_make_mock_email(1)]
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: emails)
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email: [{"chunk_id": f"{email.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    sqlite_file = str(tmp_path / "test.db")
    ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file)

    # Wipe body text to simulate missing body
    db = EmailDatabase(sqlite_file)
    db.conn.execute("UPDATE emails SET body_text = ''")
    db.conn.commit()
    db.close()

    class _MockEmbedderForReembed:
        def __init__(self, **_kw):
            pass

        def set_sparse_db(self, db):
            pass

        def close(self):
            pass

        def get_existing_ids(self, refresh=False):
            return set()

        def delete_chunks_by_uid(self, uid):
            return 0

        def upsert_chunks(self, chunks, batch_size=100):
            return len(chunks)

    monkeypatch.setattr("src.embedder.EmailEmbedder", _MockEmbedderForReembed)

    result = ingest_mod.reembed(sqlite_path=sqlite_file)
    assert result["reembedded"] == 0
    assert result["skipped_no_body"] == 1


def test_reembed_empty_database(monkeypatch, tmp_path):
    """reembed() should handle empty database gracefully."""
    import src.ingest as ingest_mod
    from src.email_db import EmailDatabase

    sqlite_file = str(tmp_path / "test.db")
    db = EmailDatabase(sqlite_file)
    db.close()

    result = ingest_mod.reembed(sqlite_path=sqlite_file)
    assert result["reembedded"] == 0
    assert result["total"] == 0


def test_format_ingestion_summary_includes_qol_fields():
    from src.ingest import format_ingestion_summary

    lines = format_ingestion_summary(
        {
            "emails_parsed": 10,
            "chunks_created": 20,
            "chunks_added": 18,
            "chunks_skipped": 2,
            "batches_written": 3,
            "total_in_db": 99,
            "dry_run": False,
            "elapsed_seconds": 1.5,
        }
    )

    assert "=== Ingestion Summary ===" in lines
    assert "Emails parsed: 10" in lines
    assert "Chunks created: 20" in lines
    assert "Chunks added: 18" in lines
    assert "Chunks skipped: 2" in lines
    assert "Write batches: 3" in lines
    assert "Total in DB: 99" in lines


def test_format_ingestion_summary_for_dry_run_hides_db_totals():
    from src.ingest import format_ingestion_summary

    lines = format_ingestion_summary(
        {
            "emails_parsed": 10,
            "chunks_created": 20,
            "chunks_added": 0,
            "chunks_skipped": 0,
            "batches_written": 0,
            "total_in_db": None,
            "dry_run": True,
            "elapsed_seconds": 1.5,
        }
    )

    assert "Database write disabled (dry-run)." in lines
    assert not any(line.startswith("Chunks added:") for line in lines)
    assert not any(line.startswith("Total in DB:") for line in lines)


def test_ingest_embed_images_enables_extract_attachments(monkeypatch):
    """embed_images=True should auto-enable extract_attachments."""
    import src.ingest as ingest_mod

    class _Email:
        def __init__(self, idx):
            self.idx = idx
            self.uid = f"uid-{idx}"
            self.attachment_contents = []

        def to_dict(self):
            return {"id": self.idx, "uid": self.uid}

    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **kw: [_Email(1)])
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email: [{"chunk_id": f"{email.get('uid', 'x')}-a"}],
    )

    # When embed_images=True, dry_run works without needing the embedder
    stats = ingest_mod.ingest("data/mock.olm", dry_run=True, embed_images=True)
    assert stats["extract_attachments"] is True
    assert stats["image_embeddings"] == 0


def test_ingest_embed_images_param_accepted(monkeypatch):
    """Verify embed_images param is accepted by ingest() function."""
    import src.ingest as ingest_mod

    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [])

    stats = ingest_mod.ingest("data/mock.olm", dry_run=True, embed_images=False)
    assert stats["image_embeddings"] == 0


def test_ingest_stats_include_image_embeddings(monkeypatch):
    """Verify image_embeddings key exists in ingestion stats."""
    import src.ingest as ingest_mod

    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [])

    stats = ingest_mod.ingest("data/mock.olm", dry_run=True)
    assert "image_embeddings" in stats


def test_ingest_embed_images_skipped_on_low_memory(monkeypatch):
    """Low-memory systems skip Visualized-BGE startup unless explicitly forced."""
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod

    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [])
    monkeypatch.setattr(ingest_mod, "should_enable_image_embedding", lambda: False)
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    stats = ingest_mod.ingest("data/mock.olm", dry_run=False, embed_images=True)
    assert stats["extract_attachments"] is True
    assert stats["image_embeddings"] == 0


# ── _EmbedPipeline tests ────────────────────────────────────────────


def test_embed_pipeline_error_propagation():
    """Errors in the consumer thread should be re-raised by finish()."""
    from src.ingest import _EmbedPipeline

    class _BrokenEmbedder:
        def add_chunks(self, chunks, **_kw):
            raise RuntimeError("embed failed")

    pipeline = _EmbedPipeline(
        embedder=_BrokenEmbedder(),
        email_db=None,
        entity_extractor_fn=None,
        batch_size=100,
    )
    pipeline.start()
    pipeline.submit(["fake_chunk"], [])

    with pytest.raises(RuntimeError, match="embed failed"):
        pipeline.finish()


def test_embed_pipeline_empty_batch():
    """Submitting empty lists should not crash."""
    from src.ingest import _EmbedPipeline

    pipeline = _EmbedPipeline(
        embedder=None,
        email_db=None,
        entity_extractor_fn=None,
        batch_size=100,
    )
    pipeline.start()
    pipeline.submit([], [])  # Should be no-op (filtered out)
    pipeline.finish()
    assert pipeline.chunks_added == 0
    assert pipeline.sqlite_inserted == 0


def test_format_ingestion_summary_includes_timing():
    from src.ingest import format_ingestion_summary

    lines = format_ingestion_summary(
        {
            "emails_parsed": 10,
            "chunks_created": 20,
            "chunks_added": 18,
            "chunks_skipped": 2,
            "batches_written": 3,
            "total_in_db": 99,
            "dry_run": False,
            "elapsed_seconds": 10.5,
            "timing": {"embed_seconds": 8.0, "write_seconds": 1.5},
        }
    )

    assert any("Timing:" in line for line in lines)
    assert any("embed=8.0s" in line for line in lines)


# ── Exchange entity extraction tests ──────────────────────────


def test_exchange_entities_from_email_extracts_all_types():
    """_exchange_entities_from_email should extract URLs, emails, contacts, meetings."""
    from src.ingest import _exchange_entities_from_email
    from src.parse_olm import Email

    email = Email(
        message_id="<msg@test.com>",
        subject="Test",
        sender_name="Sender",
        sender_email="sender@test.com",
        to=["r@test.com"],
        cc=[],
        bcc=[],
        date="2024-01-01T10:00:00",
        body_text="Body",
        body_html="",
        folder="Inbox",
        has_attachments=False,
        exchange_extracted_links=[{"url": "https://example.com", "text": "Example"}],
        exchange_extracted_emails=["alice@company.com"],
        exchange_extracted_contacts=["Bob Smith"],
        exchange_extracted_meetings=[{"subject": "Team Standup", "start": "2024-01-02"}],
    )

    entities = _exchange_entities_from_email(email)
    assert len(entities) == 4

    types = {e[1] for e in entities}
    assert types == {"url", "email", "person", "event"}

    # Check normalized forms are lowercased
    for text, _etype, norm in entities:
        assert norm == text.lower()


def test_exchange_entities_from_email_empty():
    """_exchange_entities_from_email returns empty list when no Exchange data."""
    from src.ingest import _exchange_entities_from_email

    email = _make_mock_email(1)
    entities = _exchange_entities_from_email(email)
    assert entities == []


def test_ingest_inserts_exchange_entities(monkeypatch, tmp_path):
    """Exchange-extracted entities should be inserted into entities table during ingest."""
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod
    from src.email_db import EmailDatabase
    from src.parse_olm import Email

    email = Email(
        message_id="<msg1@test.com>",
        subject="With Exchange Data",
        sender_name="Sender",
        sender_email="sender@test.com",
        to=["r@test.com"],
        cc=[],
        bcc=[],
        date="2024-01-01T10:00:00",
        body_text="Hello world",
        body_html="",
        folder="Inbox",
        has_attachments=False,
        exchange_extracted_links=[{"url": "https://intranet.company.com"}],
        exchange_extracted_emails=["contact@vendor.com"],
    )

    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [email])
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda e: [{"chunk_id": f"{e.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    sqlite_file = str(tmp_path / "test.db")
    ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file)

    db = EmailDatabase(sqlite_file)
    entities = db.conn.execute("SELECT entity_text, entity_type FROM entities ORDER BY entity_type").fetchall()
    entity_types = {row["entity_type"] for row in entities}
    assert "url" in entity_types
    assert "email" in entity_types
    db.close()


def test_reingest_analytics_backfills_missing(tmp_path):
    """reingest_analytics() should populate language/sentiment for emails missing them."""
    from src.email_db import EmailDatabase
    from src.ingest import reingest_analytics

    sqlite_file = str(tmp_path / "test.db")
    db = EmailDatabase(sqlite_file)
    from src.parse_olm import Email

    email = Email(
        message_id="<analytics1@test.com>",
        subject="Test",
        sender_name="Alice",
        sender_email="alice@test.com",
        to=["bob@test.com"],
        cc=[],
        bcc=[],
        date="2024-01-01T10:00:00",
        body_text="Thank you very much for the wonderful and excellent presentation. "
        "I really appreciate the great work done by the team.",
        body_html="",
        folder="Inbox",
        has_attachments=False,
    )
    db.insert_email(email)

    # Confirm analytics columns are NULL initially
    row = db.conn.execute("SELECT detected_language, sentiment_label FROM emails").fetchone()
    assert row["detected_language"] is None
    assert row["sentiment_label"] is None
    db.close()

    result = reingest_analytics(sqlite_path=sqlite_file)
    assert result["updated"] == 1

    db2 = EmailDatabase(sqlite_file)
    row = db2.conn.execute("SELECT detected_language, sentiment_label, sentiment_score FROM emails").fetchone()
    assert row["detected_language"] == "en"
    assert row["sentiment_label"] is not None
    db2.close()


def test_ingest_computes_language_and_sentiment(monkeypatch, tmp_path):
    """Ingest should auto-populate detected_language and sentiment columns."""
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod
    from src.email_db import EmailDatabase
    from src.parse_olm import Email

    email = Email(
        message_id="<lang1@test.com>",
        subject="Thank you",
        sender_name="Alice",
        sender_email="alice@test.com",
        to=["bob@test.com"],
        cc=[],
        bcc=[],
        date="2024-01-01T10:00:00",
        body_text="Thank you so much for the excellent work on this project. "
        "I really appreciate your help and the team has been great.",
        body_html="",
        folder="Inbox",
        has_attachments=False,
    )

    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [email])
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda e: [{"chunk_id": f"{e.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    sqlite_file = str(tmp_path / "test.db")
    ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file)

    db = EmailDatabase(sqlite_file)
    row = db.conn.execute("SELECT detected_language, sentiment_label, sentiment_score FROM emails").fetchone()
    assert row["detected_language"] == "en"
    assert row["sentiment_label"] == "positive"
    assert row["sentiment_score"] > 0
    db.close()


def test_exchange_entities_dedup_with_regex(tmp_path):
    """Exchange and regex entities with the same normalized_form and type should deduplicate."""
    from src.email_db import EmailDatabase

    db = EmailDatabase(":memory:")
    email = _make_mock_email(1)
    db.insert_email(email)

    # Simulate regex extractor inserting a URL entity
    db.insert_entities_batch(
        email.uid,
        [
            ("https://example.com", "url", "https://example.com"),
        ],
    )

    # Now simulate Exchange extractor inserting the same URL (canonical type)
    from src.ingest import _exchange_entities_from_email
    from src.parse_olm import Email

    exchange_email = Email(
        message_id="<msg1@test.com>",
        subject="Test",
        sender_name="Sender",
        sender_email="sender@test.com",
        to=["r@test.com"],
        cc=[],
        bcc=[],
        date="2024-01-01T10:00:00",
        body_text="Body",
        body_html="",
        folder="Inbox",
        has_attachments=False,
        exchange_extracted_links=[{"url": "https://example.com"}],
    )
    exchange_entities = _exchange_entities_from_email(exchange_email)
    assert exchange_entities[0][1] == "url"  # canonical type, not exchange_url

    # Insert exchange entities — ON CONFLICT should deduplicate
    db.insert_entities_batch(email.uid, exchange_entities)

    # Should be only ONE entity row for this URL
    rows = db.conn.execute("SELECT * FROM entities WHERE normalized_form = 'https://example.com'").fetchall()
    assert len(rows) == 1
    db.close()


def test_incremental_skips_existing_emails(monkeypatch, tmp_path):
    """incremental=True should skip emails already in SQLite and not re-extract entities."""
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod
    from src.email_db import EmailDatabase

    emails = [_make_mock_email(i) for i in range(1, 4)]
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: emails)
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email: [{"chunk_id": f"{email.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    sqlite_file = str(tmp_path / "test.db")

    # First ingest: all 3 emails inserted
    stats1 = ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file)
    assert stats1["sqlite_inserted"] == 3
    assert stats1["skipped_incremental"] == 0

    # Second ingest with incremental: all 3 skipped at parse-loop level
    stats2 = ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file, incremental=True)
    assert stats2["skipped_incremental"] == 3
    assert stats2["sqlite_inserted"] == 0
    assert stats2["chunks_added"] == 0

    db = EmailDatabase(sqlite_file)
    assert db.email_count() == 3
    db.close()


def test_incremental_processes_new_emails(monkeypatch, tmp_path):
    """incremental=True should process only new emails, skipping existing ones."""
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod
    from src.email_db import EmailDatabase

    first_batch = [_make_mock_email(i) for i in range(1, 3)]
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: first_batch)
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email: [{"chunk_id": f"{email.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    sqlite_file = str(tmp_path / "test.db")

    # First ingest: 2 emails
    stats1 = ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file)
    assert stats1["sqlite_inserted"] == 2

    # Second ingest with 3 emails (2 old + 1 new), incremental mode
    mixed_batch = [_make_mock_email(i) for i in range(1, 4)]
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: mixed_batch)

    stats2 = ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file, incremental=True)
    assert stats2["skipped_incremental"] == 2
    assert stats2["sqlite_inserted"] == 1

    db = EmailDatabase(sqlite_file)
    assert db.email_count() == 3
    db.close()


def test_timing_flag_parsed():
    args = parse_args(["data/file.olm", "--timing"])
    assert args.timing is True


def test_timing_flag_default():
    args = parse_args(["data/file.olm"])
    assert args.timing is False


def test_format_ingestion_summary_detailed_timing():
    from src.ingest import format_ingestion_summary

    lines = format_ingestion_summary(
        {
            "emails_parsed": 10,
            "chunks_created": 20,
            "chunks_added": 18,
            "chunks_skipped": 2,
            "batches_written": 3,
            "total_in_db": 99,
            "dry_run": False,
            "elapsed_seconds": 10.5,
            "timing": {
                "embed_seconds": 6.0,
                "write_seconds": 3.0,
                "parse_seconds": 1.2,
                "queue_wait_seconds": 0.3,
                "sqlite_seconds": 1.5,
                "entity_seconds": 0.8,
                "analytics_seconds": 0.7,
            },
        }
    )

    assert any("Timing:" in line for line in lines)
    assert any("Breakdown:" in line for line in lines)
    assert any("parse=1.2s" in line for line in lines)
    assert any("sqlite=1.5s" in line for line in lines)
    assert any("analytics=0.7s" in line for line in lines)


def test_reingest_metadata_backfills_v7_fields(monkeypatch, tmp_path):
    """reingest_metadata should update categories, thread_topic, etc. for existing emails."""
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod
    from src.email_db import EmailDatabase
    from src.parse_olm import Email

    # First ingest: basic email without v7 metadata
    basic_email = Email(
        message_id="<msg1@test.com>",
        subject="Test",
        sender_name="Sender",
        sender_email="sender@test.com",
        to=["r@test.com"],
        cc=[],
        bcc=[],
        date="2024-01-01T10:00:00",
        body_text="Hello",
        body_html="",
        folder="Inbox",
        has_attachments=False,
    )
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [basic_email])
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda e: [{"chunk_id": f"{e.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    sqlite_file = str(tmp_path / "test.db")
    ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file)

    # Now simulate re-parse with v7 metadata
    enriched_email = Email(
        message_id="<msg1@test.com>",
        subject="Test",
        sender_name="Sender",
        sender_email="sender@test.com",
        to=["r@test.com"],
        cc=[],
        bcc=[],
        date="2024-01-01T10:00:00",
        body_text="Hello",
        body_html="",
        folder="Inbox",
        has_attachments=False,
        categories=["Important", "Project X"],
        thread_topic="Test Thread",
        is_calendar_message=True,
        exchange_extracted_emails=["vendor@example.com"],
    )
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [enriched_email])

    result = ingest_mod.reingest_metadata("mock.olm", sqlite_path=sqlite_file)
    assert result["updated"] == 1
    assert result["exchange_entities_inserted"] == 1

    db = EmailDatabase(sqlite_file)
    row = db.conn.execute("SELECT categories, thread_topic, is_calendar_message FROM emails").fetchone()
    assert "Important" in row["categories"]
    assert row["thread_topic"] == "Test Thread"
    assert row["is_calendar_message"] == 1

    cats = db.conn.execute("SELECT category FROM email_categories").fetchall()
    assert {r["category"] for r in cats} == {"Important", "Project X"}
    db.close()


def test_pipeline_consumer_error_does_not_deadlock():
    """When consumer thread raises, producer should not block on full queue."""
    pipeline = _EmbedPipeline.__new__(_EmbedPipeline)
    pipeline._queue = queue.Queue(maxsize=2)
    pipeline._embedder = None
    pipeline._email_db = None
    pipeline._ingestion_run_id = None
    pipeline._batch_size = 64
    pipeline._error = None
    pipeline._thread = None
    pipeline.chunks_added = 0
    pipeline.sqlite_inserted = 0
    pipeline.batches_written = 0
    pipeline.embed_seconds = 0.0
    pipeline.write_seconds = 0.0
    pipeline.sqlite_seconds = 0.0
    pipeline.entity_seconds = 0.0
    pipeline._detailed_timing = False
    pipeline.analytics_seconds = 0.0

    # Override _process_batch to always raise
    def _failing_batch(chunks, emails):
        raise RuntimeError("test error")

    pipeline._process_batch = _failing_batch
    pipeline._thread = threading.Thread(target=pipeline._run, daemon=True)
    pipeline._thread.start()

    # Submit work — consumer will crash on first batch
    pipeline._queue.put((["chunk1"], []))
    time.sleep(0.2)

    # The consumer should have drained the queue, so this put should not block
    # even though the consumer has died
    pipeline._queue.put(([" chunk2"], []))
    pipeline._queue.put(_SENTINEL)
    pipeline._thread.join(timeout=2)
    assert not pipeline._thread.is_alive(), "Consumer thread should have exited"
    assert pipeline._error is not None
