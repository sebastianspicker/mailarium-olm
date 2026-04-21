"""Thread-oriented retrieval helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from .result_filters import _deduplicate_by_email
from .rfc2822 import _normalize_date

if TYPE_CHECKING:
    from .retriever import EmailRetriever, SearchResult


def _parsed_thread_date(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = _normalize_date(raw) or raw
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def search_by_thread_impl(retriever: EmailRetriever, conversation_id: str, top_k: int = 50) -> list[SearchResult]:
    """Retrieve all emails in a conversation thread, sorted by date."""
    from .retriever import SearchResult

    if not conversation_id or not conversation_id.strip():
        return []
    if top_k <= 0:
        raise ValueError("top_k must be a positive integer.")

    conv_filter: dict[str, dict[str, str]] = {"conversation_id": {"$eq": conversation_id.strip()}}
    fetch_limit = max(top_k * 5, 500)
    all_ids: list[str] = []
    all_docs: list[str | None] = []
    all_metas: list[dict[str, Any]] = []
    offset = 0

    while True:
        raw = retriever.collection.get(
            where=cast(Any, conv_filter),
            include=["documents", "metadatas"],
            limit=fetch_limit,
            offset=offset,
        )
        batch_ids = raw.get("ids", []) if raw else []
        if not batch_ids:
            break
        all_ids.extend(batch_ids)
        raw_docs: list[str | None]
        docs_value = raw.get("documents")
        if isinstance(docs_value, list):
            raw_docs = [doc if isinstance(doc, str) else None for doc in docs_value]
        else:
            raw_docs = [None] * len(batch_ids)
        normalized_docs = [doc if isinstance(doc, str) else None for doc in raw_docs]
        all_docs.extend(normalized_docs)
        raw_metas = raw.get("metadatas") or [{}] * len(batch_ids)
        normalized_metas = [dict(meta) if isinstance(meta, dict) else {} for meta in raw_metas]
        all_metas.extend(normalized_metas)
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
    deduped.sort(
        key=lambda result: (
            _parsed_thread_date(result.metadata.get("date")) is None,
            _parsed_thread_date(result.metadata.get("date")) or datetime.max,
            str(result.metadata.get("date", "")),
            str(result.metadata.get("uid", "")),
        )
    )
    return deduped[:top_k]
