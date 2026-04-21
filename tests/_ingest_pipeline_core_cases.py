# ruff: noqa: F401, I001
import queue
import threading
import time
from typing import Any

import pytest

from src.ingest import _SENTINEL, _EmbedPipeline, main, parse_args

from .helpers.ingest_fixtures import _MockEmbedder, _make_mock_email


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
    monkeypatch.setattr("src.attachment_extractor.image_ocr_available", lambda: False)
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
    assert attachments[0]["extracted_text"] == "hello from attachment"
    assert attachments[0]["normalized_text"] == "hello from attachment"
    assert attachments[0]["text_normalization_version"] == 1
    assert attachments[0]["attachment_id"]
    assert attachments[0]["content_sha256"]
    assert attachments[0]["locator_version"] == 2
    assert attachments[0]["text_source_path"] == f"attachment://{email.uid}/0/notes.txt"
    locator = attachments[0]["text_locator"]
    assert locator["kind"] == "mailbox_attachment"
    assert locator["email_uid"] == email.uid
    assert locator["attachment_index"] == 0
    assert locator["filename"] == "notes.txt"
    assert locator["extraction_state"] == "text_extracted"
    assert locator["attachment_id"] == attachments[0]["attachment_id"]
    assert locator["content_sha256"] == attachments[0]["content_sha256"]
    assert locator["locator_version"] == 2
    db.close()


def test_mailbox_attachment_locator_extracts_rich_subdocument_hints() -> None:
    import src.ingest_pipeline as ingest_pipeline

    locator = ingest_pipeline._mailbox_attachment_locator(
        email_uid="uid-locator",
        att_index=0,
        filename="bundle.zip",
        extraction_state="text_extracted",
        attachment_id="att-1",
        content_sha256="sha-1",
        extracted_text="[Member: records/report.xlsx]\n[Sheet: Tabelle1]\nA1:B4\n[Page 2]",
    )

    assert locator["archive_member_path"] == "records/report.xlsx"
    assert locator["sheet_name"] == "Tabelle1"
    assert locator["cell_range"] == "A1:B4"
    assert locator["page_number"] == 2
    assert locator["page_count"] == 2


def test_ingest_zero_chunk_email_marks_ledger_completed(monkeypatch, tmp_path):
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod
    from src.email_db import EmailDatabase

    email = _make_mock_email(1)

    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [email])
    monkeypatch.setattr(ingest_mod, "chunk_email", lambda _email: [])
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    sqlite_file = str(tmp_path / "test.db")
    stats = ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file)

    assert stats["sqlite_inserted"] == 1

    db = EmailDatabase(sqlite_file)
    row = db.conn.execute(
        "SELECT vector_status, vector_chunk_count, attachment_status, image_status FROM email_ingest_state WHERE email_uid = ?",
        (email.uid,),
    ).fetchone()
    assert row is not None
    assert row["vector_status"] == "completed"
    assert row["vector_chunk_count"] == 0
    assert row["attachment_status"] == "not_requested"
    assert row["image_status"] == "not_requested"
    db.close()


def test_ingest_binary_only_attachment_stays_degraded_in_ledger(monkeypatch, tmp_path):
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod
    from src.email_db import EmailDatabase

    email = _make_mock_email(1)
    email.has_attachments = True
    email.attachment_names = ["photo.png"]
    email.attachments = [
        {
            "name": "photo.png",
            "mime_type": "image/png",
            "size": 128,
            "content_id": "",
            "is_inline": False,
        }
    ]
    email.attachment_contents = [("photo.png", b"fake-image")]

    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [email])
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email_dict: [{"chunk_id": f"{email_dict.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr("src.attachment_extractor.image_ocr_available", lambda: False)
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    sqlite_file = str(tmp_path / "test.db")
    stats = ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file, extract_attachments=True)

    assert stats["sqlite_inserted"] == 1

    db = EmailDatabase(sqlite_file)
    row = db.conn.execute(
        "SELECT vector_status, attachment_status FROM email_ingest_state WHERE email_uid = ?",
        (email.uid,),
    ).fetchone()
    assert row is not None
    assert row["vector_status"] == "completed"
    assert row["attachment_status"] == "degraded"
    attachment = db.attachments_for_email(email.uid)[0]
    assert attachment["extraction_state"] == "binary_only"
    assert attachment["failure_reason"] == "no_text_extracted_ocr_not_available"
    db.close()


def test_attachment_payload_failure_marks_degraded_not_completed(monkeypatch, tmp_path):
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod
    from src.email_db import EmailDatabase

    email = _make_mock_email(1)
    email.has_attachments = True
    email.attachment_names = ["scan.pdf"]
    email.attachments = [
        {
            "name": "scan.pdf",
            "mime_type": "application/pdf",
            "size": 1024,
            "content_id": "",
            "is_inline": False,
        }
    ]
    email.attachment_contents = []
    email.__dict__["_attachment_payload_extraction_failed"] = True

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
    row = db.conn.execute(
        "SELECT attachment_status FROM email_ingest_state WHERE email_uid = ?",
        (email.uid,),
    ).fetchone()
    assert row is not None
    assert row["attachment_status"] == "degraded"
    attachment = db.attachments_for_email(email.uid)[0]
    assert attachment["extraction_state"] == "extraction_failed"
    assert attachment["failure_reason"] == "attachment_payload_extraction_failed"
    assert email.uid not in db.completed_ingest_uids(attachment_required=True)
    db.close()


def test_ingest_image_attachment_uses_ocr_when_available(monkeypatch, tmp_path):
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod
    from src.email_db import EmailDatabase

    email = _make_mock_email(1)
    email.has_attachments = True
    email.attachment_names = ["photo.png"]
    email.attachments = [
        {
            "name": "photo.png",
            "mime_type": "image/png",
            "size": 128,
            "content_id": "",
            "is_inline": False,
        }
    ]
    email.attachment_contents = [("photo.png", b"fake-image")]

    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [email])
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email_dict: [{"chunk_id": f"{email_dict.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr(
        "src.attachment_extractor.extract_image_text_ocr",
        lambda filename, content, **_kw: "Recovered screenshot text",
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    sqlite_file = str(tmp_path / "test.db")
    ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file, extract_attachments=True)

    db = EmailDatabase(sqlite_file)
    row = db.conn.execute(
        "SELECT attachment_status FROM email_ingest_state WHERE email_uid = ?",
        (email.uid,),
    ).fetchone()
    attachment = db.attachments_for_email(email.uid)[0]
    assert row["attachment_status"] == "completed"
    assert attachment["extraction_state"] == "ocr_text_extracted"
    assert attachment["evidence_strength"] == "strong_text"
    assert attachment["ocr_used"] == 1
    assert attachment["text_preview"] == "Recovered screenshot text"
    db.close()


def test_textless_pdf_ocr_state_requires_pdf_tooling(monkeypatch):
    from src.attachment_extractor import attachment_ocr_available_for
    from src.ingest_pipeline import _textless_attachment_state_with_ocr

    monkeypatch.setattr("src.attachment_extractor.image_ocr_available", lambda: True)
    monkeypatch.setattr("src.attachment_extractor.pdf_ocr_available", lambda: False)

    state, reason = _textless_attachment_state_with_ocr(
        filename="scan.pdf",
        mime_type="application/pdf",
        ocr_attempted=True,
        ocr_available=attachment_ocr_available_for("scan.pdf", mime_type="application/pdf"),
    )

    assert state == "binary_only"
    assert reason == "no_text_extracted_ocr_not_available"


def test_ingest_image_chunks_use_normalized_attachment_metadata(monkeypatch, tmp_path):
    import src.ingest as ingest_mod

    email = _make_mock_email(1)
    email.has_attachments = True
    email.attachment_names = ["photo.png"]
    email.attachments = [
        {
            "name": "photo.png",
            "mime_type": "image/png",
            "size": 128,
            "content_id": "",
            "is_inline": False,
        }
    ]
    email.attachment_contents = [("photo.png", b"fake-image")]

    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [email])
    monkeypatch.setattr(ingest_mod, "chunk_email", lambda email_dict: [{"chunk_id": f"{email_dict.get('uid', 'x')}-a"}])
    monkeypatch.setattr(ingest_mod, "should_enable_image_embedding", lambda: True)
    monkeypatch.setattr("src.attachment_extractor._get_image_embedder", lambda: type("Probe", (), {"is_available": True})())
    monkeypatch.setattr("src.attachment_extractor.extract_image_embedding", lambda *_args, **_kwargs: [0.1, 0.2, 0.3])

    class _TrackingEmbedder:
        last_instance: Any | None = None

        def __init__(self, **_kw):
            type(self).last_instance = self
            self._count = 0
            self.added_chunks = []

        def count(self):
            return self._count

        def add_chunks(self, chunks, **_kw):
            self.added_chunks.extend(chunks)
            self._count += len(chunks)
            return len(chunks)

        def set_sparse_db(self, db):
            return None

        def warmup(self):
            return None

    monkeypatch.setattr("src.embedder.EmailEmbedder", _TrackingEmbedder)

    sqlite_file = str(tmp_path / "test.db")
    ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file, embed_images=True)

    instance = _TrackingEmbedder.last_instance
    assert instance is not None
    image_chunks = [c for c in instance.added_chunks if c.metadata.get("chunk_type") == "image"]
    assert len(image_chunks) == 1
    metadata = image_chunks[0].metadata
    assert metadata["candidate_kind"] == "attachment"
    assert metadata["is_attachment"] == "True"
    assert metadata["attachment_filename"] == "photo.png"
    assert metadata["attachment_name"] == "photo.png"
    assert metadata["attachment_type"] == "png"


def test_ingest_surfaces_sparse_storage_diagnostics_in_stats(monkeypatch, tmp_path):
    import src.ingest as ingest_mod

    email = _make_mock_email(1)
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [email])
    monkeypatch.setattr(ingest_mod, "chunk_email", lambda email_dict: [{"chunk_id": f"{email_dict.get('uid', 'x')}-a"}])

    class _SparseDiagnosticsEmbedder:
        def __init__(self, **_kw):
            self._count = 0
            self.sparse_store_failures = 2
            self.sparse_vectors_stored = 7

        def count(self):
            return self._count

        def add_chunks(self, chunks, **_kw):
            self._count += len(chunks)
            return len(chunks)

        def set_sparse_db(self, db):
            return None

        def warmup(self):
            return None

    monkeypatch.setattr("src.embedder.EmailEmbedder", _SparseDiagnosticsEmbedder)

    sqlite_file = str(tmp_path / "test.db")
    stats = ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file)

    assert stats["sparse_store_failures"] == 2
    assert stats["sparse_vectors_stored"] == 7


def test_reprocess_degraded_attachments_recovers_image_text(tmp_path, monkeypatch):
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod
    from src.email_db import EmailDatabase

    def _make_image_email():
        email = _make_mock_email(1)
        email.has_attachments = True
        email.attachment_names = ["photo.png"]
        email.attachments = [
            {
                "name": "photo.png",
                "mime_type": "image/png",
                "size": 128,
                "content_id": "",
                "is_inline": False,
            }
        ]
        email.attachment_contents = [("photo.png", b"fake-image")]
        return email

    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email_dict: [{"chunk_id": f"{email_dict.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    email_uid = _make_image_email().uid
    sqlite_file = str(tmp_path / "test.db")
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [_make_image_email()])
    monkeypatch.setattr("src.attachment_extractor.image_ocr_available", lambda: False)
    monkeypatch.setattr("src.attachment_extractor.extract_image_text_ocr", lambda filename, content, **_kw: None)
    ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file, extract_attachments=True)

    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [_make_image_email()])
    monkeypatch.setattr("src.attachment_extractor.image_ocr_available", lambda: True)
    monkeypatch.setattr(
        "src.attachment_extractor.extract_image_text_ocr",
        lambda filename, content, **_kw: "Recovered screenshot text",
    )
    result = ingest_mod.reprocess_degraded_attachments(
        "mock.olm",
        sqlite_path=sqlite_file,
        batch_size=10,
    )

    assert result["updated"] == 1
    assert result["ocr_recovered"] == 1
    db = EmailDatabase(sqlite_file)
    row = db.conn.execute(
        "SELECT attachment_status FROM email_ingest_state WHERE email_uid = ?",
        (email_uid,),
    ).fetchone()
    attachment = db.attachments_for_email(email_uid)[0]
    assert row["attachment_status"] == "completed"
    assert attachment["extraction_state"] == "ocr_text_extracted"
    assert attachment["ocr_used"] == 1
    db.close()


def test_reprocess_degraded_attachments_deletes_stale_attachment_chunks(tmp_path, monkeypatch):
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod
    from src.ingest_reingest import _attachment_chunk_prefix

    def _make_image_email():
        email = _make_mock_email(1)
        email.has_attachments = True
        email.attachment_names = ["photo.png"]
        email.attachments = [
            {
                "name": "photo.png",
                "mime_type": "image/png",
                "size": 128,
                "content_id": "",
                "is_inline": False,
            }
        ]
        email.attachment_contents = [("photo.png", b"fake-image")]
        return email

    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email_dict: [{"chunk_id": f"{email_dict.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    email_uid = _make_image_email().uid
    sqlite_file = str(tmp_path / "test.db")
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [_make_image_email()])
    monkeypatch.setattr("src.attachment_extractor.image_ocr_available", lambda: False)
    monkeypatch.setattr("src.attachment_extractor.extract_image_text_ocr", lambda filename, content, **_kw: None)
    ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file, extract_attachments=True)

    stale_prefix = _attachment_chunk_prefix(email_uid, "photo.png", 0)
    delete_calls = []

    class _TrackingEmbedder:
        def __init__(self, **_kw):
            self.collection = type("Collection", (), {"delete": lambda self, ids: delete_calls.append(list(ids))})()

        def set_sparse_db(self, db):
            pass

        def close(self):
            pass

        def get_existing_ids(self, refresh=False):
            return {f"{stale_prefix}0", f"{stale_prefix}1", f"{stale_prefix}2"}

        def upsert_chunks(self, chunks, batch_size=100):
            return len(chunks)

    monkeypatch.setattr("src.embedder.EmailEmbedder", _TrackingEmbedder)
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [_make_image_email()])
    monkeypatch.setattr("src.attachment_extractor.image_ocr_available", lambda: True)
    monkeypatch.setattr(
        "src.attachment_extractor.extract_image_text_ocr",
        lambda filename, content, **_kw: "Recovered screenshot text",
    )

    result = ingest_mod.reprocess_degraded_attachments(
        "mock.olm",
        sqlite_path=sqlite_file,
        batch_size=10,
    )

    assert result["chunks_deleted"] == 3
    assert len(delete_calls) == 1
    assert set(delete_calls[0]) == {f"{stale_prefix}0", f"{stale_prefix}1", f"{stale_prefix}2"}


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


def test_ingest_resume_skips_previously_parsed_emails(monkeypatch, tmp_path):
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

    sqlite_file = str(tmp_path / "resume.db")
    db = EmailDatabase(sqlite_file)
    run_id = db.record_ingestion_start("mock.olm")
    db.update_ingest_checkpoint(
        run_id=run_id,
        olm_path="mock.olm",
        last_batch_ordinal=1,
        emails_parsed=2,
        emails_inserted=0,
        last_email_uid=emails[1].uid,
        status="failed",
        commit=True,
    )
    db.record_ingestion_failure(run_id, error_message="interrupted", stats={"emails_parsed": 2, "emails_inserted": 0})
    db.close()

    stats = ingest_mod.ingest(
        "mock.olm",
        dry_run=False,
        sqlite_path=sqlite_file,
        resume=True,
    )

    assert stats["resumed_from_checkpoint"] is True
    assert stats["skipped_resume"] == 2
    assert stats["sqlite_inserted"] == 1


def test_update_ingest_checkpoint_safe_skips_locked_checkpoint(monkeypatch):
    import logging
    import sqlite3

    import src.ingest_pipeline as ingest_pipeline_mod

    class _CheckpointStore:
        def update_ingest_checkpoint(self, **_kwargs):
            raise sqlite3.OperationalError("database is locked")

    messages: list[str] = []

    class _Handler(logging.Handler):
        def emit(self, record):
            messages.append(record.getMessage())

    handler = _Handler()
    logger = logging.getLogger(ingest_pipeline_mod.__name__)
    logger.addHandler(handler)
    previous_level = logger.level
    logger.setLevel(logging.DEBUG)
    try:
        updated = ingest_pipeline_mod._update_ingest_checkpoint_safe(
            checkpoint_store=_CheckpointStore(),
            run_id=1,
            olm_path="archive.olm",
            last_batch_ordinal=2,
            emails_parsed=42,
            emails_inserted=40,
            last_email_uid="uid-42",
            status="running",
            allow_locked_skip=True,
            stage="mid_run_batch_submit",
        )
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)

    assert updated is False
    assert any("Skipping ingest checkpoint update during mid_run_batch_submit" in message for message in messages)


def test_embed_pipeline_subbatches_large_chunk_groups():
    from typing import Any, cast

    from src.chunker import EmailChunk

    calls: list[int] = []

    class _FakeEmbedder:
        def add_chunks(self, chunks, batch_size=500, skip_existing_check=False):
            calls.append(len(chunks))
            return len(chunks)

    pipeline = _EmbedPipeline(
        embedder=cast(Any, _FakeEmbedder()),
        email_db=None,
        entity_extractor_fn=None,
        batch_size=10,
    )

    chunks = [EmailChunk(uid="u1", chunk_id=f"u1__{idx}", text=f"chunk {idx}", metadata={}) for idx in range(25)]
    pipeline._process_batch(chunks, [])

    assert calls == [10, 10, 5]
    assert pipeline.chunks_added == 25


def test_producer_parse_exception_aborts_pipeline_before_db_close(monkeypatch, tmp_path):
    import src.ingest as ingest_mod
    import src.ingest_pipeline as ingest_pipeline_mod

    events: list[str] = []

    class _FakeEmbedder:
        def count(self):
            return 0

        def set_sparse_db(self, _db):
            return None

        def warmup(self):
            return None

    class _FakeEmailDB:
        def record_ingestion_start(self, *_args, **_kwargs):
            events.append("db.record_start")
            return 1

        def record_ingestion_failure(self, *_args, **_kwargs):
            events.append("db.record_failure")

        def close(self):
            events.append("db.close")

    class _FakePipeline:
        def __init__(self, **_kwargs):
            self.chunks_added = 0
            self.batches_written = 0
            self.sqlite_inserted = 0
            self.embed_seconds = 0.0
            self.write_seconds = 0.0
            self.sqlite_seconds = 0.0
            self.entity_seconds = 0.0
            self.analytics_seconds = 0.0

        def start(self):
            events.append("pipeline.start")

        def submit(self, _chunks, _emails):
            events.append("pipeline.submit")

        def finish(self):
            events.append("pipeline.finish")

        def abort(self):
            events.append("pipeline.abort")
            return None

    def _parse_then_fail(_path, **_kwargs):
        yield _make_mock_email(1)
        raise RuntimeError("parse exploded")

    monkeypatch.setattr(ingest_pipeline_mod, "_build_runtime", lambda **_kwargs: (_FakeEmbedder(), _FakeEmailDB()))
    monkeypatch.setattr(ingest_mod, "parse_olm", _parse_then_fail)
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email_dict: [{"chunk_id": f"{email_dict.get('uid', 'x')}__0"}],
    )
    monkeypatch.setattr(ingest_mod, "_EmbedPipeline", _FakePipeline)

    with pytest.raises(RuntimeError, match="parse exploded"):
        ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=str(tmp_path / "test.db"), batch_size=1)

    assert "pipeline.abort" in events
    assert "db.close" in events
    assert events.index("pipeline.abort") < events.index("db.close")


def test_reingest_force_updates_headers(monkeypatch, tmp_path):
    """--reingest-bodies --force should update subject, sender_name, sender_email."""
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod
    from src.email_db import EmailDatabase
    from src.parse_olm import Email

    # First ingest: store emails with MIME-encoded subject and sender name.
    encoded_emails = [
        Email(
            message_id="<msg1@example.test>",
            subject="=?iso-8859-1?Q?Caf=E9?=",
            sender_name="=?utf-8?B?TMO8ZGVy?=",
            sender_email="old@example.test",
            to=["r@example.test"],
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
            message_id="<msg1@example.test>",
            subject="Café",
            sender_name="Lüder",
            sender_email="new@example.test",
            to=["r@example.test"],
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
    assert row["sender_email"] == "new@example.test"
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
            message_id="<msg1@example.test>",
            subject="=?utf-8?Q?encoded?=",
            sender_name="Old Name",
            sender_email="old@example.test",
            to=["r@example.test"],
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
            message_id="<msg1@example.test>",
            subject="decoded",
            sender_name="New Name",
            sender_email="new@example.test",
            to=["r@example.test"],
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
