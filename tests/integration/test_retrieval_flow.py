"""Synthetic end-to-end checks for the local retrieval facade."""

from __future__ import annotations

from mailarium.archive import open_archive_database
from mailarium.retrieval.retriever import SearchEngine


class _SyntheticEmbedder:
    """Keep retrieval tests independent of downloaded embedding models."""

    def __init__(self) -> None:
        self.queries: list[list[str]] = []

    def encode_dense(self, queries: list[str]) -> list[list[float]]:
        self.queries.append(queries)
        return [[1.0, 0.0] for _query in queries]


def test_filtered_retrieval_uses_canonical_vectors_and_deduplicates_email_chunks(monkeypatch, tmp_path) -> None:
    """One synthetic query exercises vector lookup, metadata filtering, and email-level deduplication."""
    runtime_home = tmp_path / "runtime"
    monkeypatch.setenv("MAILARIUM_RUNTIME_HOME", str(runtime_home))
    monkeypatch.setenv("RERANK_ENABLED", "false")
    monkeypatch.setenv("HYBRID_ENABLED", "false")
    database = open_archive_database(str(runtime_home / "archive.db"))
    engine = SearchEngine(
        vector_index_path=str(runtime_home / "vectors"),
        sqlite_path=str(runtime_home / "archive.db"),
        sparse_enabled=False,
        image_search_enabled=False,
        database=database,
    )
    embedder = _SyntheticEmbedder()
    engine._embedder = embedder
    engine.collection.add(
        ids=["mail-1__chunk_0", "mail-1__chunk_1", "mail-2__chunk_0"],
        embeddings=[[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]],
        documents=["first matching fragment", "second matching fragment", "unrelated fragment"],
        metadatas=[
            {"uid": "mail-1", "sender_email": "analyst@example.test", "folder": "Inbox", "date": "2026-08-20"},
            {"uid": "mail-1", "sender_email": "analyst@example.test", "folder": "Inbox", "date": "2026-08-20"},
            {"uid": "mail-2", "sender_email": "other@example.test", "folder": "Archive", "date": "2026-08-21"},
        ],
    )

    try:
        results = engine.search_filtered("handoff timeline", top_k=2, sender="analyst", folder="inbox")

        assert [result.chunk_id for result in results] == ["mail-1__chunk_0"]
        assert results[0].metadata["uid"] == "mail-1"
        assert embedder.queries == [["handoff timeline"]]
    finally:
        engine.close()
        database.close()
