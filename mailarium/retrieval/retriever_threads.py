"""Thread-oriented retrieval helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from mailarium.model.rfc2822 import _normalize_date

from .result_filters import _attachment_dedup_key, _email_dedup_key

if TYPE_CHECKING:
    from .retriever import SearchEngine, SearchResult


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


def search_by_thread_impl(retriever: SearchEngine, conversation_id: str, top_k: int = 50) -> list[SearchResult]:
    """Retrieve one conversation's messages in date order, validating the requested limit."""
    from .retriever import SearchResult

    if not conversation_id or not conversation_id.strip():
        return []
    if top_k <= 0:
        raise ValueError("top_k must be a positive integer.")

    all_ids, all_docs, all_metas = _thread_rows(retriever, conversation_id.strip(), top_k)
    results = [
        SearchResult(chunk_id=doc_id, text=all_docs[index] or "", metadata=all_metas[index] or {}, distance=0.0)
        for index, doc_id in enumerate(all_ids)
    ]

    deduped = _deduplicate_thread_emails(results)
    deduped.sort(
        key=lambda result: (
            _parsed_thread_date(result.metadata.get("date")) is None,
            _parsed_thread_date(result.metadata.get("date")) or datetime.max,
            str(result.metadata.get("date", "")),
            str(result.metadata.get("uid", "")),
        )
    )
    return deduped[:top_k]


def _deduplicate_thread_emails(results: list[SearchResult]) -> list[SearchResult]:
    positions: dict[str, int] = {}
    deduped: list[SearchResult] = []
    for result in results:
        key = _email_dedup_key(result.metadata)
        if key is None:
            deduped.append(result)
            continue
        position = positions.get(key)
        if position is None:
            positions[key] = len(deduped)
            deduped.append(result)
            continue
        selected = deduped[position]
        if _attachment_dedup_key(selected.metadata) and not _attachment_dedup_key(result.metadata):
            deduped[position] = result
    return deduped


def _thread_rows(
    retriever: SearchEngine, conversation_id: str, top_k: int
) -> tuple[list[str], list[str | None], list[dict[str, Any]]]:
    """Fetch and normalize all collection rows for one conversation identifier."""
    conv_filter: dict[str, dict[str, str]] = {"conversation_id": {"$eq": conversation_id}}
    fetch_limit = max(top_k * 5, 500)
    all_ids: list[str] = []
    all_docs: list[str | None] = []
    all_metas: list[dict[str, Any]] = []
    offset = 0
    while True:
        raw = retriever.collection.get(
            where=cast(Any, conv_filter), include=["documents", "metadatas"], limit=fetch_limit, offset=offset
        )
        batch_ids = raw.get("ids", []) if raw else []
        if not batch_ids:
            return all_ids, all_docs, all_metas
        all_ids.extend(batch_ids)
        all_docs.extend(_thread_documents(raw.get("documents"), len(batch_ids)))
        all_metas.extend(_thread_metadatas(raw.get("metadatas"), len(batch_ids)))
        if len(batch_ids) < fetch_limit:
            return all_ids, all_docs, all_metas
        offset += fetch_limit


def _thread_documents(value: Any, count: int) -> list[str | None]:
    """Normalize optional collection documents without altering their order."""
    if not isinstance(value, list):
        return [None] * count
    return [document if isinstance(document, str) else None for document in value]


def _thread_metadatas(value: Any, count: int) -> list[dict[str, Any]]:
    """Normalize optional collection metadata without altering row alignment."""
    raw_metas = value if isinstance(value, list) else [{}] * count
    return [dict(meta) if isinstance(meta, dict) else {} for meta in raw_metas]
