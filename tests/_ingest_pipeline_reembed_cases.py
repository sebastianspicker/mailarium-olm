# ruff: noqa: I001

"""Reembedding recovery, replacement, empty-mail handling, and obsolete-chunk deletion behavior."""

import pytest
from types import SimpleNamespace


from .helpers.ingest_fixtures import _make_mock_email, _make_reembed_embedder, _seed_ingest_database


def test_multibatch_reembed_restores_prior_chunks_after_partial_upsert_failure():
    from mailarium.ingest_reingest import _upsert_reembed_chunks

    old_state = {
        "uid__0": ([0.1], "old zero", {"version": "old"}),
        "uid__1": ([0.2], "old one", {"version": "old"}),
    }

    class _Collection:
        def __init__(self):
            self.state = dict(old_state)

        def get(self, ids, include):
            del include
            present = [chunk_id for chunk_id in ids if chunk_id in self.state]
            return {
                "ids": present,
                "embeddings": [self.state[chunk_id][0] for chunk_id in present],
                "documents": [self.state[chunk_id][1] for chunk_id in present],
                "metadatas": [self.state[chunk_id][2] for chunk_id in present],
            }

        def delete(self, ids):
            for chunk_id in ids:
                self.state.pop(chunk_id, None)

        def upsert(self, ids, embeddings, documents, metadatas):
            for index, chunk_id in enumerate(ids):
                self.state[chunk_id] = (embeddings[index], documents[index], metadatas[index])

    class _Embedder:
        def __init__(self):
            self.collection = _Collection()

        def upsert_chunks(self, chunks, batch_size):
            del batch_size
            first = chunks[0]
            self.collection.state[first.chunk_id] = ([9.9], first.text, {"version": "new"})
            raise RuntimeError("second batch failed")

    embedder = _Embedder()
    chunks = [
        SimpleNamespace(chunk_id="uid__2", text="new two"),
        SimpleNamespace(chunk_id="uid__0", text="new zero"),
        SimpleNamespace(chunk_id="uid__1", text="new one"),
    ]

    with pytest.raises(RuntimeError, match="second batch failed"):
        _upsert_reembed_chunks(
            embedder,
            chunks,
            old_ids=["uid__0", "uid__1"],
            new_ids={chunk.chunk_id for chunk in chunks},
            batch_size=1,
        )

    assert embedder.collection.state == old_state


def test_reembed_rechunks_and_upserts(monkeypatch, tmp_path):
    """reembed() should read body text from SQLite, re-chunk, and upsert embeddings."""
    emails = [_make_mock_email(i) for i in range(1, 3)]
    ingest_mod, sqlite_file = _seed_ingest_database(monkeypatch, tmp_path, emails)
    vector_index_dir = str(tmp_path / "vector-index")

    # Track what reembed does
    upserted_chunks = []

    monkeypatch.setattr(
        "mailarium.embedder.EmailEmbedder",
        _make_reembed_embedder(received_chunks=upserted_chunks),
    )

    result = ingest_mod.reembed(vector_index_path=vector_index_dir, sqlite_path=sqlite_file)
    assert result["reembedded"] == 2
    assert result["chunks_added"] == len(upserted_chunks)
    assert result["skipped_no_body"] == 0
    assert len(upserted_chunks) >= 2  # At least 1 chunk per email


def test_reembed_skips_emails_without_body(monkeypatch, tmp_path):
    """reembed() should skip emails with empty body text."""
    from mailarium.email_db import EmailDatabase

    emails = [_make_mock_email(1)]
    ingest_mod, sqlite_file = _seed_ingest_database(monkeypatch, tmp_path, emails)

    # Wipe body text to simulate missing body
    db = EmailDatabase(sqlite_file)
    db.conn.execute("UPDATE emails SET body_text = ''")
    db.conn.commit()
    db.close()

    monkeypatch.setattr("mailarium.embedder.EmailEmbedder", _make_reembed_embedder())

    result = ingest_mod.reembed(sqlite_path=sqlite_file)
    assert result["reembedded"] == 0
    assert result["skipped_no_body"] == 1


def test_reembed_empty_database(monkeypatch, tmp_path):
    """reembed() should handle empty database gracefully."""
    import mailarium.ingest as ingest_mod
    from mailarium.email_db import EmailDatabase

    sqlite_file = str(tmp_path / "test.db")
    db = EmailDatabase(sqlite_file)
    db.close()

    result = ingest_mod.reembed(sqlite_path=sqlite_file)
    assert result["reembedded"] == 0
    assert result["total"] == 0


def test_reembed_keeps_existing_body_chunks_when_upsert_fails(monkeypatch, tmp_path):
    emails = [_make_mock_email(1)]
    ingest_mod, sqlite_file = _seed_ingest_database(
        monkeypatch,
        tmp_path,
        emails,
        chunk_email=lambda email: [{"chunk_id": f"{email.get('uid', 'x')}__0"}],
    )

    delete_calls = []
    monkeypatch.setattr(
        "mailarium.embedder.EmailEmbedder",
        _make_reembed_embedder(
            existing_ids={f"{emails[0].uid}__0", f"{emails[0].uid}__1"},
            error=RuntimeError("upsert failed"),
            delete_calls=delete_calls,
        ),
    )

    with pytest.raises(RuntimeError, match="upsert failed"):
        ingest_mod.reembed(sqlite_path=sqlite_file)

    assert delete_calls == []


def test_reembed_deletes_only_obsolete_body_chunks_after_success(monkeypatch, tmp_path):
    from mailarium.chunker import EmailChunk

    emails = [_make_mock_email(1)]
    ingest_mod, sqlite_file = _seed_ingest_database(
        monkeypatch,
        tmp_path,
        emails,
        chunk_email=lambda email: [
            EmailChunk(uid=email.get("uid", "x"), chunk_id=f"{email.get('uid', 'x')}__0", text="a", metadata={}),
            EmailChunk(uid=email.get("uid", "x"), chunk_id=f"{email.get('uid', 'x')}__1", text="b", metadata={}),
        ],
    )

    delete_calls = []
    operations = []
    monkeypatch.setattr(
        "mailarium.embedder.EmailEmbedder",
        _make_reembed_embedder(
            existing_ids={f"{emails[0].uid}__0", f"{emails[0].uid}__1", f"{emails[0].uid}__2"},
            delete_calls=delete_calls,
            on_upsert=lambda _chunks: operations.append("upsert"),
            on_delete=lambda _ids: operations.append("delete"),
        ),
    )

    result = ingest_mod.reembed(sqlite_path=sqlite_file)

    assert result["chunks_deleted"] == 2
    assert delete_calls == [[f"{emails[0].uid}__1", f"{emails[0].uid}__2"]]
    assert operations == ["upsert", "delete"]
