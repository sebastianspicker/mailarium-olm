"""Extended tests for src/embedder.py beyond the basic guards."""

from __future__ import annotations

import pytest

from src.chunker import EmailChunk
from src.embedder import EmailEmbedder


def _make_chunk(uid: str = "uid1", index: int = 0, text: str = "Hello world") -> EmailChunk:
    return EmailChunk(
        uid=uid,
        chunk_id=f"{uid}__{index}",
        text=text,
        metadata={"uid": uid, "chunk_index": str(index)},
    )


@pytest.fixture(autouse=True)
def _stub_multi_vector_embedder(stub_multi_vector_embedder):
    import src.embedder as embedder_mod

    stub_multi_vector_embedder(embedder_mod)


# ── add_chunks ───────────────────────────────────────────────────────


def test_add_chunks_empty_list(tmp_path):
    embedder = EmailEmbedder(chromadb_path=str(tmp_path / "db"))
    result = embedder.add_chunks([])
    assert result == 0
    assert embedder.count() == 0


def test_add_chunks_single_chunk(tmp_path):
    embedder = EmailEmbedder(chromadb_path=str(tmp_path / "db"))
    chunks = [_make_chunk()]
    added = embedder.add_chunks(chunks, batch_size=100)
    assert added == 1
    assert embedder.count() == 1


def test_add_chunks_skips_existing(tmp_path):
    embedder = EmailEmbedder(chromadb_path=str(tmp_path / "db"))
    chunk = _make_chunk()
    embedder.add_chunks([chunk], batch_size=100)
    assert embedder.count() == 1

    # Adding the same chunk again should skip it
    added = embedder.add_chunks([chunk], batch_size=100)
    assert added == 0
    assert embedder.count() == 1


def test_add_chunks_multiple_batches(tmp_path):
    embedder = EmailEmbedder(chromadb_path=str(tmp_path / "db"))
    chunks = [_make_chunk(uid=f"uid{i}", index=0) for i in range(5)]

    # batch_size=2 means 3 batches: [2, 2, 1]
    added = embedder.add_chunks(chunks, batch_size=2)
    assert added == 5
    assert embedder.count() == 5


def test_add_chunks_rejects_non_positive_batch_size():
    embedder = EmailEmbedder.__new__(EmailEmbedder)
    with pytest.raises(ValueError, match="batch_size must be a positive integer"):
        embedder.add_chunks([], batch_size=0)
    with pytest.raises(ValueError, match="batch_size must be a positive integer"):
        embedder.add_chunks([], batch_size=-1)


# ── get_existing_ids ─────────────────────────────────────────────────


def test_get_existing_ids_empty(tmp_path):
    embedder = EmailEmbedder(chromadb_path=str(tmp_path / "db"))
    ids = embedder.get_existing_ids()
    assert ids == set()


def test_get_existing_ids_after_insert(tmp_path):
    embedder = EmailEmbedder(chromadb_path=str(tmp_path / "db"))
    embedder.add_chunks([_make_chunk(uid="a"), _make_chunk(uid="b")], batch_size=100)

    ids = embedder.get_existing_ids(refresh=True)
    assert "a__0" in ids
    assert "b__0" in ids
    assert len(ids) == 2


def test_get_existing_ids_cached(tmp_path):
    embedder = EmailEmbedder(chromadb_path=str(tmp_path / "db"))
    ids1 = embedder.get_existing_ids()
    ids2 = embedder.get_existing_ids()
    # Should return the same set object (cached)
    assert ids1 is ids2


def test_get_existing_ids_refresh(tmp_path):
    embedder = EmailEmbedder(chromadb_path=str(tmp_path / "db"))
    ids1 = embedder.get_existing_ids()
    ids2 = embedder.get_existing_ids(refresh=True)
    # refresh=True creates a new set
    assert ids1 is not ids2


# ── count ────────────────────────────────────────────────────────────


def test_get_existing_ids_skips_scan_for_empty_collection(tmp_path, monkeypatch):
    """When collection is empty, iter_collection_ids should not be called."""
    embedder = EmailEmbedder(chromadb_path=str(tmp_path / "db"))
    assert embedder.collection.count() == 0

    import src.embedder as embedder_mod

    def _should_not_be_called(*_a, **_kw):
        raise AssertionError("iter_collection_ids should not be called for empty collection")

    monkeypatch.setattr(embedder_mod, "iter_collection_ids", _should_not_be_called)

    ids = embedder.get_existing_ids()
    assert ids == set()


# ── count ────────────────────────────────────────────────────────────


def test_count_empty(tmp_path):
    embedder = EmailEmbedder(chromadb_path=str(tmp_path / "db"))
    assert embedder.count() == 0


def test_count_after_inserts(tmp_path):
    embedder = EmailEmbedder(chromadb_path=str(tmp_path / "db"))
    embedder.add_chunks([_make_chunk(uid="x", index=0), _make_chunk(uid="y", index=0)], batch_size=100)
    assert embedder.count() == 2


# ── sparse DB sharing ────────────────────────────────────────────────


def test_set_sparse_db_is_used_by_store_sparse(tmp_path):
    """set_sparse_db() should be used instead of creating new connections."""
    from unittest.mock import MagicMock

    embedder = EmailEmbedder(chromadb_path=str(tmp_path / "db"))
    mock_db = MagicMock()
    mock_db.insert_sparse_batch = MagicMock(return_value=2)
    embedder.set_sparse_db(mock_db)

    embedder._store_sparse(["id1", "id2"], [{1: 0.5}, {2: 0.3}])
    mock_db.insert_sparse_batch.assert_called_once_with(["id1", "id2"], [{1: 0.5}, {2: 0.3}])


def test_store_sparse_fallback_creates_one_connection(tmp_path):
    """Without set_sparse_db, fallback should create only one connection."""
    import dataclasses

    from src.email_db import EmailDatabase

    sqlite_path = str(tmp_path / "test.db")
    # Create the DB file so the path check passes (access conn to trigger lazy init)
    db = EmailDatabase(sqlite_path)
    _ = db.conn  # force file creation
    db.close()

    embedder = EmailEmbedder(chromadb_path=str(tmp_path / "db"))
    embedder.settings = dataclasses.replace(embedder.settings, sqlite_path=sqlite_path)

    embedder._store_sparse(["id1"], [{1: 0.5}])
    first_fallback = embedder._sparse_db_fallback
    assert first_fallback is not None

    embedder._store_sparse(["id2"], [{2: 0.3}])
    assert embedder._sparse_db_fallback is first_fallback  # same object

    embedder.close()
    assert embedder._sparse_db_fallback is None


# ── warmup ────────────────────────────────────────────────────────


def test_warmup_forces_model_load(tmp_path):
    """warmup() should trigger model loading and a test encode."""
    embedder = EmailEmbedder(chromadb_path=str(tmp_path / "db"))
    assert embedder._embedder is None  # not yet loaded
    embedder.warmup()
    assert embedder._embedder is not None  # now loaded


# ── encode-then-store (single GPU pass) ──────────────────────────


def test_add_chunks_encodes_all_at_once(tmp_path, monkeypatch):
    """add_chunks() should call encode_all() exactly once regardless of storage batch_size."""
    embedder = EmailEmbedder(chromadb_path=str(tmp_path / "db"))

    encode_call_count = 0
    original_encode_all = embedder.embedder.encode_all

    def _counting_encode(texts):
        nonlocal encode_call_count
        encode_call_count += 1
        return original_encode_all(texts)

    monkeypatch.setattr(embedder.embedder, "encode_all", _counting_encode)

    chunks = [_make_chunk(uid=f"uid{i}", index=0) for i in range(10)]
    # storage batch_size=3 means 4 ChromaDB writes, but only 1 encode call
    added = embedder.add_chunks(chunks, batch_size=3)
    assert added == 10
    assert encode_call_count == 1


def test_add_chunks_handles_pre_embedded_chunks(tmp_path):
    """Pre-embedded chunks should be stored without re-encoding."""
    embedder = EmailEmbedder(chromadb_path=str(tmp_path / "db"))

    pre_embedded = EmailChunk(
        uid="img1",
        chunk_id="img1__0",
        text="[Image: photo.jpg]",
        metadata={"uid": "img1", "chunk_type": "image"},
        embedding=[0.5, 0.6, 0.7],
    )
    text_chunk = _make_chunk(uid="txt1", index=0)

    added = embedder.add_chunks([pre_embedded, text_chunk], batch_size=100)
    assert added == 2
    assert embedder.count() == 2


def test_add_chunks_skip_existing_check_avoids_existing_id_scan(tmp_path, monkeypatch):
    embedder = EmailEmbedder(chromadb_path=str(tmp_path / "db"))

    def _should_not_be_called(*_args, **_kwargs):
        raise AssertionError("get_existing_ids should not be called when skip_existing_check=True")

    monkeypatch.setattr(embedder, "get_existing_ids", _should_not_be_called)
    added = embedder.add_chunks([_make_chunk(uid="fast", index=0)], batch_size=100, skip_existing_check=True)
    assert added == 1
    assert embedder.count() == 1


def test_upsert_chunks_encodes_all_at_once(tmp_path, monkeypatch):
    """upsert_chunks() should call encode_all() exactly once."""
    embedder = EmailEmbedder(chromadb_path=str(tmp_path / "db"))

    encode_call_count = 0
    original_encode_all = embedder.embedder.encode_all

    def _counting_encode(texts):
        nonlocal encode_call_count
        encode_call_count += 1
        return original_encode_all(texts)

    monkeypatch.setattr(embedder.embedder, "encode_all", _counting_encode)

    chunks = [_make_chunk(uid=f"uid{i}", index=0) for i in range(5)]
    added = embedder.upsert_chunks(chunks, batch_size=2)
    assert added == 5
    assert encode_call_count == 1
