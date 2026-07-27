"""Query-lane derivation and segment retrieval helpers."""

from __future__ import annotations

from typing import Any

from ..mcp_models import EmailAnswerContextInput


def _text(value: Any) -> str:
    return str(value) if value else ""


def _segment_result(row: dict[str, Any], lane_id: str, lane_query: str) -> Any:
    """Convert a database message segment into a ranked SearchResult with segment provenance."""
    from ..retriever_models import SearchResult

    ordinal = int(row.get("ordinal") or 0)
    return SearchResult(
        chunk_id=f"{row['uid']}__segment_{ordinal}",
        text=_text(row.get("segment_text")),
        metadata={
            "uid": _text(row.get("uid")),
            "subject": _text(row.get("subject")),
            "sender_email": _text(row.get("sender_email")),
            "sender_name": _text(row.get("sender_name")),
            "date": _text(row.get("date")),
            "conversation_id": _text(row.get("conversation_id")),
            "folder": _text(row.get("folder")),
            "has_attachments": bool(row.get("has_attachments") or row.get("attachment_count")),
            "detected_language": _text(row.get("detected_language")),
            "detected_language_confidence": _text(row.get("detected_language_confidence")),
            "segment_type": _text(row.get("segment_type")),
            "segment_ordinal": ordinal,
            "source_surface": _text(row.get("source_surface")),
            "body_render_source": f"message_segments:{_text(row.get('segment_type'))}",
            "score_kind": "segment_sql",
            "score_calibration": "synthetic",
            "result_key": f"segment:{row['uid']}:{ordinal}",
            "matched_query_lanes": [lane_id],
            "matched_query_queries": [lane_query],
        },
        distance=max(0.0, 1.0 - float(row.get("score") or 0.0)),
    )


def _segment_rows(retriever: Any, lane_query: str, limit: int) -> list[dict[str, Any]]:
    """Search message segments when the database supports it and fail closed on adapter errors."""
    db = getattr(retriever, "email_db", None)
    if db is None or not hasattr(db, "search_message_segments"):
        return []
    try:
        return db.search_message_segments(lane_query, limit=limit)
    except Exception:  # pylint: disable=broad-exception-caught
        return []


def _segment_search_results(
    *,
    retriever: Any,
    lane_query: str,
    lane_id: str,
    limit: int,
    scan_id: str | None = None,
) -> tuple[list[Any], dict[str, Any]]:
    """Search for message segments matching a lane query."""
    results = [_segment_result(row, lane_id, lane_query) for row in _segment_rows(retriever, lane_query, limit)]
    scan_meta: dict[str, Any] | None = None
    if scan_id and results:
        from ..scan_session import filter_seen

        results, scan_meta = filter_seen(scan_id, results)
    return results, {
        "segment_result_count": len(results),
        "segment_excluded_count": int((scan_meta or {}).get("excluded_count") or 0),
    }


def _append_lane(lanes: list[str], lane: str) -> None:
    """Append a whitespace-normalized, case-insensitively unique query lane capped at 500 characters."""
    compact = " ".join(_text(lane).split()).strip()
    if compact and all(existing.casefold() != compact.casefold() for existing in lanes):
        lanes.append(compact[:500])


def _expanded_query_lanes(retriever: Any, query: str, requested: bool, *, scope: str | None = None) -> list[str]:
    """Request at most four scoped expansion lanes and discard empty or malformed results."""
    expand = getattr(retriever, "_expand_query_lanes", None)
    if not requested or not callable(expand):
        return []
    expanded = expand(query, max_lanes=4, scope=scope)
    values = expanded if isinstance(expanded, list) else []
    return [" ".join(_text(item).split()).strip() for item in values if _text(item).strip()]


def _derive_query_lanes(*, retriever: Any, params: EmailAnswerContextInput, search_kwargs: dict[str, Any]) -> list[str]:
    """Derive deterministic lanes from explicit or corpus-expanded queries."""
    explicit = [" ".join(_text(item).split()).strip() for item in params.query_lanes if _text(item).strip()]
    if explicit:
        return explicit[:8]
    query = _text(search_kwargs.get("query")).strip()
    if not query:
        return []
    expanded = _expanded_query_lanes(
        retriever,
        query,
        bool(search_kwargs.get("expand_query")),
        scope=_text(search_kwargs.get("scope")) or None,
    )
    if not expanded:
        return [query]
    lanes: list[str] = []
    for lane in expanded:
        _append_lane(lanes, lane)
    return lanes[:8]


__all__ = ["_derive_query_lanes", "_segment_search_results"]
