# ruff: noqa: F401, I001
import queue
import threading
import time

import pytest

from src.ingest import _SENTINEL, _EmbedPipeline, main, parse_args

from .helpers.ingest_fixtures import _MockEmbedder, _make_mock_email


def test_exchange_entities_from_email_extracts_all_types():
    """_exchange_entities_from_email should extract URLs, emails, contacts, meetings."""
    from src.ingest import _exchange_entities_from_email
    from src.parse_olm import Email

    email = Email(
        message_id="<msg@example.test>",
        subject="Test",
        sender_name="Sender",
        sender_email="sender@example.test",
        to=["r@example.test"],
        cc=[],
        bcc=[],
        date="2024-01-01T10:00:00",
        body_text="Body",
        body_html="",
        folder="Inbox",
        has_attachments=False,
        exchange_extracted_links=[{"url": "https://example.com", "text": "Example"}],
        exchange_extracted_emails=["alice@example.test"],
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


def test_ingest_computes_language_and_sentiment(monkeypatch, tmp_path):
    """Ingest should auto-populate detected_language and sentiment columns."""
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod
    from src.email_db import EmailDatabase
    from src.parse_olm import Email

    email = Email(
        message_id="<lang1@example.test>",
        subject="Thank you",
        sender_name="Alice",
        sender_email="alice@example.test",
        to=["bob@example.test"],
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
    row = db.conn.execute(
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
        message_id="<msg1@example.test>",
        subject="Test",
        sender_name="Sender",
        sender_email="sender@example.test",
        to=["r@example.test"],
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


def test_reextract_entities_backfills_provenance_for_existing_archive(tmp_path):
    from src.email_db import EmailDatabase
    from src.entity_extractor import ExtractedEntity
    from src.ingest_reingest import reextract_entities_impl

    sqlite_file = str(tmp_path / "entities.db")
    db = EmailDatabase(sqlite_file)
    email = _make_mock_email(1)
    db.insert_email(email)
    db.insert_entities_batch(
        email.uid,
        [("https://example.com", "url", "https://example.com")],
    )
    db.close()

    result = reextract_entities_impl(
        sqlite_path=sqlite_file,
        entity_extractor_fn=lambda body, sender: [ExtractedEntity("https://example.com", "url", "https://example.com")],
        extractor_key="spacy_regex",
        extraction_version="1",
        force=False,
    )

    assert result["updated"] == 1
    db = EmailDatabase(sqlite_file)
    row = db.conn.execute("SELECT extractor_key, extraction_version FROM entity_mentions").fetchone()
    assert row["extractor_key"] == "spacy_regex"
    assert row["extraction_version"] == "1"
    db.close()


def test_ingest_persists_body_and_exchange_entity_provenance(monkeypatch, tmp_path):
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod
    from src.email_db import EmailDatabase
    from src.entity_extractor import extract_entities

    email = _make_mock_email(1)
    email.body_text = "Please review https://example.com for details."
    email.exchange_extracted_emails = ["exchange-only@example.com"]

    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [email])
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda e: [{"chunk_id": f"{e.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr(ingest_mod, "_resolve_entity_extractor", lambda _extract, _dry: extract_entities)
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    sqlite_file = str(tmp_path / "test.db")
    ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file, extract_entities=True)

    db = EmailDatabase(sqlite_file)
    rows = db.conn.execute("SELECT extractor_key, extraction_version FROM entity_mentions").fetchall()
    provenances = {(row["extractor_key"], row["extraction_version"]) for row in rows}
    assert ("regex_only", "1") in provenances
    assert ("exchange_metadata", "1") in provenances
    db.close()


def test_reextract_entities_preserves_exchange_only_entities(tmp_path):
    from src.email_db import EmailDatabase
    from src.ingest_reingest import reextract_entities_impl

    sqlite_file = str(tmp_path / "entities-preserve.db")
    db = EmailDatabase(sqlite_file)
    email = _make_mock_email(1)
    email.body_text = ""
    email.exchange_extracted_emails = ["exchange-preserve@example.com"]
    db.insert_email(email)
    db.insert_entities_batch(
        email.uid,
        [("exchange-preserve@example.com", "email", "exchange-preserve@example.com")],
        extractor_key="",
        extraction_version="",
    )
    db.close()

    result = reextract_entities_impl(
        sqlite_path=sqlite_file,
        entity_extractor_fn=lambda body, sender: [],
        extractor_key="spacy_regex",
        extraction_version="1",
        force=True,
    )

    assert result["updated"] == 1
    db = EmailDatabase(sqlite_file)
    rows = db.conn.execute(
        """
        SELECT ent.normalized_form, em.extractor_key, em.extraction_version
        FROM entity_mentions em
        JOIN entities ent ON ent.id = em.entity_id
        WHERE em.email_uid = ?
        """,
        (email.uid,),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["normalized_form"] == "exchange-preserve@example.com"
    assert rows[0]["extractor_key"] == "exchange_metadata"
    assert rows[0]["extraction_version"] == "1"
    db.close()


def test_reingest_metadata_is_idempotent_for_exchange_entities(monkeypatch, tmp_path):
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod
    from src.email_db import EmailDatabase

    email = _make_mock_email(1)
    email.exchange_extracted_emails = ["idempotent@example.com"]

    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [email])
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda e: [{"chunk_id": f"{e.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    sqlite_file = str(tmp_path / "metadata-idempotent.db")
    ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file)

    ingest_mod.reingest_metadata("mock.olm", sqlite_path=sqlite_file)
    ingest_mod.reingest_metadata("mock.olm", sqlite_path=sqlite_file)

    db = EmailDatabase(sqlite_file)
    row = db.conn.execute(
        """
        SELECT em.mention_count, em.extractor_key, em.extraction_version
        FROM entity_mentions em
        JOIN entities ent ON ent.id = em.entity_id
        WHERE em.email_uid = ? AND ent.normalized_form = ?
        """,
        (email.uid, "idempotent@example.com"),
    ).fetchone()
    assert row is not None
    assert row["mention_count"] == 1
    assert row["extractor_key"] == "exchange_metadata"
    assert row["extraction_version"] == "1"
    db.close()
