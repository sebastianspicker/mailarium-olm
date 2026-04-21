# ruff: noqa: F401, I001
import queue
import threading
import time

import pytest

from src.ingest import _SENTINEL, _EmbedPipeline, main, parse_args

from .helpers.ingest_fixtures import _MockEmbedder, _make_mock_email


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


def test_reembed_keeps_existing_body_chunks_when_upsert_fails(monkeypatch, tmp_path):
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod

    emails = [_make_mock_email(1)]
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: emails)
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email: [{"chunk_id": f"{email.get('uid', 'x')}__0"}],
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    sqlite_file = str(tmp_path / "test.db")
    ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file)

    delete_calls = []

    class _FailingEmbedder:
        def __init__(self, **_kw):
            self.collection = type("Collection", (), {"delete": lambda self, ids: delete_calls.append(list(ids))})()

        def set_sparse_db(self, db):
            pass

        def close(self):
            pass

        def get_existing_ids(self, refresh=False):
            return {f"{emails[0].uid}__0", f"{emails[0].uid}__1"}

        def upsert_chunks(self, chunks, batch_size=100):
            raise RuntimeError("upsert failed")

    monkeypatch.setattr("src.embedder.EmailEmbedder", _FailingEmbedder)

    with pytest.raises(RuntimeError, match="upsert failed"):
        ingest_mod.reembed(sqlite_path=sqlite_file)

    assert delete_calls == []


def test_reembed_deletes_only_obsolete_body_chunks_after_success(monkeypatch, tmp_path):
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod
    from src.chunker import EmailChunk

    emails = [_make_mock_email(1)]
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: emails)
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email: [
            EmailChunk(uid=email.get("uid", "x"), chunk_id=f"{email.get('uid', 'x')}__0", text="a", metadata={}),
            EmailChunk(uid=email.get("uid", "x"), chunk_id=f"{email.get('uid', 'x')}__1", text="b", metadata={}),
        ],
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    sqlite_file = str(tmp_path / "test.db")
    ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file)

    delete_calls = []

    class _TrackingEmbedder:
        def __init__(self, **_kw):
            self.collection = type("Collection", (), {"delete": lambda self, ids: delete_calls.append(list(ids))})()

        def set_sparse_db(self, db):
            pass

        def close(self):
            pass

        def get_existing_ids(self, refresh=False):
            return {f"{emails[0].uid}__0", f"{emails[0].uid}__1", f"{emails[0].uid}__2"}

        def upsert_chunks(self, chunks, batch_size=100):
            return len(chunks)

    monkeypatch.setattr("src.embedder.EmailEmbedder", _TrackingEmbedder)

    result = ingest_mod.reembed(sqlite_path=sqlite_file)

    assert result["chunks_deleted"] == 2
    assert delete_calls == [[f"{emails[0].uid}__1", f"{emails[0].uid}__2"]]
