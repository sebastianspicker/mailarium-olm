"""Integration coverage for bounded vector publication and warm-query validity."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import mailarium.archive.vectors as storage_module
from mailarium.archive import open_archive_database
from mailarium.archive.vectors import SQLiteVectorCollection, get_vector_collection
from mailarium.ingestion.ingest_embed_pipeline import _EmbedPipeline
from mailarium.ingestion.records import ParsedMessage
from mailarium.model.chunks import EmailChunk
from mailarium.retrieval.embedder import EmailEmbedder


def _collection(database, vector_path: Path, *, model_id: str = "optimization-test") -> SQLiteVectorCollection:
    return get_vector_collection(
        database=database,
        vector_index_path=str(vector_path),
        model_id=model_id,
        model_revision="v1",
    )


def _add_vectors(
    collection: SQLiteVectorCollection,
    rows: list[tuple[str, str, list[float]]],
) -> None:
    collection.add(
        ids=[chunk_id for chunk_id, _uid, _embedding in rows],
        embeddings=[embedding for _chunk_id, _uid, embedding in rows],
        documents=[f"document for {chunk_id}" for chunk_id, _uid, _embedding in rows],
        metadatas=[{"uid": uid, "kind": "body"} for _chunk_id, uid, _embedding in rows],
    )


def _email(message_id: str) -> ParsedMessage:
    email = ParsedMessage(
        message_id=message_id,
        subject="Bounded vector checkpoint",
        sender_name="Sender",
        sender_email="sender@example.test",
        to=["recipient@example.test"],
        cc=[],
        bcc=[],
        date="2026-09-08T10:00:00",
        body_text="Precomputed vector content.",
        body_html="",
        folder="Inbox",
        has_attachments=False,
    )
    email_state: Any = email
    email_state._ingest_body_chunk_count = 1
    email_state._ingest_attachment_chunk_count = 0
    email_state._ingest_image_chunk_count = 0
    email_state._ingest_attachment_requested = False
    email_state._ingest_image_requested = False
    return email


def _chunk(email: ParsedMessage, embedding: list[float]) -> EmailChunk:
    return EmailChunk(
        uid=email.uid,
        chunk_id=f"{email.uid}__0",
        text=email.body_text,
        metadata={"uid": email.uid, "folder": email.folder},
        embedding=embedding,
    )


def _checkpoint_counter(monkeypatch: pytest.MonkeyPatch, embedder: EmailEmbedder) -> dict[str, int]:
    counts = {"text": 0, "image": 0}
    for name, collection in (("text", embedder.collection), ("image", embedder.image_collection)):
        original = collection._checkpoint_now

        def counted(*, _name=name, _original=original) -> None:
            counts[_name] += 1
            _original()

        monkeypatch.setattr(collection, "_checkpoint_now", counted)
    return counts


def test_add_batches_publish_each_vector_space_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Internal SQLite batches retain one high-level derived-index checkpoint."""
    runtime_home = tmp_path / "runtime"
    monkeypatch.setenv("MAILARIUM_RUNTIME_HOME", str(runtime_home))
    sqlite_path = runtime_home / "archive.db"
    database = open_archive_database(str(sqlite_path))
    embedder = EmailEmbedder(database, vector_index_path=str(runtime_home / "vectors"), sqlite_path=str(sqlite_path))
    counts = _checkpoint_counter(monkeypatch, embedder)
    chunks = [
        EmailChunk(
            uid=f"mail-{index}",
            chunk_id=f"mail-{index}__0",
            text=f"message {index}",
            metadata={"uid": f"mail-{index}"},
            embedding=[1.0, float(index)],
        )
        for index in range(5)
    ]
    try:
        assert embedder.add_chunks(chunks, batch_size=2) == 5
        assert counts == {"text": 1, "image": 1}
        assert embedder.collection.count() == 5
    finally:
        embedder.close()
        database.close()


def test_pipeline_owns_one_checkpoint_for_multiple_committed_batches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The bounded pipeline commits every SQLite batch but publishes its derived index once."""
    runtime_home = tmp_path / "runtime"
    monkeypatch.setenv("MAILARIUM_RUNTIME_HOME", str(runtime_home))
    sqlite_path = runtime_home / "archive.db"
    database = open_archive_database(str(sqlite_path))
    embedder = EmailEmbedder(database, vector_index_path=str(runtime_home / "vectors"), sqlite_path=str(sqlite_path))
    counts = _checkpoint_counter(monkeypatch, embedder)
    first = _email("first@example.test")
    second = _email("second@example.test")
    pipeline = _EmbedPipeline(embedder, database, entity_extractor_fn=None, batch_size=1)
    try:
        pipeline.start()
        pipeline.submit([_chunk(first, [1.0, 0.0])], [first])
        pipeline.submit([_chunk(second, [0.0, 1.0])], [second])
        pipeline.finish()
        assert counts == {"text": 1, "image": 1}
        assert pipeline.batches_written == 2
        assert database.conn.execute("SELECT COUNT(*) FROM vector_chunks").fetchone()[0] == 2
        completed = database.conn.execute("SELECT COUNT(*) FROM email_ingest_state WHERE vector_status = 'completed'").fetchone()[
            0
        ]
        assert completed == 2
    finally:
        embedder.close()
        database.close()


def test_checkpoint_failure_does_not_mask_bounded_operation_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Best-effort exceptional publication preserves the original operation failure."""
    database = open_archive_database(str(tmp_path / "archive.db"))
    collection = _collection(database, tmp_path / "vectors")

    def fail_checkpoint() -> None:
        raise RuntimeError("synthetic checkpoint failure")

    monkeypatch.setattr(collection, "_checkpoint_now", fail_checkpoint)
    try:
        with pytest.raises(ValueError, match="synthetic operation failure"):
            with collection.defer_checkpoints():
                collection.checkpoint()
                raise ValueError("synthetic operation failure")
    finally:
        collection.close()
        database.close()


def test_query_during_deferral_exactly_ranks_pending_same_count_upsert(tmp_path: Path) -> None:
    """A deferred same-count mutation cannot leave warm accelerator results stale."""
    database = open_archive_database(str(tmp_path / "archive.db"))
    collection = _collection(database, tmp_path / "vectors")
    distractors = [(f"other-{index}__0", f"other-{index}", [0.9, 0.01 * index]) for index in range(6)]
    try:
        _add_vectors(collection, [("target__0", "target", [-1.0, 0.0]), *distractors])
        assert collection.query(query_embeddings=[[1.0, 0.0]], n_results=1)["ids"] != [["target__0"]]
        with collection.defer_checkpoints():
            collection.upsert(
                ids=["target__0"],
                embeddings=[[1.0, 0.0]],
                documents=["updated target"],
                metadatas=[{"uid": "target", "kind": "body"}],
            )
            assert collection.query(query_embeddings=[[1.0, 0.0]], n_results=1)["ids"] == [["target__0"]]
        assert collection.query(query_embeddings=[[1.0, 0.0]], n_results=1)["ids"] == [["target__0"]]
    finally:
        collection.close()
        database.close()


def test_returning_preserves_stable_ids_and_duplicate_add_semantics(tmp_path: Path) -> None:
    """RETURNING removes per-row lookups without changing stable IDs or add rejection."""
    database = open_archive_database(str(tmp_path / "archive.db"))
    collection = _collection(database, tmp_path / "vectors")
    try:
        _add_vectors(collection, [("mail-1__0", "mail-1", [1.0, 0.0])])
        vector_id = database.conn.execute("SELECT vector_id FROM vector_chunks WHERE chunk_id = 'mail-1__0'").fetchone()[0]
        with pytest.raises(ValueError, match="Vector already exists"):
            _add_vectors(collection, [("mail-1__0", "mail-1", [0.0, 1.0])])
        statements: list[str] = []
        database.conn.set_trace_callback(statements.append)
        collection.upsert(
            ids=["mail-1__0"],
            embeddings=[[0.0, 1.0]],
            documents=["updated document"],
            metadatas=[{"uid": "mail-1", "kind": "body"}],
        )
        database.conn.set_trace_callback(None)
        updated = database.conn.execute("SELECT vector_id, document FROM vector_chunks WHERE chunk_id = 'mail-1__0'").fetchone()
        assert tuple(updated) == (vector_id, "updated document")
        assert not any("SELECT vector_id FROM vector_chunks WHERE chunk_id" in sql for sql in statements)
        assert collection.query(query_embeddings=[[0.0, 1.0]], n_results=1)["ids"] == [["mail-1__0"]]
    finally:
        database.conn.set_trace_callback(None)
        collection.close()
        database.close()


def test_uid_lookup_uses_scoped_index_and_returns_both_vector_spaces(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Mailbox dedupe performs one indexed UID query independent of unrelated IDs."""
    runtime_home = tmp_path / "runtime"
    monkeypatch.setenv("MAILARIUM_RUNTIME_HOME", str(runtime_home))
    sqlite_path = runtime_home / "archive.db"
    database = open_archive_database(str(sqlite_path))
    embedder = EmailEmbedder(database, vector_index_path=str(runtime_home / "vectors"), sqlite_path=str(sqlite_path))
    unrelated = [(f"other-{index}__0", f"other-{index}", [1.0, 0.0]) for index in range(200)]
    try:
        with embedder.defer_checkpoints():
            _add_vectors(embedder.collection, [*unrelated, ("target__text", "target", [1.0, 0.0])])
            _add_vectors(embedder.image_collection, [("target__image", "target", [0.0, 1.0])])
        statements: list[str] = []
        database.conn.set_trace_callback(statements.append)
        assert embedder.get_ids_for_uids(["target"]) == {"target__text", "target__image"}
        database.conn.set_trace_callback(None)
        selects = [sql for sql in statements if sql.lstrip().upper().startswith("SELECT")]
        assert len(selects) == 1
        assert "email_uid IN (SELECT value FROM json_each" in selects[0]
        plan = database.conn.execute(
            """EXPLAIN QUERY PLAN SELECT chunk_id FROM vector_chunks
               WHERE email_uid IN (SELECT value FROM json_each(?)) ORDER BY vector_id""",
            (json.dumps(["target"]),),
        ).fetchall()
        assert any("idx_vector_chunks_email_uid" in str(row[3]) for row in plan)
    finally:
        database.conn.set_trace_callback(None)
        embedder.close()
        database.close()


def test_forget_existing_ids_allows_deleted_chunk_to_be_added_again(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Scoped mailbox deletion can update lifecycle dedupe state without a full scan."""
    runtime_home = tmp_path / "runtime"
    monkeypatch.setenv("MAILARIUM_RUNTIME_HOME", str(runtime_home))
    sqlite_path = runtime_home / "archive.db"
    database = open_archive_database(str(sqlite_path))
    embedder = EmailEmbedder(database, vector_index_path=str(runtime_home / "vectors"), sqlite_path=str(sqlite_path))
    email = _email("readd@example.test")
    chunk = _chunk(email, [1.0, 0.0])
    try:
        assert embedder.add_chunks([chunk]) == 1
        assert chunk.chunk_id in embedder.get_existing_ids()
        embedder.collection.delete(ids=[chunk.chunk_id])
        embedder.image_collection.delete(ids=[chunk.chunk_id])
        embedder.forget_existing_ids([chunk.chunk_id])
        assert embedder.add_chunks([chunk]) == 1
        assert embedder.collection.count() == 1
    finally:
        embedder.close()
        database.close()


def test_warm_query_caches_integrity_but_explicit_verify_rehashes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Warm ranking avoids repeated full-file SHA work while verify remains exhaustive."""
    database = open_archive_database(str(tmp_path / "archive.db"))
    collection = _collection(database, tmp_path / "vectors")
    try:
        _add_vectors(collection, [("mail-1__0", "mail-1", [1.0, 0.0])])
        original_sha256 = storage_module._sha256_file
        calls = 0

        def counted_sha256(path: Path) -> str:
            nonlocal calls
            calls += 1
            return original_sha256(path)

        monkeypatch.setattr(storage_module, "_sha256_file", counted_sha256)
        assert collection.query(query_embeddings=[[1.0, 0.0]], n_results=1)["ids"] == [["mail-1__0"]]
        first_query_calls = calls
        assert collection.query(query_embeddings=[[1.0, 0.0]], n_results=1)["ids"] == [["mail-1__0"]]
        assert calls == first_query_calls == 1
        assert collection.verify()["healthy"] is True
        assert calls == 2
    finally:
        collection.close()
        database.close()


def test_cached_query_detects_file_corruption_and_recovers_from_sqlite(tmp_path: Path) -> None:
    """A changed derived file is rebuilt even after its checksum was cached."""
    database = open_archive_database(str(tmp_path / "archive.db"))
    collection = _collection(database, tmp_path / "vectors")
    try:
        _add_vectors(
            collection,
            [
                ("mail-1__0", "mail-1", [1.0, 0.0]),
                ("mail-2__0", "mail-2", [0.0, 1.0]),
            ],
        )
        assert collection.query(query_embeddings=[[0.0, 1.0]], n_results=1)["ids"] == [["mail-2__0"]]
        index_path = tmp_path / "vectors" / "text.usearch"
        index_path.write_bytes(b"\0" * index_path.stat().st_size)
        assert collection.query(query_embeddings=[[0.0, 1.0]], n_results=1)["ids"] == [["mail-2__0"]]
        assert collection.verify()["healthy"] is True
    finally:
        collection.close()
        database.close()


def test_cached_query_invalidates_for_cross_process_index_replacement(tmp_path: Path) -> None:
    """An independent canonical writer invalidates the warm accelerator and ranking state."""
    sqlite_path = tmp_path / "archive.db"
    first_database = open_archive_database(str(sqlite_path))
    first = _collection(first_database, tmp_path / "vectors")
    second_database = None
    second = None
    try:
        _add_vectors(first, [("mail-1__0", "mail-1", [1.0, 0.0])])
        assert first.query(query_embeddings=[[1.0, 0.0]], n_results=1)["ids"] == [["mail-1__0"]]
        second_database = open_archive_database(str(sqlite_path))
        second = _collection(second_database, tmp_path / "vectors")
        _add_vectors(second, [("mail-2__0", "mail-2", [0.0, 1.0])])
        assert first.query(query_embeddings=[[0.0, 1.0]], n_results=1)["ids"] == [["mail-2__0"]]
    finally:
        if second is not None:
            second.close()
        if second_database is not None:
            second_database.close()
        first.close()
        first_database.close()


def test_cached_query_detects_independent_generation_mutation_without_state_change(tmp_path: Path) -> None:
    """SQLite data-version invalidation catches generation changes without index-state edits."""
    sqlite_path = tmp_path / "archive.db"
    first_database = open_archive_database(str(sqlite_path))
    collection = _collection(first_database, tmp_path / "vectors")
    second_database = None
    try:
        _add_vectors(collection, [("mail-1__0", "mail-1", [1.0, 0.0])])
        assert collection.query(query_embeddings=[[1.0, 0.0]], n_results=1)["ids"] == [["mail-1__0"]]
        second_database = open_archive_database(str(sqlite_path))
        second_database.conn.execute("UPDATE vector_chunks SET model_id = 'different-generation'")
        second_database.conn.commit()
        with pytest.raises(ValueError, match="Embedding generation mismatch"):
            collection.query(query_embeddings=[[1.0, 0.0]], n_results=1)
    finally:
        if second_database is not None:
            second_database.close()
        collection.close()
        first_database.close()
