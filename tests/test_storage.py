"""SQLite-authoritative vector collection contracts."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import numpy as np
import pytest

import mailarium.storage as storage_module
from mailarium.email_db import EmailDatabase
from mailarium.storage import SQLiteVectorCollection, _metadata_matches, to_builtin_list


def _collection(tmp_path):
    database = EmailDatabase(str(tmp_path / "mail.sqlite"))
    collection = SQLiteVectorCollection(
        sqlite_path=str(tmp_path / "mail.sqlite"),
        vector_index_path=str(tmp_path / "vectors.usearch"),
        embedding_space="text",
    )
    collection.attach_database(database)
    return collection


def test_to_builtin_list_converts_numpy():
    assert to_builtin_list(np.array([[1.0, 2.0]])) == [[1.0, 2.0]]


def test_metadata_filters_reject_unknown_operators() -> None:
    assert _metadata_matches({"score": 3}, {"score": {"$gte": 3}}) is True
    assert _metadata_matches({"score": 3}, {"score": {"$unknown": 3}}) is False


def test_sqlite_collection_add_get_query_and_delete(tmp_path):
    collection = _collection(tmp_path)
    collection.add(
        ids=["a", "b"],
        embeddings=[[1.0, 0.0], [0.0, 1.0]],
        documents=["alpha", "beta"],
        metadatas=[{"uid": "u1"}, {"uid": "u2"}],
    )
    assert collection.count() == 2
    assert collection.get(ids=["a"], include=["documents"])["documents"] == ["alpha"]
    assert collection.query(query_embeddings=[[1.0, 0.0]], n_results=1)["ids"] == [["a"]]
    collection.delete(ids=["a"])
    assert collection.count() == 1


def test_delete_treats_ids_as_data_and_handles_large_batches(tmp_path):
    text = _collection(tmp_path)
    image = SQLiteVectorCollection(
        sqlite_path=text.sqlite_path,
        vector_index_path=str(tmp_path / "image.usearch"),
        embedding_space="image",
    )
    image.attach_database(text._database)
    exact_ids = [f"bulk-{index}" for index in range(1_005)]
    exact_ids.extend(["') OR 1=1 --", "quote'comma,percent%underscore_", "nul-\x00-value"])
    text.add(
        ids=exact_ids,
        embeddings=[[1.0] for _ in exact_ids],
        documents=["synthetic" for _ in exact_ids],
        metadatas=[{} for _ in exact_ids],
    )
    image.add(
        ids=[exact_ids[0]],
        embeddings=[[1.0]],
        documents=["other space"],
        metadatas=[{}],
    )

    text.delete(ids=[*exact_ids, exact_ids[0]])
    text.delete(ids=[])

    assert text.count() == 0
    assert image.get(include=["documents"]) == {"ids": [exact_ids[0]], "documents": ["other space"]}


def test_embedding_spaces_are_isolated(tmp_path):
    text = _collection(tmp_path)
    image = SQLiteVectorCollection(
        sqlite_path=text.sqlite_path, vector_index_path=str(tmp_path / "image.usearch"), embedding_space="image"
    )
    image.attach_database(text._database)
    text.add(ids=["text"], embeddings=[[1.0]], documents=["text"], metadatas=[{"uid": "u"}])
    image.add(ids=["image"], embeddings=[[1.0]], documents=["image"], metadatas=[{"uid": "u"}])
    assert text.count() == image.count() == 1


@pytest.mark.parametrize(
    ("first_model", "second_model"),
    [
        ({"model_id": "model-a"}, {"model_id": "model-b"}),
        (
            {"model_id": "model-a", "model_revision": "revision-1"},
            {"model_id": "model-a", "model_revision": "revision-2"},
        ),
    ],
    ids=("model-id", "model-revision"),
)
def test_embedding_space_rejects_second_model_generation(tmp_path, first_model, second_model):
    first = SQLiteVectorCollection(
        sqlite_path=str(tmp_path / "mail.sqlite"),
        vector_index_path=str(tmp_path / "vectors"),
        **first_model,
    )
    first.add(ids=["a"], embeddings=[[1.0]], documents=["a"], metadatas=[{}])
    second = SQLiteVectorCollection(
        sqlite_path=first.sqlite_path,
        vector_index_path=str(tmp_path / "vectors"),
        **second_model,
    )

    with pytest.raises(ValueError, match="reset and re-embed"):
        second.query(query_embeddings=[[1.0]], n_results=1)
    with pytest.raises(ValueError, match="reset and re-embed"):
        second.add(ids=["b"], embeddings=[[1.0]], documents=["b"], metadatas=[{}])


def test_reset_allows_replacing_an_old_model_generation(tmp_path):
    first = SQLiteVectorCollection(
        sqlite_path=str(tmp_path / "mail.sqlite"),
        vector_index_path=str(tmp_path / "vectors"),
        model_id="model-a",
    )
    first.add(ids=["a"], embeddings=[[1.0]], documents=["a"], metadatas=[{}])
    replacement = SQLiteVectorCollection(
        sqlite_path=first.sqlite_path,
        vector_index_path=str(tmp_path / "vectors"),
        model_id="model-b",
    )

    assert replacement.reset() == 1
    replacement.add(ids=["b"], embeddings=[[1.0]], documents=["b"], metadatas=[{}])
    assert replacement.get(include=["documents"]) == {"ids": ["b"], "documents": ["b"]}


def test_get_filters_before_pagination_and_query_rejects_batches(tmp_path):
    collection = _collection(tmp_path)
    collection.add(
        ids=["a", "b", "c"],
        embeddings=[[1.0], [1.0], [1.0]],
        documents=["a", "b", "c"],
        metadatas=[{"keep": False}, {"keep": True}, {"keep": True}],
    )

    assert collection.get(where={"keep": True}, limit=1, offset=0)["ids"] == ["b"]
    assert collection.get(where={"keep": True}, limit=1, offset=1)["ids"] == ["c"]
    with pytest.raises(ValueError, match="exactly one"):
        collection.query(query_embeddings=[[1.0], [1.0]], n_results=1)


def test_query_uses_exact_fallback_when_accelerator_returns_too_few_rows(tmp_path, monkeypatch):
    collection = _collection(tmp_path)
    collection.add(
        ids=["a", "b"],
        embeddings=[[1.0], [1.0]],
        documents=["a", "b"],
        metadatas=[{}, {}],
    )

    class _IncompleteIndex:
        def search(self, _query, _requested):
            return argparse.Namespace(keys=[1])

    monkeypatch.setattr(collection, "_ensure_index", lambda: None)
    collection._index = _IncompleteIndex()
    collection._index_dimensions = 1

    result = collection.query(query_embeddings=[[1.0]], n_results=2, include=["documents"])

    assert result == {"ids": [["a", "b"]], "documents": [["a", "b"]]}


def test_attached_database_operation_is_reentrant_and_checkpoint_preserves_newer_journal(tmp_path, monkeypatch):
    collection = _collection(tmp_path)
    collection.add(ids=["a"], embeddings=[[1.0]], documents=["a"], metadatas=[{}])
    database = collection._database
    assert database is not None
    # The operation context used by EmailDatabase is deliberately reentrant.
    with database.operation():
        collection.upsert(ids=["a"], embeddings=[[1.0]], documents=["a"], metadatas=[{}])

    calls = 0

    class _Index:
        def save(self, path):
            Path(path).write_bytes(b"index")

    def inject_newer_operation(*_args):
        nonlocal calls
        calls += 1
        writer = sqlite3.connect(collection.sqlite_path)
        try:
            writer.execute("PRAGMA busy_timeout = 5000")
            writer.execute(
                "INSERT INTO vector_index_ops(embedding_space, operation, vector_id) VALUES(?, 'upsert', ?)",
                (collection.embedding_space, 1),
            )
            writer.commit()
        finally:
            writer.close()
        return _Index()

    monkeypatch.setattr(storage_module, "_build_usearch_index", inject_newer_operation)
    collection.checkpoint()
    assert calls == 2
    assert (
        database.conn.execute(
            "SELECT COUNT(*) FROM vector_index_ops WHERE embedding_space = ?", (collection.embedding_space,)
        ).fetchone()[0]
        == 2
    )


def test_index_state_requires_checksum_count_and_model_match(tmp_path, monkeypatch):
    collection = _collection(tmp_path)
    collection.add(ids=["a"], embeddings=[[1.0]], documents=["a"], metadatas=[{}])
    collection.vector_index_path.mkdir(parents=True, exist_ok=True)
    collection._index_file.write_bytes(b"not an index")
    collection._record_state(dimensions=1, applied_seq=0, item_count=99, file_sha256="wrong", status="healthy")
    collection._connection().commit()

    assert not collection._index_state_matches_storage(collection._index_file)
    restored = SQLiteVectorCollection(
        sqlite_path=collection.sqlite_path,
        vector_index_path=str(collection.vector_index_path),
    )
    restored.attach_database(collection._database)

    def unavailable_accelerator(*_args, **_kwargs):
        raise ImportError("synthetic unavailable accelerator")

    monkeypatch.setattr(storage_module, "_build_usearch_index", unavailable_accelerator)
    restored._ensure_index()
    assert restored.metadata["status"] == "usearch_unavailable"


def test_cached_usearch_index_reloads_after_another_connection_checkpoints(tmp_path):
    pytest.importorskip("usearch.index")
    writer = SQLiteVectorCollection(
        sqlite_path=str(tmp_path / "mail.sqlite"),
        vector_index_path=str(tmp_path / "vectors.usearch"),
    )
    reader = SQLiteVectorCollection(
        sqlite_path=writer.sqlite_path,
        vector_index_path=str(tmp_path / "vectors.usearch"),
    )
    writer.add(ids=["old"], embeddings=[[1.0, 0.0]], documents=["old"], metadatas=[{}])
    assert reader.query(query_embeddings=[[1.0, 0.0]], n_results=1)["ids"] == [["old"]]
    assert reader._index is not None

    writer.add(ids=["new"], embeddings=[[0.0, 1.0]], documents=["new"], metadatas=[{}])
    assert (
        writer._connection().execute("SELECT COUNT(*) FROM vector_index_ops WHERE embedding_space = ?", ("text",)).fetchone()[0]
        == 0
    )

    assert reader.query(query_embeddings=[[0.0, 1.0]], n_results=1)["ids"] == [["new"]]
