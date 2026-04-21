"""Thread-oriented retrieval helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .result_filters import _deduplicate_by_email

if TYPE_CHECKING:
    from .retriever import EmailRetriever, SearchResult


def search_by_thread_impl(retriever: EmailRetriever, conversation_id: str, top_k: int = 50) -> list[SearchResult]:
    """Retrieve all emails in a conversation thread, sorted by date."""
    from .retriever import SearchResult

    if not conversation_id or not conversation_id.strip():
        return []
    if top_k <= 0:
        raise ValueError("top_k must be a positive integer.")

    conv_filter = {"conversation_id": {"$eq": conversation_id.strip()}}
    fetch_limit = max(top_k * 5, 500)
    all_ids: list[str] = []
    all_docs: list[str | None] = []
    all_metas: list[dict] = []
    offset = 0

    while True:
        raw = retriever.collection.get(
            where=conv_filter,
            include=["documents", "metadatas"],
            limit=fetch_limit,
            offset=offset,
        )
        batch_ids = raw.get("ids", []) if raw else []
        if not batch_ids:
            break
        all_ids.extend(batch_ids)
        all_docs.extend(raw.get("documents") or [None] * len(batch_ids))
        all_metas.extend(raw.get("metadatas") or [{}] * len(batch_ids))
        if len(batch_ids) < fetch_limit:
            break
        offset += fetch_limit

    results: list[SearchResult] = []
    for index, doc_id in enumerate(all_ids):
        results.append(
            SearchResult(
                chunk_id=doc_id,
                text=all_docs[index] or "",
                metadata=all_metas[index] or {},
                distance=0.0,
            )
        )

    deduped = _deduplicate_by_email(results)
    deduped.sort(key=lambda result: str(result.metadata.get("date", "")))
    return deduped[:top_k]
