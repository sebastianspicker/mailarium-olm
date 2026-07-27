"""Bare retriever and SearchResult factories for focused retriever behavior tests."""

from mailarium.retriever import EmailRetriever, SearchResult

# ── Helpers ────────────────────────────────────────────────────────


def _make_result(chunk_id="c1", text="body text", uid="u1", date="2024-01-01", distance=0.1, **extra_meta):
    """Build deterministic result data without external services."""
    meta = {"uid": uid, "date": date, **extra_meta}
    return SearchResult(chunk_id=chunk_id, text=text, metadata=meta, distance=distance)


def _bare_retriever(**attrs):
    """Create a retriever via __new__ with optional attribute overrides."""
    r = EmailRetriever.__new__(EmailRetriever)
    # Set common defaults that many methods expect
    r._email_db = None
    r._email_db_checked = True
    r.settings = None
    for k, v in attrs.items():
        setattr(r, k, v)
    return r


def _thread_collection(*, ids, documents, metadatas):
    """Build a collection mock returning one deterministic thread result page."""
    from unittest.mock import MagicMock

    collection = MagicMock()
    collection.get.return_value = {"ids": ids, "documents": documents, "metadatas": metadatas}
    return collection


def _paged_metadata_collection(*pages):
    """Build a vector collection whose metadata pages are addressed by offset."""
    offsets = []
    current_offset = 0
    for page in pages:
        offsets.append((current_offset, page))
        current_offset += len(page)

    class _Collection:
        def count(self):
            return current_offset

        def get(self, include, limit, offset):
            for page_offset, page in offsets:
                if offset == page_offset:
                    return {"metadatas": page}
            return {"metadatas": []}

    return _Collection()


def _configured_sparse_retriever(vector, *, index_revision="rev-1", sparse_doc_count=100):
    """Create a retriever and sparse-index doubles for sparse-result behavior tests."""
    from unittest.mock import MagicMock

    retriever = _bare_retriever()
    embedder = MagicMock()
    embedder.has_sparse = True
    embedder.encode_sparse_query.return_value = [vector]
    retriever._embedder = embedder
    retriever._email_db = MagicMock()
    retriever._email_db_checked = True
    retriever.collection = MagicMock()
    retriever.collection.count.return_value = 100
    retriever.collection.metadata = {"index_revision": index_revision}

    sparse_index = MagicMock()
    sparse_index.is_built = True
    sparse_index.doc_count = sparse_doc_count
    retriever._sparse_index = sparse_index
    return retriever, sparse_index, embedder
