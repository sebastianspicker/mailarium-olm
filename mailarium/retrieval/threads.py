"""Load one conversation's messages from the text collection in date order."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from mailarium.model.rfc2822 import normalize_date

from .models import SearchResult
from .result_filters import _attachment_dedup_key, _email_dedup_key


def _parsed_thread_date(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = normalize_date(raw) or raw
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def thread_results(collection: Any, conversation_id: str, top_k: int = 50) -> list[SearchResult]:
    """Retrieve one conversation's messages in date order, validating the requested limit."""
    if not conversation_id or not conversation_id.strip():
        return []
    if top_k <= 0:
        raise ValueError("top_k must be a positive integer.")

    conv_filter: dict[str, Any] = {"conversation_id": {"$eq": conversation_id.strip()}}
    return _ordered_thread_results(*_thread_rows(collection, conv_filter, top_k), top_k=top_k)


def thread_results_for_uids(collection: Any, uids: list[str], top_k: int = 50) -> list[SearchResult]:
    """Retrieve the given emails' messages in thread date order, validating the requested limit."""
    if not uids:
        return []
    if top_k <= 0:
        raise ValueError("top_k must be a positive integer.")
    uid_filter: dict[str, Any] = {"uid": {"$in": list(uids)}}
    return _ordered_thread_results(*_thread_rows(collection, uid_filter, top_k), top_k=top_k)


def _ordered_thread_results(
    all_ids: list[str], all_docs: list[str | None], all_metas: list[dict[str, Any]], *, top_k: int
) -> list[SearchResult]:
    """Deduplicate collection rows per email and order them by thread date."""
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


def _thread_rows(collection: Any, where: dict[str, Any], top_k: int) -> tuple[list[str], list[str | None], list[dict[str, Any]]]:
    """Fetch and normalize all collection rows matching one thread filter."""
    fetch_limit = max(top_k * 5, 500)
    all_ids: list[str] = []
    all_docs: list[str | None] = []
    all_metas: list[dict[str, Any]] = []
    offset = 0
    while True:
        raw = collection.get(where=cast(Any, where), include=["documents", "metadatas"], limit=fetch_limit, offset=offset)
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
