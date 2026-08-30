"""Administrative and metadata helpers for the retriever facade."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from mailarium.archive.storage import iter_vector_metadatas

logger = logging.getLogger(__name__)


def list_senders_impl(retriever: Any, limit: int = 50) -> list[dict[str, Any]]:
    """List unique senders sorted by message count."""
    if limit <= 0:
        raise ValueError("limit must be a positive integer.")
    if limit > 10_000:
        raise ValueError("limit must be <= 10000.")

    sqlite_rows = _sqlite_senders(retriever, limit)
    if sqlite_rows:
        return sqlite_rows
    sender_counts, sender_email_keys, sender_unknown_uid_counts = _collection_sender_counts(retriever)
    return _finalize_sender_counts(sender_counts, sender_email_keys, sender_unknown_uid_counts, limit)


def _sqlite_senders(retriever: Any, limit: int) -> list[dict[str, Any]]:
    """Use the exact SQLite summary when it is populated and available."""
    if not retriever.email_db:
        return []
    try:
        rows = retriever.email_db.top_senders(limit=limit)
        return [{"name": row["sender_name"], "email": row["sender_email"], "count": row["message_count"]} for row in rows]
    except Exception:
        logger.debug("SQLite list_senders failed, falling back to vector metadata", exc_info=True)
        return []


def _collection_sender_counts(retriever: Any) -> tuple[dict[str, dict[str, Any]], dict[str, set[str]], dict[str, int]]:
    """Accumulate vector metadata while retaining UID-aware deduplication."""
    sender_counts: dict[str, dict[str, Any]] = {}
    sender_email_keys: dict[str, set[str]] = {}
    sender_unknown_uid_counts: dict[str, int] = {}
    for meta in iter_vector_metadatas(retriever.collection):
        email = (meta.get("sender_email") or "unknown").strip()
        name = (meta.get("sender_name") or "").strip()
        key = email.lower()
        sender_counts.setdefault(key, {"name": name, "email": email, "count": 0})

        email_key = retriever._email_dedup_key(meta)
        if email_key:
            sender_email_keys.setdefault(key, set()).add(email_key)
        else:
            sender_unknown_uid_counts[key] = sender_unknown_uid_counts.get(key, 0) + 1
    return sender_counts, sender_email_keys, sender_unknown_uid_counts


def _finalize_sender_counts(
    sender_counts: dict[str, dict[str, Any]], sender_email_keys: dict[str, set[str]], unknown_counts: dict[str, int], limit: int
) -> list[dict[str, Any]]:
    """Set accurate deduplicated counts and apply the caller's limit."""
    if not sender_counts:
        return []
    for key, entry in sender_counts.items():
        entry["count"] = len(sender_email_keys.get(key, set())) + unknown_counts.get(key, 0)
    return sorted(sender_counts.values(), key=lambda item: item["count"], reverse=True)[:limit]


def stats_impl(retriever: Any) -> dict[str, Any]:
    """Get summary statistics about the indexed archive."""
    total_chunks = retriever.collection.count()
    sqlite_stats, warning = _sqlite_stats(retriever, total_chunks)
    if sqlite_stats:
        return sqlite_stats
    if total_chunks == 0:
        return _empty_stats(warning)
    return _vector_metadata_stats(retriever, total_chunks, warning)


def _sqlite_stats(retriever: Any, total_chunks: int) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    if not retriever.email_db:
        return None, None
    try:
        email_count = retriever.email_db.email_count()
        if email_count <= 0:
            return None, None
        min_date, max_date = retriever.email_db.date_range()
        return {
            "total_chunks": total_chunks,
            "total_emails": email_count,
            "unique_senders": retriever.email_db.unique_sender_count(),
            "date_range": {"earliest": min_date[:10] if min_date else None, "latest": max_date[:10] if max_date else None},
            "folders": retriever.email_db.folder_counts(),
            "metadata_source": "sqlite",
        }, None
    except Exception as exc:
        logger.debug("SQLite stats failed, falling back to vector metadata", exc_info=True)
        return None, {
            "metadata_warning": "sqlite_stats_failed_vector_collection_fallback",
            "metadata_error_type": type(exc).__name__,
            "metadata_error": str(exc),
        }


def _empty_stats(warning: dict[str, str] | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "total_chunks": 0,
        "total_emails": 0,
        "unique_senders": 0,
        "date_range": {},
        "folders": {},
        "metadata_source": "vector_collection_fallback",
    }
    if warning:
        payload.update(warning)
    return payload


def _vector_metadata_stats(retriever: Any, total_chunks: int, warning: dict[str, str] | None) -> dict[str, Any]:
    state = _CollectionStats()
    for meta in iter_vector_metadatas(retriever.collection):
        _record_collection_metadata(state, retriever, meta)
        _record_collection_sender(state, meta)
        _record_collection_date(state, meta)
    folders = _collection_folder_counts(state)

    payload = {
        "total_chunks": total_chunks,
        "total_emails": len(state.email_keys) + state.unknown_email_rows,
        "unique_senders": len(state.senders),
        "date_range": {"earliest": state.earliest, "latest": state.latest},
        "folders": dict(sorted(folders.items(), key=lambda item: item[1], reverse=True)),
        "metadata_source": "vector_collection_fallback",
    }
    if warning:
        payload.update(warning)
    return payload


@dataclass
class _CollectionStats:
    """Accumulates vector-metadata totals for the SQLite fallback response."""

    email_keys: set[str] = field(default_factory=set)
    unknown_email_rows: int = 0
    senders: set[str] = field(default_factory=set)
    earliest: str | None = None
    latest: str | None = None
    folder_email_keys: dict[str, set[str]] = field(default_factory=dict)
    folder_unknown_rows: dict[str, int] = field(default_factory=dict)


def _record_collection_metadata(state: _CollectionStats, retriever: Any, metadata: dict[str, Any]) -> None:
    folder = str(metadata.get("folder") or "Unknown").strip() or "Unknown"
    email_key = retriever._email_dedup_key(metadata)
    if email_key:
        state.email_keys.add(email_key)
        state.folder_email_keys.setdefault(folder, set()).add(email_key)
        return
    state.unknown_email_rows += 1
    state.folder_unknown_rows[folder] = state.folder_unknown_rows.get(folder, 0) + 1


def _record_collection_sender(state: _CollectionStats, metadata: dict[str, Any]) -> None:
    sender = str(metadata.get("sender_email", "")).strip().lower()
    if sender:
        state.senders.add(sender)


def _record_collection_date(state: _CollectionStats, metadata: dict[str, Any]) -> None:
    value = metadata.get("date")
    if not value:
        return
    date_prefix = str(value)[:10]
    state.earliest = date_prefix if state.earliest is None or date_prefix < state.earliest else state.earliest
    state.latest = date_prefix if state.latest is None or date_prefix > state.latest else state.latest


def _collection_folder_counts(state: _CollectionStats) -> dict[str, int]:
    """Combine known-UID and unknown-row folder counts deterministically."""
    folders = {folder: len(keys) for folder, keys in state.folder_email_keys.items()}
    for folder, count in state.folder_unknown_rows.items():
        folders[folder] = folders.get(folder, 0) + count
    return folders


def _store_semantic_filter_errors(retriever: Any, errors: list[dict[str, Any]]) -> None:
    """Store semantic-filter diagnostics through the thread-local retriever seam."""
    setter = getattr(retriever, "_set_last_semantic_filter_errors", None)
    if callable(setter):
        setter(errors)
    else:
        retriever._last_semantic_filter_errors = [dict(error) for error in errors]


def _store_query_expansion(retriever: Any, payload: dict[str, Any]) -> None:
    """Store query-expansion diagnostics through the thread-local retriever seam."""
    setter = getattr(retriever, "_set_last_query_expansion", None)
    if callable(setter):
        setter(payload)
    else:
        retriever._last_query_expansion = dict(payload)


def resolve_semantic_uids_impl(
    retriever: Any,
    topic_id: int | None = None,
    cluster_id: int | None = None,
) -> set[str]:
    """Pre-fetch email UIDs matching semantic filters from SQLite."""
    errors: list[dict[str, Any]] = []
    _store_semantic_filter_errors(retriever, errors)
    db = retriever.email_db
    if db is None:
        return set()

    uid_sets: list[set[str]] = []
    if topic_id is not None:
        try:
            rows = db.emails_by_topic(topic_id, limit=10_000)
            uid_sets.append({r["uid"] for r in rows})
        except Exception as exc:
            logger.debug("topic_id filter failed", exc_info=True)
            errors.append(
                {
                    "filter": "topic_id",
                    "value": topic_id,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
            uid_sets.append(set())

    if cluster_id is not None:
        try:
            rows = db.emails_in_cluster(cluster_id, limit=10_000)
            uid_sets.append({r["uid"] for r in rows})
        except Exception as exc:
            logger.debug("cluster_id filter failed", exc_info=True)
            errors.append(
                {
                    "filter": "cluster_id",
                    "value": cluster_id,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
            uid_sets.append(set())

    _store_semantic_filter_errors(retriever, errors)
    if not uid_sets:
        return set()

    result = uid_sets[0]
    for item in uid_sets[1:]:
        result &= item
    return result


def expand_query_impl(retriever: Any, query: str, *, scope: str = "general") -> str:
    """Expand query with semantically related terms."""
    _store_query_expansion(
        retriever,
        {
            "original_query": query,
            "expanded_query": query,
            "used_query_expansion": False,
            "query_expansion_status": "unchanged",
            "scope": scope,
        },
    )
    try:
        from .query_planning import QueryExpander

        db = retriever.email_db
        if db is None:
            return query

        if retriever._query_expander is None:
            keywords = db.top_keywords(limit=400)
            if not keywords:
                return query
            vocab = [kw["keyword"] for kw in keywords]
            retriever._query_expander = QueryExpander(model=retriever.embedder, vocabulary=vocab)

        expanded = retriever._query_expander.expand(
            query,
            n_terms=3,
            scope=scope,
        )
        expansion_debug = {
            "original_query": query,
            "expanded_query": expanded,
            "used_query_expansion": expanded != query,
            "query_expansion_status": "expanded" if expanded != query else "unchanged",
            "scope": scope,
        }
        _store_query_expansion(retriever, expansion_debug)
        return expanded
    except Exception as exc:
        logger.debug("Query expansion failed", exc_info=True)
        _store_query_expansion(
            retriever,
            {
                "original_query": query,
                "expanded_query": query,
                "used_query_expansion": False,
                "query_expansion_status": "error",
                "query_expansion_error_type": type(exc).__name__,
                "query_expansion_error": str(exc),
            },
        )
        return query


def expand_query_lanes_impl(
    retriever: Any,
    query: str,
    *,
    max_lanes: int = 4,
    scope: str = "general",
) -> list[str]:
    """Expand one query into multiple retrieval lanes."""
    _store_query_expansion(
        retriever,
        {
            "original_query": query,
            "query_lanes": [query],
            "used_query_expansion": False,
            "scope": scope,
        },
    )
    try:
        from .query_planning import QueryExpander

        db = retriever.email_db
        if db is None:
            return [query]

        if retriever._query_expander is None:
            keywords = db.top_keywords(limit=400)
            if not keywords:
                return [query]
            vocab = [kw["keyword"] for kw in keywords]
            retriever._query_expander = QueryExpander(model=retriever.embedder, vocabulary=vocab)

        lanes = retriever._query_expander.expand_lanes(
            query,
            n_terms=3,
            max_lanes=max_lanes,
            scope=scope,
        )
        expansion_debug = {
            "original_query": query,
            "query_lanes": lanes,
            "used_query_expansion": len(lanes) > 1,
            "scope": scope,
        }
        _store_query_expansion(retriever, expansion_debug)
        return lanes or [query]
    except Exception:
        logger.debug("Query lane expansion failed", exc_info=True)
        return [query]
