"""Rejects invalid embedding batches and deduplicates repeated chunk identifiers before vector writes."""

import pytest

from mailarium.chunker import EmailChunk
from mailarium.embedder import EmailEmbedder
from mailarium.multi_vector_embedder import MultiVectorResult


class _FakeMultiVectorEmbedder:
    def __init__(self, **_kw):
        self.model_name = "fake-bge-m3"

    def encode_all(self, texts):
        dense = [[0.1, 0.2, 0.3] for _ in texts]
        return MultiVectorResult(dense=dense, sparse=None)

    def warmup(self):
        return None


@pytest.fixture(autouse=True)
def _stub_multi_vector_embedder(monkeypatch, tmp_path):
    import mailarium.embedder as embedder_mod

    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "email_metadata.db"))
    monkeypatch.setattr(embedder_mod, "MultiVectorEmbedder", _FakeMultiVectorEmbedder)


def test_add_chunks_rejects_non_positive_batch_size():
    embedder = EmailEmbedder.__new__(EmailEmbedder)

    with pytest.raises(ValueError):
        embedder.add_chunks([], batch_size=0)


def test_add_chunks_deduplicates_within_batch(tmp_path):
    """Duplicate chunk IDs in the same batch must not raise DuplicateIDError."""
    embedder = EmailEmbedder(vector_index_path=str(tmp_path / "vector-index"))

    dup_id = "aaaa__0"
    chunks = [
        EmailChunk(uid="aaaa", chunk_id=dup_id, text="Hello", metadata={"uid": "aaaa", "chunk_index": "0"}),
        EmailChunk(uid="aaaa", chunk_id=dup_id, text="World", metadata={"uid": "aaaa", "chunk_index": "0"}),
        EmailChunk(uid="bbbb", chunk_id="bbbb__0", text="Other", metadata={"uid": "bbbb", "chunk_index": "0"}),
    ]

    added = embedder.add_chunks(chunks, batch_size=100)

    # Only 2 unique chunk IDs, so only 2 should be stored
    assert added == 2
    assert embedder.count() == 2
