"""Provides deterministic email and embedder doubles for ingestion batching and persistence tests."""


def _make_mock_email(idx):
    """Build deterministic mock email data without external services."""
    from mailarium.parse_olm import Email

    return Email(
        message_id=f"<msg{idx}@test.com>",
        subject=f"Subject {idx}",
        sender_name="Sender",
        sender_email="sender@example.test",
        to=["recipient@example.test"],
        cc=[],
        bcc=[],
        date=f"2024-01-0{idx}T10:00:00",
        body_text=f"Body {idx}",
        body_html="",
        folder="Inbox",
        has_attachments=False,
    )


def _make_exchange_email(**overrides):
    """Build a stable email record with optional Exchange metadata fields."""
    from mailarium.parse_olm import Email

    defaults = {
        "message_id": "<msg@example.test>",
        "subject": "Test",
        "sender_name": "Sender",
        "sender_email": "sender@example.test",
        "to": ["r@example.test"],
        "cc": [],
        "bcc": [],
        "date": "2024-01-01T10:00:00",
        "body_text": "Body",
        "body_html": "",
        "folder": "Inbox",
        "has_attachments": False,
    }
    defaults.update(overrides)
    return Email(**defaults)


def _make_minimal_ingest_email(idx):
    """Build a lightweight parser result for dry-run count and progress tests."""

    class _Email:
        def __init__(self, number):
            self.idx = number
            self.uid = f"uid-{number}"
            self.attachment_contents = []

        def to_dict(self):
            return {"id": self.idx, "uid": self.uid}

    return _Email(idx)


def _make_header_email(*, subject, sender_name, sender_email, body_text):
    """Build a stable email record for header reingestion tests."""
    from mailarium.parse_olm import Email

    return Email(
        message_id="<msg1@example.test>",
        subject=subject,
        sender_name=sender_name,
        sender_email=sender_email,
        to=["r@example.test"],
        cc=[],
        bcc=[],
        date="2024-01-01T10:00:00",
        body_text=body_text,
        body_html="",
        folder="Inbox",
        has_attachments=False,
    )


def _make_mock_image_email(idx=1, *, filename=None):
    """Build a mock email with one deterministic PNG attachment payload."""
    email = _make_mock_email(idx)
    filename = filename or f"photo-{idx}.png"
    email.has_attachments = True
    email.attachment_names = [filename]
    email.attachments = [
        {
            "name": filename,
            "mime_type": "image/png",
            "size": 128,
            "content_id": "",
            "is_inline": False,
        }
    ]
    email.attachment_contents = [(filename, b"fake-image")]
    return email


def _seed_degraded_image_ingest(monkeypatch, tmp_path, *, filename="photo.png"):
    """Seed one image attachment while OCR is unavailable, ready for reprocessing tests."""
    email = _make_mock_image_email(filename=filename)
    monkeypatch.setattr("mailarium.attachment_extractor.image_ocr_available", lambda: False)
    monkeypatch.setattr("mailarium.attachment_extractor.extract_image_text_ocr", lambda *_args, **_kwargs: None)
    ingest_mod, sqlite_file = _seed_ingest_database(monkeypatch, tmp_path, [email], extract_attachments=True)
    return ingest_mod, sqlite_file, email


def _configure_ocr_reparse(monkeypatch, ingest_mod, *, filename="photo.png", recovered_text="Recovered screenshot text"):
    """Configure deterministic OCR recovery for a fresh reparse of one image attachment."""
    monkeypatch.setattr(
        ingest_mod,
        "parse_olm",
        lambda _path, **_kw: [_make_mock_image_email(filename=filename)],
    )
    monkeypatch.setattr("mailarium.attachment_extractor.image_ocr_available", lambda: True)
    monkeypatch.setattr(
        "mailarium.attachment_extractor.extract_image_text_ocr",
        lambda *_args, **_kwargs: recovered_text,
    )


def _seed_ingest_database(
    monkeypatch,
    tmp_path,
    emails,
    *,
    chunk_email=None,
    extract_attachments=False,
    database_name="test.db",
    embedder_cls=None,
    return_stats=False,
    ingest_kwargs=None,
    dry_run=False,
):
    """Ingest deterministic emails into a temporary SQLite database for follow-up tests."""
    import mailarium.embedder as embedder_mod
    import mailarium.ingest as ingest_mod

    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: emails)
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        chunk_email or (lambda email: [{"chunk_id": f"{email.get('uid', 'x')}-a"}]),
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", embedder_cls or _MockEmbedder)

    sqlite_file = str(tmp_path / database_name)
    stats = ingest_mod.ingest(
        "mock.olm",
        dry_run=dry_run,
        sqlite_path=sqlite_file,
        extract_attachments=extract_attachments,
        **(ingest_kwargs or {}),
    )
    if return_stats:
        return ingest_mod, sqlite_file, stats
    return ingest_mod, sqlite_file


def _record_collection_delete(delete_calls, on_delete, ids):
    return (
        delete_calls.append(list(ids)) if delete_calls is not None else None,
        on_delete(ids) if on_delete is not None else None,
    )


def _record_reembed_upsert(chunks, *, error, received_chunks, upsert_calls, on_upsert):
    if error is not None:
        raise error
    if received_chunks is not None:
        received_chunks.extend(chunks)
    if upsert_calls is not None:
        upsert_calls.append([chunk.chunk_id for chunk in chunks])
    if on_upsert is not None:
        on_upsert(chunks)
    return len(chunks)


def _make_reembed_embedder(
    *,
    existing_ids=(),
    received_chunks=None,
    upsert_calls=None,
    error=None,
    delete_calls=None,
    id_lookups=None,
    on_upsert=None,
    on_delete=None,
):
    """Build a configurable reembed fake with observable chunk, lookup, and delete behavior."""

    class _Reembedder:
        def __init__(self, **_kw):
            self.collection = type(
                "Collection",
                (),
                {"delete": lambda _self, ids=None, **_kwargs: _record_collection_delete(delete_calls, on_delete, ids)},
            )()

        def set_sparse_db(self, db):
            pass

        def close(self):
            pass

        def get_existing_ids(self, refresh=False):
            if id_lookups is not None:
                id_lookups.append(refresh)
            return set(existing_ids)

        def delete_chunks_by_uid(self, uid):
            return 0

        def upsert_chunks(self, chunks, batch_size=100):
            return _record_reembed_upsert(
                chunks,
                error=error,
                received_chunks=received_chunks,
                upsert_calls=upsert_calls,
                on_upsert=on_upsert,
            )

    return _Reembedder


def _make_ingest_pipeline(embedder, email_db, *, entity_extractor_fn=None):
    """Build an ingest pipeline with WAL checkpoints disabled for deterministic unit tests."""
    from mailarium.ingest import _EmbedPipeline

    pipeline = _EmbedPipeline(
        embedder=embedder,
        email_db=email_db,
        entity_extractor_fn=entity_extractor_fn,
        batch_size=100,
    )
    pipeline._wal_checkpoint_interval = 0
    return pipeline


def _make_pipeline_embedder(*, existing_ids, error=None, seen_chunk_ids=None):
    """Build an embedder fake that records accepted chunks or raises a configured error."""
    from unittest.mock import MagicMock

    class _Embedder:
        def __init__(self):
            self.collection = MagicMock()

        def add_chunks(self, chunks, **_kw):
            if error is not None:
                raise error
            if seen_chunk_ids is not None:
                seen_chunk_ids.extend(str(chunk.chunk_id) for chunk in chunks)
            return len(chunks)

        def get_existing_ids(self, refresh=False):
            return existing_ids

    return _Embedder()


def _make_ingest_body_chunks(*emails):
    """Mark emails as body-chunked and return their deterministic body chunks."""
    from mailarium.chunker import EmailChunk

    chunks = []
    for email in emails:
        email._ingest_body_chunk_count = 1
        email._ingest_attachment_chunk_count = 0
        email._ingest_image_chunk_count = 0
        email._ingest_attachment_requested = False
        email._ingest_image_requested = False
        chunks.append(EmailChunk(uid=email.uid, chunk_id=f"{email.uid}__0", text="hello", metadata={"uid": email.uid}))
    return chunks


class _MockEmbedder:
    """Count ingested chunks without loading a vector model or writing an index."""

    def __init__(self, **_kw):
        """Initialize the observable chunk count and stable mock model metadata."""
        self.vector_index_path = "mock"
        self.model_name = "mock"
        self._count = 0

    def count(self):
        """Return the number of chunks accepted by this fake."""
        return self._count

    def add_chunks(self, chunks, **_kw):
        """Record a batch as indexed and return its accepted chunk count."""
        self._count += len(chunks)
        return len(chunks)

    def set_sparse_db(self, db):
        """Accept sparse-database wiring without introducing storage side effects."""

    def warmup(self):
        """Model a successful no-op warmup for ingestion tests."""
