# ruff: noqa: F401, I001
import queue
import threading
import time

import pytest

from src.ingest import _SENTINEL, _EmbedPipeline, main, parse_args

from .helpers.ingest_fixtures import _MockEmbedder, _make_mock_email


def test_ingest_inserts_exchange_entities(monkeypatch, tmp_path):
    """Exchange-extracted entities should be inserted into entities table during ingest."""
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod
    from src.email_db import EmailDatabase
    from src.parse_olm import Email

    email = Email(
        message_id="<msg1@example.test>",
        subject="With Exchange Data",
        sender_name="Sender",
        sender_email="sender@example.test",
        to=["r@example.test"],
        cc=[],
        bcc=[],
        date="2024-01-01T10:00:00",
        body_text="Hello world",
        body_html="",
        folder="Inbox",
        has_attachments=False,
        exchange_extracted_links=[{"url": "https://intranet.company.com"}],
        exchange_extracted_emails=["contact@example.test"],
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
        message_id="<analytics1@example.test>",
        subject="Test",
        sender_name="Alice",
        sender_email="alice@example.test",
        to=["bob@example.test"],
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
    row = db2.conn.execute(
        """
        SELECT detected_language, detected_language_confidence, detected_language_reason,
               detected_language_source, sentiment_label, sentiment_score
        FROM emails
        """
    ).fetchone()
    assert row["detected_language"] == "en"
    assert row["detected_language_confidence"] in {"medium", "high"}
    assert row["detected_language_reason"] == "stopword_overlap"
    assert row["detected_language_source"] == "body_text"
    assert row["sentiment_label"] is not None
    db2.close()


def test_reingest_analytics_prefers_forensic_text_and_handles_short_german_messages(tmp_path):
    """reingest_analytics() should use the best available text surface and recover short German mails."""
    from src.email_db import EmailDatabase
    from src.ingest import reingest_analytics
    from src.parse_olm import Email

    sqlite_file = str(tmp_path / "short-german.db")
    db = EmailDatabase(sqlite_file)
    email = Email(
        message_id="<analytics2@example.test>",
        subject="Kurznotiz",
        sender_name="Alice",
        sender_email="alice@example.test",
        to=["bob@example.test"],
        cc=[],
        bcc=[],
        date="2024-01-01T10:00:00",
        body_text="ok",
        body_html="",
        folder="Inbox",
        has_attachments=False,
        raw_body_text="zur Prüfung",
        forensic_body_text="zur Prüfung",
        forensic_body_source="raw_body_text",
    )
    db.insert_email(email)
    db.close()

    result = reingest_analytics(sqlite_path=sqlite_file)
    assert result["updated"] == 1

    db2 = EmailDatabase(sqlite_file)
    row = db2.conn.execute(
        """
        SELECT detected_language, detected_language_confidence, detected_language_reason,
               detected_language_source, sentiment_label
        FROM emails
        """
    ).fetchone()
    assert row["detected_language"] == "de"
    assert row["detected_language_confidence"] == "low"
    assert row["detected_language_reason"] == "short_text_stopword_vote"
    assert row["detected_language_source"] == "raw_body_text"
    assert row["sentiment_label"] is not None
    db2.close()


def test_reingest_analytics_skips_rows_without_usable_text(tmp_path):
    """reingest_analytics() should skip textless rows instead of raising."""
    from src.email_db import EmailDatabase
    from src.ingest import reingest_analytics
    from src.parse_olm import Email

    sqlite_file = str(tmp_path / "empty-text.db")
    db = EmailDatabase(sqlite_file)
    email = Email(
        message_id="<analytics-empty@example.test>",
        subject="",
        sender_name="Alice",
        sender_email="alice@example.test",
        to=["bob@example.test"],
        cc=[],
        bcc=[],
        date="2024-01-01T10:00:00",
        body_text="",
        body_html="",
        folder="Inbox",
        has_attachments=False,
    )
    db.insert_email(email)
    db.close()

    result = reingest_analytics(sqlite_path=sqlite_file)

    assert result["updated"] == 0
    assert result["skipped_empty_text_rows"] == 1


def test_reingest_analytics_persists_unknown_without_reprocessing(tmp_path):
    """Processed unknown-language rows should not reappear as missing analytics."""
    from src.email_db import EmailDatabase
    from src.ingest import reingest_analytics
    from src.parse_olm import Email

    sqlite_file = str(tmp_path / "unknown-language.db")
    db = EmailDatabase(sqlite_file)
    email = Email(
        message_id="<analytics-unknown@example.test>",
        subject="Mystery note",
        sender_name="Alice",
        sender_email="alice@example.test",
        to=["bob@example.test"],
        cc=[],
        bcc=[],
        date="2024-01-01T10:00:00",
        body_text="xyzzy plugh frotz gnusto rezrov",
        body_html="",
        folder="Inbox",
        has_attachments=False,
    )
    db.insert_email(email)
    db.close()

    first = reingest_analytics(sqlite_path=sqlite_file)
    assert first["updated"] == 1

    db2 = EmailDatabase(sqlite_file)
    row = db2.conn.execute(
        "SELECT detected_language, detected_language_reason FROM emails WHERE uid = ?",
        (email.uid,),
    ).fetchone()
    assert row["detected_language"] == "unknown"
    assert row["detected_language_reason"] == "score_below_threshold"
    db2.close()

    second = reingest_analytics(sqlite_path=sqlite_file)
    assert second["updated"] == 0
    assert second["total_missing"] == 0


def test_reingest_analytics_backfills_surface_rows_for_attachment_only_email(tmp_path):
    """reingest_analytics() should persist per-surface rows even when body text is empty."""
    from src.email_db import EmailDatabase
    from src.ingest import reingest_analytics
    from src.parse_olm import Email

    sqlite_file = str(tmp_path / "attachment-surface.db")
    db = EmailDatabase(sqlite_file)
    email = Email(
        message_id="<analytics-attachment@example.test>",
        subject="Anlage",
        sender_name="Alice",
        sender_email="alice@example.test",
        to=["bob@example.test"],
        cc=[],
        bcc=[],
        date="2024-01-01T10:00:00",
        body_text="",
        body_html="",
        folder="Inbox",
        has_attachments=True,
        attachment_names=["scan.pdf"],
        attachments=[
            {
                "name": "scan.pdf",
                "mime_type": "application/pdf",
                "size": 1024,
                "content_id": "",
                "is_inline": False,
                "normalized_text": "BEM Teilnahmeprotokoll",
            }
        ],
    )
    db.insert_email(email)
    db.close()

    result = reingest_analytics(sqlite_path=sqlite_file)
    assert result["updated"] == 1
    assert result["surface_rows_upserted"] >= 1

    db2 = EmailDatabase(sqlite_file)
    scopes = {
        row["surface_scope"]
        for row in db2.conn.execute(
            "SELECT surface_scope FROM language_surface_analytics WHERE email_uid = ?",
            (email.uid,),
        ).fetchall()
    }
    assert "attachment_text" in scopes
    db2.close()


def test_reingest_analytics_surface_backfill_is_idempotent(tmp_path):
    """Rows with existing analytics but missing surface rows should be backfilled once."""
    from src.email_db import EmailDatabase
    from src.ingest import reingest_analytics
    from src.parse_olm import Email

    sqlite_file = str(tmp_path / "surface-idempotent.db")
    db = EmailDatabase(sqlite_file)
    email = Email(
        message_id="<analytics-surface-idempotent@example.test>",
        subject="Status update",
        sender_name="Alice",
        sender_email="alice@example.test",
        to=["bob@example.test"],
        cc=[],
        bcc=[],
        date="2024-01-01T10:00:00",
        body_text="Please review the attached timeline and meeting notes.",
        body_html="",
        folder="Inbox",
        has_attachments=False,
    )
    db.insert_email(email)
    db.conn.execute(
        """
        UPDATE emails
        SET detected_language = 'en',
            detected_language_confidence = 'medium',
            detected_language_reason = 'stopword_overlap',
            detected_language_source = 'body_text',
            detected_language_token_count = 8,
            sentiment_label = 'neutral',
            sentiment_score = 0.0
        WHERE uid = ?
        """,
        (email.uid,),
    )
    db.conn.commit()
    db.close()

    first = reingest_analytics(sqlite_path=sqlite_file)
    assert first["updated"] == 1
    assert first["surface_rows_upserted"] >= 1

    db2 = EmailDatabase(sqlite_file)
    count_after_first = int(
        db2.conn.execute(
            "SELECT COUNT(*) AS c FROM language_surface_analytics WHERE email_uid = ?",
            (email.uid,),
        ).fetchone()["c"]
    )
    assert count_after_first >= 1
    db2.close()

    second = reingest_analytics(sqlite_path=sqlite_file)
    assert second["updated"] == 0
    assert second["total_missing"] == 0

    db3 = EmailDatabase(sqlite_file)
    count_after_second = int(
        db3.conn.execute(
            "SELECT COUNT(*) AS c FROM language_surface_analytics WHERE email_uid = ?",
            (email.uid,),
        ).fetchone()["c"]
    )
    assert count_after_second == count_after_first
    db3.close()


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
    states = db.conn.execute(
        "SELECT vector_status, attachment_status FROM email_ingest_state ORDER BY email_uid",
    ).fetchall()
    assert {row["vector_status"] for row in states} == {"completed"}
    assert {row["attachment_status"] for row in states} == {"not_requested"}
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


def test_ingest_persists_event_records_and_entity_occurrences(monkeypatch, tmp_path):
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod
    from src.conversation_segments import ConversationSegment
    from src.email_db import EmailDatabase

    email = _make_mock_email(1)
    email.body_text = "Bitte um Rueckmeldung bis spaetestens morgen."
    email.segments = [
        ConversationSegment(
            ordinal=0,
            segment_type="authored_body",
            depth=0,
            source_surface="body_text",
            text="Bitte SBV beteiligen und Rueckmeldung bis spaetestens morgen.",
            provenance={"kind": "test"},
        )
    ]
    email.attachments = [
        {
            "name": "note.txt",
            "mime_type": "text/plain",
            "size": 128,
            "content_id": "",
            "is_inline": False,
            "normalized_text": "AGG Gleichbehandlung Hinweis",
        }
    ]
    email.attachment_contents = [("note.txt", b"AGG Gleichbehandlung Hinweis")]

    class _Entity:
        def __init__(self, text: str, entity_type: str, normalized_form: str) -> None:
            self.text = text
            self.entity_type = entity_type
            self.normalized_form = normalized_form

    def _fake_entity_extractor(_text: str, _sender: str):
        return [_Entity("SBV", "organization", "sbv"), _Entity("Gleichbehandlung", "legal_reference", "gleichbehandlung")]

    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [email])
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email_dict: [{"chunk_id": f"{email_dict.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)
    monkeypatch.setattr(ingest_mod, "_resolve_entity_extractor", lambda _extract, _dry: _fake_entity_extractor)

    sqlite_file = str(tmp_path / "event-entity.db")
    stats = ingest_mod.ingest(
        "mock.olm",
        dry_run=False,
        sqlite_path=sqlite_file,
        extract_attachments=True,
        extract_entities=True,
    )
    assert stats["sqlite_inserted"] == 1

    db = EmailDatabase(sqlite_file)
    event_count = int(
        db.conn.execute("SELECT COUNT(*) AS c FROM event_records WHERE email_uid = ?", (email.uid,)).fetchone()["c"]
    )
    occurrence_count = int(
        db.conn.execute("SELECT COUNT(*) AS c FROM entity_occurrences WHERE email_uid = ?", (email.uid,)).fetchone()["c"]
    )
    assert event_count >= 1
    assert occurrence_count >= 1
    db.close()


def test_reingest_metadata_backfills_v7_fields(monkeypatch, tmp_path):
    """reingest_metadata should update categories, thread_topic, etc. for existing emails."""
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod
    from src.email_db import EmailDatabase
    from src.parse_olm import Email

    # First ingest: basic email without v7 metadata
    basic_email = Email(
        message_id="<msg1@example.test>",
        subject="Test",
        sender_name="Sender",
        sender_email="sender@example.test",
        to=["r@example.test"],
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
        message_id="<msg1@example.test>",
        subject="Test",
        sender_name="Sender",
        sender_email="sender@example.test",
        to=["r@example.test"],
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
