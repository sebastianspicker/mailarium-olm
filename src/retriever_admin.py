"""Administrative and metadata helpers for the retriever facade."""

from __future__ import annotations

import logging
from importlib import import_module
from typing import Any

from .storage import iter_collection_metadatas

logger = logging.getLogger(__name__)


def list_senders_impl(retriever: Any, limit: int = 50) -> list[dict[str, Any]]:
    """List unique senders sorted by message count."""
    if limit <= 0:
        raise ValueError("limit must be a positive integer.")
    if limit > 10_000:
        raise ValueError("limit must be <= 10000.")

    if retriever.email_db:
        try:
            rows = retriever.email_db.top_senders(limit=limit)
            if rows:
                return [{"name": r["sender_name"], "email": r["sender_email"], "count": r["message_count"]} for r in rows]
        except Exception:
            logger.debug("SQLite list_senders failed, falling back to ChromaDB", exc_info=True)

    sender_counts: dict[str, dict[str, Any]] = {}
    sender_email_keys: dict[str, set[str]] = {}
    sender_unknown_uid_counts: dict[str, int] = {}
    for meta in iter_collection_metadatas(retriever.collection):
        email = (meta.get("sender_email") or "unknown").strip()
        name = (meta.get("sender_name") or "").strip()
        key = email.lower()
        sender_counts.setdefault(key, {"name": name, "email": email, "count": 0})

        email_key = retriever._email_dedup_key(meta)
        if email_key:
            sender_email_keys.setdefault(key, set()).add(email_key)
        else:
            sender_unknown_uid_counts[key] = sender_unknown_uid_counts.get(key, 0) + 1

    if not sender_counts:
        return []

    for key, entry in sender_counts.items():
        unique_uid_count = len(sender_email_keys.get(key, set()))
        unknown_uid_count = sender_unknown_uid_counts.get(key, 0)
        entry["count"] = unique_uid_count + unknown_uid_count

    return sorted(sender_counts.values(), key=lambda item: item["count"], reverse=True)[:limit]


def stats_impl(retriever: Any) -> dict[str, Any]:
    """Get summary statistics about the indexed archive."""
    total_chunks = retriever.collection.count()

    if retriever.email_db:
        try:
            email_count = retriever.email_db.email_count()
            if email_count > 0:
                min_d, max_d = retriever.email_db.date_range()
                return {
                    "total_chunks": total_chunks,
                    "total_emails": email_count,
                    "unique_senders": retriever.email_db.unique_sender_count(),
                    "date_range": {"earliest": min_d[:10] if min_d else None, "latest": max_d[:10] if max_d else None},
                    "folders": retriever.email_db.folder_counts(),
                }
        except Exception:
            logger.debug("SQLite stats failed, falling back to ChromaDB", exc_info=True)

    if total_chunks == 0:
        return {"total_chunks": 0, "total_emails": 0, "unique_senders": 0, "date_range": {}, "folders": {}}

    unique_email_keys: set[str] = set()
    unknown_email_rows = 0
    unique_senders: set[str] = set()
    earliest: str | None = None
    latest: str | None = None
    folder_email_keys: dict[str, set[str]] = {}
    folder_unknown_rows: dict[str, int] = {}

    for meta in iter_collection_metadatas(retriever.collection):
        email_key = retriever._email_dedup_key(meta)
        folder = str(meta.get("folder") or "Unknown").strip() or "Unknown"
        if email_key:
            unique_email_keys.add(email_key)
            folder_email_keys.setdefault(folder, set()).add(email_key)
        else:
            unknown_email_rows += 1
            folder_unknown_rows[folder] = folder_unknown_rows.get(folder, 0) + 1

        sender_email = str(meta.get("sender_email", "")).strip().lower()
        if sender_email:
            unique_senders.add(sender_email)

        raw_date = meta.get("date")
        if raw_date:
            date_prefix = str(raw_date)[:10]
            if earliest is None or date_prefix < earliest:
                earliest = date_prefix
            if latest is None or date_prefix > latest:
                latest = date_prefix

    folders: dict[str, int] = {}
    for folder, keys in folder_email_keys.items():
        folders[folder] = len(keys)
    for folder, count in folder_unknown_rows.items():
        folders[folder] = folders.get(folder, 0) + count

    return {
        "total_chunks": total_chunks,
        "total_emails": len(unique_email_keys) + unknown_email_rows,
        "unique_senders": len(unique_senders),
        "date_range": {"earliest": earliest, "latest": latest},
        "folders": dict(sorted(folders.items(), key=lambda item: item[1], reverse=True)),
    }


def resolve_semantic_uids_impl(
    retriever: Any,
    topic_id: int | None = None,
    cluster_id: int | None = None,
) -> set[str]:
    """Pre-fetch email UIDs matching semantic filters from SQLite."""
    db = retriever.email_db
    if db is None:
        return set()

    uid_sets: list[set[str]] = []
    if topic_id is not None:
        try:
            rows = db.emails_by_topic(topic_id, limit=10_000)
            uid_sets.append({r["uid"] for r in rows})
        except Exception:
            logger.debug("topic_id filter failed", exc_info=True)
            uid_sets.append(set())

    if cluster_id is not None:
        try:
            rows = db.emails_in_cluster(cluster_id, limit=10_000)
            uid_sets.append({r["uid"] for r in rows})
        except Exception:
            logger.debug("cluster_id filter failed", exc_info=True)
            uid_sets.append(set())

    if not uid_sets:
        return set()

    result = uid_sets[0]
    for item in uid_sets[1:]:
        result &= item
    return result


def expand_query_impl(retriever: Any, query: str) -> str:
    """Expand query with semantically related terms."""
    try:
        query_expander_module = import_module("src.query_expander")

        QueryExpander = query_expander_module.QueryExpander
        legal_support_query_profile = getattr(query_expander_module, "legal_support_query_profile", None)

        db = retriever.email_db
        if db is None:
            return query

        if retriever._query_expander is None:
            keywords = db.top_keywords(limit=400)
            if not keywords:
                return query
            vocab = [kw["keyword"] for kw in keywords]
            retriever._query_expander = QueryExpander(model=retriever.model, vocabulary=vocab)

        if callable(legal_support_query_profile):
            profile = legal_support_query_profile(query)
        else:
            profile = {"is_legal_support": False, "intents": [], "suggested_terms": []}
        expanded = retriever._query_expander.expand(query, n_terms=5 if profile["is_legal_support"] else 3)
        retriever._last_query_expansion = {
            "original_query": query,
            "expanded_query": expanded,
            "used_query_expansion": expanded != query,
            "legal_support_profile": profile,
        }
        return expanded
    except Exception:
        logger.debug("Query expansion failed", exc_info=True)
        return query


def expand_query_lanes_impl(retriever: Any, query: str, *, max_lanes: int = 4) -> list[str]:
    """Expand one query into multiple retrieval lanes."""
    try:
        query_expander_module = import_module("src.query_expander")

        QueryExpander = query_expander_module.QueryExpander
        legal_support_query_profile = getattr(query_expander_module, "legal_support_query_profile", None)

        db = retriever.email_db
        if db is None:
            return [query]

        if retriever._query_expander is None:
            keywords = db.top_keywords(limit=400)
            if not keywords:
                return [query]
            vocab = [kw["keyword"] for kw in keywords]
            retriever._query_expander = QueryExpander(model=retriever.model, vocabulary=vocab)

        if callable(legal_support_query_profile):
            profile = legal_support_query_profile(query)
        else:
            profile = {"is_legal_support": False, "intents": [], "suggested_terms": []}
        lanes = retriever._query_expander.expand_lanes(
            query,
            n_terms=5 if profile["is_legal_support"] else 3,
            max_lanes=max_lanes,
        )
        retriever._last_query_expansion = {
            "original_query": query,
            "query_lanes": lanes,
            "used_query_expansion": len(lanes) > 1,
            "legal_support_profile": profile,
        }
        return lanes or [query]
    except Exception:
        logger.debug("Query lane expansion failed", exc_info=True)
        return [query]
