"""Dense, learned-sparse, BM25, and hybrid retrieval over canonical SQLite vectors."""

from __future__ import annotations

from mailarium.archive import open_archive_database
from mailarium.retrieval.retriever import SearchEngine


class _DeterministicEmbedder:
    """Small local-only encoder for exercising retrieval channel routing."""

    has_sparse = True

    def encode_dense(self, queries: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] if "handoff" in query else [0.0, 1.0] for query in queries]

    def encode_sparse_query(self, queries: list[str]) -> list[dict[int, float]]:
        return [{7: 1.0} if "needle" in query else {8: 1.0} for query in queries]


def test_canonical_collection_serves_dense_bm25_sparse_and_hybrid_channels(monkeypatch, tmp_path) -> None:
    """Each channel reads the same SQLite-owned corpus without loading a model."""
    runtime_home = tmp_path / "runtime"
    monkeypatch.setenv("MAILARIUM_RUNTIME_HOME", str(runtime_home))
    monkeypatch.setenv("RERANK_ENABLED", "false")
    monkeypatch.setenv("HYBRID_ENABLED", "false")
    sqlite_path = runtime_home / "archive.db"
    database = open_archive_database(str(sqlite_path))
    engine = SearchEngine(
        vector_index_path=str(runtime_home / "vectors"),
        sqlite_path=str(sqlite_path),
        sparse_enabled=True,
        image_search_enabled=False,
        database=database,
    )
    engine._embedder = _DeterministicEmbedder()
    engine.collection.add(
        ids=["dense__0", "keyword__0"],
        embeddings=[[1.0, 0.0], [0.0, 1.0]],
        documents=["routine delivery note", "needle-only escalation record"],
        metadatas=[
            {"uid": "dense", "folder": "Inbox", "sender_email": "sender@example.test"},
            {"uid": "keyword", "folder": "Inbox", "sender_email": "sender@example.test"},
        ],
    )
    database.insert_sparse_batch(
        ["dense__0", "keyword__0"],
        [{8: 1.0}, {7: 1.0}],
        model_id=engine.settings.sparse_model,
        model_revision=engine.settings.sparse_model_revision,
    )
    try:
        dense = engine.search_filtered("handoff", top_k=1)
        bm25 = engine._get_bm25_results("needle", 2)
        sparse = engine._get_sparse_results("needle", 2)
        hybrid = engine.search_filtered("needle", top_k=2, hybrid=True)

        assert [result.chunk_id for result in dense] == ["dense__0"]
        assert bm25 and bm25[0] == "keyword__0"
        assert sparse and sparse[0] == "keyword__0"
        assert hybrid and hybrid[0].chunk_id == "keyword__0"
        assert engine.last_search_debug["sparse_diagnostics"]["status"] == "ok"
    finally:
        engine.close()
        database.close()
