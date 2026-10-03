"""Query-lane derivation, segment retrieval, and expansion-term attribution."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from mailarium.model.data_shapes import as_dict

from .contracts import AnswerContextRequest
from .text import _text

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase


def _segment_result(row: dict[str, Any], lane_id: str, lane_query: str) -> Any:
    """Convert a database message segment into a ranked SearchResult with segment provenance."""
    from mailarium.retrieval.models import SearchResult

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
    db: ArchiveDatabase | None = getattr(retriever, "email_db", None)
    if db is None:
        return []
    try:
        return db.queries.search_message_segments(lane_query, limit=limit)
    except Exception:
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
        from mailarium.retrieval.scan_session import filter_seen

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
    if not requested:
        return []
    try:
        expand = retriever.expand_query_lanes
    except AttributeError:
        return []
    if not callable(expand):
        return []
    expanded = expand(query, max_lanes=4, scope=scope)
    values = expanded if isinstance(expanded, list) else []
    return [" ".join(_text(item).split()).strip() for item in values if _text(item).strip()]


def _derive_query_lanes(*, retriever: Any, params: AnswerContextRequest, search_kwargs: dict[str, Any]) -> list[str]:
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


def _term_tokens(text: str) -> list[str]:
    """Extract term tokens from text.

    Tokenizes text into word tokens using a regex pattern that matches
    word characters and hyphens. Converts to lowercase for case-insensitive
    matching.

    Args:
        text: The input text to tokenize.

    Returns:
        A list of non-empty term tokens in lowercase.
    """
    return [token for token in re.findall(r"[\w-]+", str(text or "").casefold()) if token]


def _lane_expansion_terms(
    *,
    base_query: str,
    lane_query: str,
    executed_query: str,
    query_expansion_suffix: str,
) -> list[str]:
    """Extract expansion terms from query variations.

    Identifies terms that were added during query expansion by comparing
    the base query against lane query, executed query, and expansion suffix.
    Returns unique terms that appear in expanded queries but not in the base.

    Args:
        base_query: The original base query string.
        lane_query: The lane-specific query string.
        executed_query: The query that was actually executed.
        query_expansion_suffix: Suffix added during query expansion.

    Returns:
        A list of unique expansion terms not present in the base query.
    """
    terms: list[str] = []
    seen: set[str] = set()

    def _add(tokens: list[str]) -> None:
        for token in tokens:
            compact = token.strip()
            if not compact or compact in seen:
                continue
            seen.add(compact)
            terms.append(compact)

    base_tokens = set(_term_tokens(base_query))
    lane_extra_tokens = [token for token in _term_tokens(lane_query) if token not in base_tokens]
    executed_extra_tokens = [token for token in _term_tokens(executed_query) if token not in base_tokens]

    _add(_term_tokens(query_expansion_suffix))
    _add(lane_extra_tokens)
    _add(executed_extra_tokens)
    return terms


def _result_search_surface(result: Any) -> str:
    """Create a searchable surface string from a result.

    Combines multiple fields from a result (text, subject, segment type,
    attachment filename, sender info) into a single casefolded string
    for use in term matching and search operations.

    Args:
        result: The search result object.

    Returns:
        A casefolded string concatenating all searchable fields.
    """
    metadata = as_dict(result.metadata)
    return " ".join(
        part
        for part in (
            str(getattr(result, "text", "") or ""),
            str(metadata.get("subject") or ""),
            str(metadata.get("segment_type") or ""),
            str(metadata.get("attachment_filename") or metadata.get("filename") or ""),
            str(metadata.get("sender_name") or ""),
            str(metadata.get("sender_email") or ""),
        )
        if part
    ).casefold()


def _lane_recovered_expansion_terms(
    *,
    expansion_terms: list[str],
    new_keys: list[str],
    result_lookup: dict[str, Any],
) -> tuple[list[str], int]:
    """Identify which expansion terms were recovered in new results.

    Checks each new result key against the expansion terms to see which
    terms appear in the result's searchable surface. Tracks both the
    recovered terms and how many keys contained at least one expansion term.

    Args:
        expansion_terms: List of terms to look for in results.
        new_keys: List of result keys to check.
        result_lookup: Dictionary mapping result keys to result objects.

    Returns:
        A tuple of (recovered_terms, recovered_key_count) where recovered_terms
        is the list of unique expansion terms found, and recovered_key_count
        is the number of keys that matched at least one expansion term.
    """
    if not expansion_terms or not new_keys:
        return [], 0
    recovered: list[str] = []
    seen: set[str] = set()
    recovered_key_count = 0
    for key in new_keys:
        result = result_lookup.get(key)
        if result is None:
            continue
        haystack = _result_search_surface(result)
        matched_any = False
        for term in expansion_terms:
            if term and term in haystack:
                matched_any = True
                if term not in seen:
                    seen.add(term)
                    recovered.append(term)
        if matched_any:
            recovered_key_count += 1
    return recovered, recovered_key_count


__all__ = ["_derive_query_lanes", "_segment_search_results"]
