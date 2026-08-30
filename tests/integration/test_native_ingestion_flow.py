"""Production SQLite ingest-pipeline checks with deterministic precomputed vectors."""

from __future__ import annotations

import pytest

from mailarium.archive import open_archive_database
from mailarium.ingestion.ingest_embed_pipeline import _EmbedPipeline
from mailarium.ingestion.records import ParsedMessage
from mailarium.model.chunks import EmailChunk
from mailarium.retrieval.embedder import EmailEmbedder


def _email(message_id: str = "native@example.test") -> ParsedMessage:
    return ParsedMessage(
        message_id=message_id,
        subject="Native storage handoff",
        sender_name="Sender",
        sender_email="sender@example.test",
        to=["recipient@example.test"],
        cc=[],
        bcc=[],
        date="2026-08-28T10:00:00",
        body_text="Deterministic native pipeline evidence.",
        body_html="",
        folder="Inbox",
        has_attachments=False,
    )


def _chunk(email: ParsedMessage) -> EmailChunk:
    email._ingest_body_chunk_count = 1
    email._ingest_attachment_chunk_count = 0
    email._ingest_image_chunk_count = 0
    email._ingest_attachment_requested = False
    email._ingest_image_requested = False
    return EmailChunk(
        uid=email.uid,
        chunk_id=f"{email.uid}__0",
        text="Deterministic native pipeline evidence.",
        metadata={"uid": email.uid, "folder": "Inbox", "sender_email": "sender@example.test"},
        # A precomputed vector exercises the production write path without a
        # sentence-transformer load or model download.
        embedding=[1.0, 0.0],
    )


def _run_pipeline(embedder: EmailEmbedder, database, email: ParsedMessage, chunk: EmailChunk) -> _EmbedPipeline:
    pipeline = _EmbedPipeline(embedder, database, entity_extractor_fn=None, batch_size=8)
    pipeline.start()
    pipeline.submit([chunk], [email])
    pipeline.finish()
    return pipeline


def _runtime_paths(monkeypatch: pytest.MonkeyPatch, tmp_path):
    runtime_home = tmp_path / "runtime"
    monkeypatch.setenv("MAILARIUM_RUNTIME_HOME", str(runtime_home))
    return runtime_home / "archive.db", runtime_home / "vectors"


def test_native_pipeline_persists_sqlite_rows_vectors_and_a_reopened_collection(monkeypatch, tmp_path) -> None:
    """One real pipeline batch survives close/reopen and serves an exact vector query."""
    sqlite_path, vector_path = _runtime_paths(monkeypatch, tmp_path)
    database = open_archive_database(str(sqlite_path))
    embedder = EmailEmbedder(database, vector_index_path=str(vector_path), sqlite_path=str(sqlite_path))
    email = _email()

    try:
        pipeline = _run_pipeline(embedder, database, email, _chunk(email))
        assert pipeline.sqlite_inserted == pipeline.chunks_added == 1
        assert database.get_email_full(email.uid)["subject"] == "Native storage handoff"
        assert embedder.collection.count() == 1
    finally:
        embedder.close()
        database.close()

    reopened = open_archive_database(str(sqlite_path))
    reopened_embedder = EmailEmbedder(reopened, vector_index_path=str(vector_path), sqlite_path=str(sqlite_path))
    try:
        result = reopened_embedder.collection.query(
            query_embeddings=[[1.0, 0.0]],
            n_results=1,
            include=["documents", "metadatas", "distances"],
        )
        assert result["ids"] == [[f"{email.uid}__0"]]
        assert result["metadatas"][0][0]["uid"] == email.uid
        assert reopened_embedder.collection.verify()["healthy"] is True
    finally:
        reopened_embedder.close()
        reopened.close()


def test_native_pipeline_rolls_back_failed_batch_and_allows_a_clean_retry(monkeypatch, tmp_path) -> None:
    """A completion failure leaves neither canonical email nor vector rows before retry."""
    sqlite_path, vector_path = _runtime_paths(monkeypatch, tmp_path)
    database = open_archive_database(str(sqlite_path))
    embedder = EmailEmbedder(database, vector_index_path=str(vector_path), sqlite_path=str(sqlite_path))
    email = _email("retry@example.test")
    original_completion = database.mark_ingest_batch_completed

    def fail_completion(*_args, **_kwargs) -> None:
        raise RuntimeError("synthetic completion failure")

    monkeypatch.setattr(database, "mark_ingest_batch_completed", fail_completion)
    try:
        with pytest.raises(RuntimeError, match="synthetic completion failure"):
            _run_pipeline(embedder, database, email, _chunk(email))
        assert database.get_email_full(email.uid) is None
        assert embedder.collection.count() == 0

        monkeypatch.setattr(database, "mark_ingest_batch_completed", original_completion)
        retry = _run_pipeline(embedder, database, email, _chunk(email))
        assert retry.sqlite_inserted == retry.chunks_added == 1
        assert database.get_email_full(email.uid) is not None
        assert embedder.collection.count() == 1
    finally:
        embedder.close()
        database.close()
