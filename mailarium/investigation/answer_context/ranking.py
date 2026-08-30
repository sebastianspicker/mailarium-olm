"""Query-lane retrieval, result ranking, and evidence-bank selection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from mailarium.model.data_shapes import as_dict, as_list
from mailarium.retrieval.scan_session import filter_seen

from .contracts import AnswerContextRequest


def _snippet(text: str, *, max_chars: int = 280) -> str:
    """Return a compact single-line text preview for retrieval diagnostics."""
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= max_chars else collapsed[: max_chars - 3].rstrip() + "..."


"""Query-lane derivation and segment retrieval helpers."""


def _segment_result(row: dict[str, Any], lane_id: str, lane_query: str) -> Any:
    """Convert a database message segment into a ranked SearchResult with segment provenance."""
    from mailarium.retrieval.retriever_models import SearchResult

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
    expand = getattr(retriever, "_expand_query_lanes", None)
    if not requested or not callable(expand):
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


__all__ = ["_derive_query_lanes", "_segment_search_results"]


"""Evidence ranking, diversification, and support-type selection for answer-context retrieval."""


def _text(value: Any, default: str = "") -> str:
    return str(value) if value else default


def _float(value: Any) -> float:
    return float(value) if value else 0.0


def _int(value: Any) -> int:
    return int(value) if value else 0


def _bank_entry(
    *,
    result: Any,
    key: str,
    matched_query_lanes: list[str],
    matched_query_queries: list[str],
) -> dict[str, Any]:
    """Create an evidence bank entry from a search result.

    Extracts relevant metadata and content from a search result to create a
    structured evidence bank entry suitable for downstream processing.

    Args:
        result: The search result object containing text and metadata.
        key: Unique identifier for this result in the evidence bank.
        matched_query_lanes: List of lane IDs that matched this result.
        matched_query_queries: List of query strings that matched this result.

    Returns:
        A dictionary containing the evidence bank entry with extracted fields
        including uid, chunk_id, score, subject, sender info, date, snippet,
        support type, and matched query information.
    """
    metadata = as_dict(result.metadata)
    text_preview = _snippet(_text(getattr(result, "text", "")))
    attachment_filename = _text(metadata.get("attachment_filename") or metadata.get("filename"))
    support_type = _support_type_for_result(result, matched_queries=matched_query_queries)
    return {
        "uid": _text(metadata.get("uid")),
        "chunk_id": _text(getattr(result, "chunk_id", "")),
        "score": _float(getattr(result, "score", 0.0)),
        "subject": _text(metadata.get("subject")),
        "sender_email": _text(metadata.get("sender_email")),
        "sender_name": _text(metadata.get("sender_name")),
        "date": _text(metadata.get("date")),
        "conversation_id": _text(metadata.get("conversation_id")),
        "folder": _text(metadata.get("folder")),
        "has_attachments": bool(metadata.get("has_attachments") or metadata.get("attachment_count")),
        "candidate_kind": "attachment" if attachment_filename else "body",
        "support_type": support_type,
        "attachment_filename": attachment_filename,
        "snippet": text_preview,
        "matched_query_lanes": list(matched_query_lanes),
        "matched_query_queries": list(matched_query_queries),
        "result_key": key,
        "score_kind": _text(metadata.get("score_kind"), "semantic"),
        "score_calibration": _text(metadata.get("score_calibration"), "calibrated"),
        "segment_type": _text(metadata.get("segment_type")),
        "segment_ordinal": _int(metadata.get("segment_ordinal")),
    }


def _basic_support_type(metadata: dict[str, Any], text: str) -> str | None:
    """Classify attachment, segment, or calendar support from metadata and conservative text cues."""
    if _text(metadata.get("attachment_filename") or metadata.get("filename")).strip():
        return "attachment"
    if _text(metadata.get("score_kind")) == "segment_sql" or _text(metadata.get("segment_type")).strip():
        return "segment"
    if bool(metadata.get("is_calendar_message")) or any(
        token in text for token in ("calendar", "meeting", "invite", "termin", "besprechung")
    ):
        return "calendar"
    return None


def _support_type_for_result(result: Any, *, matched_queries: list[str]) -> str:
    """Determine the support type for a search result.

    Classifies a result as body, segment, attachment, or calendar evidence.

    Args:
        result: The search result object to classify.
        matched_queries: List of queries that matched this result (currently unused
            but kept for API compatibility).

    Returns:
        A string representing the support type classification.
    """
    metadata = as_dict(result.metadata)
    explicit_support_type = _text(metadata.get("support_type")).strip().lower()
    if explicit_support_type in {"body", "segment", "attachment", "calendar"}:
        return explicit_support_type

    text = " ".join(
        part
        for part in (
            _text(getattr(result, "text", "")),
            _text(metadata.get("subject")),
            _text(metadata.get("body_render_source")),
            _text(metadata.get("segment_type")),
            _text(metadata.get("source_type")),
        )
        if part
    ).lower()

    del matched_queries
    basic = _basic_support_type(metadata, text)
    if basic is not None:
        return basic
    return "body"


def _support_type_for_row(row: dict[str, Any]) -> str:
    """Determine the support type for a result row from the database.

    Classifies a database row into a support type, similar to _support_type_for_result
    but working with raw row data instead of result objects.

    Args:
        row: A dictionary containing the database row data.

    Returns:
        A string representing the support type classification.
    """
    declared = _text(row.get("support_type")).strip().lower()
    if declared in {"body", "segment", "attachment", "calendar"}:
        return declared
    attachment_filename = ""
    attachment_value: Any = row.get("attachment")
    if isinstance(attachment_value, dict):
        attachment_filename = _text(attachment_value.get("filename"))
    metadata = {
        "attachment_filename": _text(row.get("attachment_filename")),
        "filename": attachment_filename,
        "score_kind": _text(row.get("score_kind")),
        "segment_type": _text(row.get("segment_type")),
        "is_calendar_message": row.get("is_calendar_message"),
        "subject": _text(row.get("subject")),
        "body_render_source": _text(row.get("body_render_source")),
    }
    proxy = type("_RowProxy", (), {"metadata": metadata, "text": _text(row.get("snippet"))})()
    return _support_type_for_result(
        proxy,
        matched_queries=[str(item) for item in row.get("matched_query_queries", []) if str(item).strip()],
    )


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


def _record_lane_match(
    *,
    key: str,
    lane_id: str,
    lane_query: str,
    lane_hits: dict[str, list[str]],
    lane_queries_by_key: dict[str, list[str]],
) -> None:
    """Record that a result key was matched by a specific lane and query.

    Updates the lane_hits and lane_queries_by_key dictionaries to track
    which lanes and queries matched each result key. Avoids duplicates.

    Args:
        key: The result key being matched.
        lane_id: The ID of the lane that matched.
        lane_query: The query string from the lane that matched.
        lane_hits: Dictionary mapping result keys to list of lane IDs.
        lane_queries_by_key: Dictionary mapping result keys to list of queries.
    """
    lane_hits.setdefault(key, [])
    lane_queries_by_key.setdefault(key, [])
    if lane_id not in lane_hits[key]:
        lane_hits[key].append(lane_id)
    if lane_query not in lane_queries_by_key[key]:
        lane_queries_by_key[key].append(lane_query)


def _attachment_identity(metadata: dict[str, Any], uid: str, chunk_id: str, fallback: str) -> str | None:
    """Create a stable attachment deduplication key from UID, filename, and locator metadata."""
    filename = _text(metadata.get("attachment_filename") or metadata.get("filename")).strip()
    if not filename:
        return None
    marker = _text(metadata.get("attachment_id") or chunk_id or metadata.get("source_surface"), "attachment")
    return f"attachment:{uid or fallback}:{filename}:{marker}"


def _segment_identity(metadata: dict[str, Any], uid: str, chunk_id: str, fallback: str) -> str | None:
    """Create a stable segment deduplication key only for segment-backed evidence."""
    ordinal = _int(metadata.get("segment_ordinal"))
    if _text(metadata.get("score_kind")).strip() != "segment_sql" and ordinal <= 0:
        return None
    segment_type = _text(metadata.get("segment_type") or metadata.get("source_surface"), "segment").strip()
    return f"segment:{uid or fallback}:{segment_type}:{ordinal or chunk_id or fallback}"


def _result_identity_key(result: Any, *, fallback: str) -> str:
    """Generate a unique identity key for a result.

    Creates a deterministic string key that uniquely identifies a result
    based on its metadata. Handles different result types (attachments,
    segments, messages) with appropriate key formats.

    Args:
        result: The search result object.
        fallback: Fallback string to use if no other identifier is available.

    Returns:
        A string key identifying this result, with format depending on type:
        - attachment: "attachment:{uid}:{filename}:{marker}"
        - segment: "segment:{uid}:{type}:{ordinal}"
        - chunk: "chunk:{chunk_id}"
        - message: "message:{uid}:{source}"
        - uid: "uid:{uid}"
        - fallback: the fallback string
    """
    metadata = as_dict(result.metadata)
    explicit_key = _text(metadata.get("result_key")).strip()
    if explicit_key:
        return explicit_key

    chunk_id = _text(getattr(result, "chunk_id", "")).strip()
    uid = _text(metadata.get("uid")).strip()
    typed_identity = _attachment_identity(metadata, uid, chunk_id, fallback)
    if typed_identity is None:
        typed_identity = _segment_identity(metadata, uid, chunk_id, fallback)
    if typed_identity is not None:
        return typed_identity

    if chunk_id:
        return f"chunk:{chunk_id}"

    body_render_source = _text(metadata.get("body_render_source")).strip()
    if uid and body_render_source:
        return f"message:{uid}:{body_render_source}"
    if uid:
        return f"uid:{uid}"
    return fallback


def _attachment_score_adjustment(metadata: dict[str, Any]) -> float:
    """Reward attachment text strength and successful extraction without affecting non-attachments."""
    if not _text(metadata.get("attachment_filename") or metadata.get("filename")).strip():
        return 0.0
    adjustment = 0.01
    if _text(metadata.get("evidence_strength")) == "strong_text":
        adjustment += 0.015
    if _text(metadata.get("extraction_state")).strip().lower() in {
        "ocr_text_extracted",
        "archive_contents_extracted",
    }:
        adjustment += 0.005
    return adjustment


def _locator_score_adjustment(metadata: dict[str, Any]) -> float:
    """Reward evidence with one or multiple precise source locator fields."""
    keys = ("attachment_id", "content_sha256", "segment_ordinal", "snippet_start", "snippet_end", "char_start", "char_end")
    count = sum(1 for key in keys if metadata.get(key) not in (None, "", 0))
    if count >= 2:
        return 0.012
    return 0.006 if count == 1 else 0.0


def _verification_score_adjustment(metadata: dict[str, Any], *, exact_wording: bool) -> float:
    """Apply calibrated verification bonuses, with larger rewards for exact-wording evidence."""
    status = _text(metadata.get("verification_status")).strip()
    source = _text(metadata.get("body_render_source")).strip()
    adjustment = 0.015 if status in {"retrieval_exact", "forensic_exact", "hybrid_verified_forensic", "segment_exact"} else 0.0
    if status == "near_exact_verified":
        adjustment = 0.008
    if not exact_wording:
        return adjustment
    if status in {"forensic_exact", "segment_exact"}:
        adjustment += 0.07
    elif status in {"retrieval_exact", "hybrid_verified_forensic"}:
        adjustment += 0.04
    if source in {"forensic_body_text", "message_segments", "quoted_reply"}:
        adjustment += 0.02
    if status in {"thread_context", "attachment_reference", "mixed_source_reference"}:
        adjustment -= 0.025
    return adjustment


def _result_competition_score(result: Any, *, exact_wording: bool = False) -> float:
    """Calculate a competition score for ranking results.

    Computes a modified score for a result that incorporates various quality
    signals beyond the base retrieval score. Adjusts based on calibration,
    score kind, verification status, attachment presence, locator fields,
    and whether exact wording was requested.

    Args:
        result: The search result object.
        exact_wording: Whether exact wording matching is requested.

    Returns:
        A float score that can be used for ranking results.
    """
    metadata = as_dict(result.metadata)
    score = _float(getattr(result, "score", 0.0))
    calibration = _text(metadata.get("score_calibration")).strip()
    score_kind = _text(metadata.get("score_kind")).strip()
    if calibration == "calibrated":
        score += 0.03
    elif calibration == "synthetic":
        score -= 0.02
    if score_kind == "segment_sql":
        score += 0.015
    return (
        score
        + _attachment_score_adjustment(metadata)
        + _locator_score_adjustment(metadata)
        + _verification_score_adjustment(metadata, exact_wording=exact_wording)
    )


def _result_competition_key(result: Any, *, exact_wording: bool = False) -> tuple[float, float, str]:
    """Generate a competition key for sorting results.

    Creates a tuple key that can be used to sort results, incorporating
    the competition score, original score, and a unique identifier.

    Args:
        result: The search result object.
        exact_wording: Whether exact wording matching is requested.

    Returns:
        A tuple of (competition_score, original_score, identifier) for sorting.
    """
    metadata = as_dict(result.metadata)
    return (
        _result_competition_score(result, exact_wording=exact_wording),
        float(getattr(result, "score", 0.0) or 0.0),
        str(getattr(result, "chunk_id", "") or metadata.get("uid") or ""),
    )


def _lane_order(ranked: list[tuple[str, Any]], lane_hits: dict[str, list[str]]) -> list[str]:
    """Preserve first-ranked occurrence order for valid query-lane identifiers."""
    order: list[str] = []
    for key, _result in ranked:
        for lane_id in lane_hits.get(key, []):
            if lane_id.startswith("lane_") and lane_id not in order:
                order.append(lane_id)
    return order


def _reserve_lane_keys(
    selected: list[str], ranked: list[tuple[str, Any]], lane_hits: dict[str, list[str]], lane_id: str, limit: int
) -> None:
    """Reserve up to the per-lane limit of unselected ranked evidence keys."""
    reserved = 0
    for key, _result in ranked:
        if key in selected or lane_id not in lane_hits.get(key, []):
            continue
        selected.append(key)
        reserved += 1
        if reserved >= limit:
            return


def _fill_ranked_keys(selected: list[str], ranked: list[tuple[str, Any]], bank_limit: int) -> None:
    """Fill remaining evidence-bank capacity by global rank without duplicates."""
    for key, _result in ranked:
        if key not in selected:
            selected.append(key)
        if len(selected) >= bank_limit:
            return


def _evidence_bank_keys_with_lane_diversity(
    *,
    ranked: list[tuple[str, Any]],
    lane_hits: dict[str, list[str]],
    bank_limit: int,
    reserve_per_lane: int,
) -> list[str]:
    """Select evidence bank keys with lane diversity.

    Selects result keys for the evidence bank ensuring representation from
    each lane. Prioritizes results from each lane in order, reserving at
    least reserve_per_lane results per lane before filling remaining slots.

    Args:
        ranked: List of (key, result) tuples sorted by relevance.
        lane_hits: Dictionary mapping result keys to list of lane IDs that matched.
        bank_limit: Maximum number of keys to select.
        reserve_per_lane: Minimum number of results to reserve per lane.

    Returns:
        A list of selected result keys, limited to bank_limit.
    """
    selected_keys: list[str] = []
    if bank_limit <= 0:
        return selected_keys
    reserve_limit = max(reserve_per_lane, 0)
    for lane_id in _lane_order(ranked, lane_hits):
        _reserve_lane_keys(selected_keys, ranked, lane_hits, lane_id, reserve_limit)
        if len(selected_keys) >= bank_limit:
            return selected_keys[:bank_limit]
    _fill_ranked_keys(selected_keys, ranked, bank_limit)
    return selected_keys[:bank_limit]


def _unique_limited(keys: list[str], limit: int) -> list[str]:
    """Deduplicate keys in encounter order and stop at the requested limit."""
    selected: list[str] = []
    for key in keys:
        if key not in selected:
            selected.append(key)
        if len(selected) >= limit:
            return selected
    return selected


def _add_support_type(
    selected: list[str],
    ranked: list[tuple[str, Any]],
    queries_by_key: dict[str, list[str]],
    required_type: str,
) -> bool:
    """Select the first unchosen result that provides the required evidence type."""
    for key, result in ranked:
        if key in selected:
            continue
        if _support_type_for_result(result, matched_queries=queries_by_key.get(key, [])) == required_type:
            selected.append(key)
            return True
    return False


def _evidence_bank_keys_with_support_diversity(
    *,
    ranked: list[tuple[str, Any]],
    selected_keys: list[str],
    lane_queries_by_key: dict[str, list[str]],
    bank_limit: int,
) -> list[str]:
    """Select evidence bank keys with support type diversity.

    Ensures the evidence bank includes generic body, segment, attachment, and
    calendar support when those surfaces are available.
    First includes already selected keys, then adds missing support types.

    Args:
        ranked: List of (key, result) tuples sorted by relevance.
        selected_keys: List of already selected result keys.
        lane_queries_by_key: Dictionary mapping result keys to list of matched queries.
        bank_limit: Maximum number of keys to select.

    Returns:
        A list of selected result keys with support type diversity, limited to bank_limit.
    """
    if bank_limit <= 0:
        return []
    selected = _unique_limited(selected_keys, bank_limit)

    support_types_present = {
        _support_type_for_result(result, matched_queries=lane_queries_by_key.get(key, []))
        for key, result in ranked
        if key in selected
    }
    for required_type in ("body", "segment", "attachment", "calendar"):
        if required_type in support_types_present:
            continue
        if _add_support_type(selected, ranked, lane_queries_by_key, required_type):
            support_types_present.add(required_type)
        if len(selected) >= bank_limit:
            break
    return selected[:bank_limit]


"""Single-lane answer-context retrieval, result merging, and diagnostics."""


# isort: off
# isort: on


@dataclass(slots=True)
class LaneDiagnosticsInput:
    """Capture one executed lane's search output and diagnostics inputs."""

    lane_id: str
    query: str
    executed_query: str
    results: list[Any]
    scan_id: str | None
    scan_meta: dict[str, Any] | None
    lane_search_top_k: int
    expansion_terms: list[str]
    debug: dict[str, Any]
    segment_diag: dict[str, Any]


@dataclass(slots=True)
class SingleLanePayloadInput:
    """Provide ranked single-lane evidence and limits for response assembly."""

    ranked_results: list[tuple[str, Any]]
    combined_results: dict[str, Any]
    lane_queries_by_key: dict[str, list[str]]
    bank_keys: list[str]
    query: str
    expansion_terms: list[str]
    recovered_terms: list[str]
    recovered_key_count: int
    bank_limit: int
    lane_search_top_k: int
    top_k: int


def _apply_filter_seen(scan_id: str | None, results: list[Any]) -> tuple[list[Any], dict[str, Any] | None]:
    """Apply scan session filtering to results.

    Filters out results that have already been seen in a previous scan session.
    If no scan_id is provided, returns the results unchanged.

    Args:
        scan_id: Optional identifier for the scan session.
        results: List of search results to filter.

    Returns:
        A tuple of (filtered_results, scan_meta) where scan_meta contains
        metadata about the filtering operation, or None if no filtering was done.
    """
    if scan_id:
        return filter_seen(scan_id, results)
    return results, None


def _build_lane_diagnostics_item(context: LaneDiagnosticsInput) -> dict[str, Any]:
    """Build a diagnostics item for a single lane.

    Creates a structured diagnostics dictionary containing information about
    a lane's search operation, including query, results count, expansion terms,
    and scan metadata.

    Args:
        context: LaneDiagnosticsInput dataclass containing all lane diagnostics data.

    Returns:
        A dictionary with lane diagnostics information.
    """
    item: dict[str, Any] = {
        "lane_id": context.lane_id,
        "query": context.query,
        "executed_query": context.executed_query,
        "result_count": len(context.results),
        "used_query_expansion": bool(context.debug.get("used_query_expansion")),
        "scan_id": context.scan_id or "",
        "excluded_count": int((context.scan_meta or {}).get("excluded_count") or 0),
        "search_top_k": context.lane_search_top_k,
        "expansion_terms": context.expansion_terms,
    }
    item.update(context.segment_diag)
    return item


def _build_evidence_bank(
    bank_keys: list[str],
    combined: dict[str, Any],
    lane_hits: dict[str, list[str]],
    lane_queries_by_key: dict[str, list[str]],
    *,
    is_single_lane: bool = False,
    single_query: str = "",
) -> list[dict[str, Any]]:
    """Build an evidence bank from selected result keys.

    Creates a list of evidence bank entries for the selected keys, extracting
    relevant metadata and content from each result.

    Args:
        bank_keys: List of result keys to include in the evidence bank.
        combined: Dictionary mapping result keys to result objects.
        lane_hits: Dictionary mapping result keys to list of lane IDs that matched.
        lane_queries_by_key: Dictionary mapping result keys to list of matched queries.
        is_single_lane: Whether this is a single-lane search (affects lane matching).
        single_query: The single query used for single-lane searches.

    Returns:
        A list of evidence bank entry dictionaries.
    """
    evidence_bank = []
    for key in bank_keys:
        result = combined[key]
        matched_lanes = ["lane_1"] if is_single_lane else lane_hits.get(key, [])
        matched_queries = lane_queries_by_key.get(key, [single_query]) if is_single_lane else lane_queries_by_key.get(key, [])
        evidence_bank.append(
            _bank_entry(
                result=result,
                key=key,
                matched_query_lanes=matched_lanes,
                matched_query_queries=matched_queries,
            )
        )
    return evidence_bank


def _compute_support_type_counts(
    bank_keys: list[str],
    combined: dict[str, Any],
    lane_queries_by_key: dict[str, list[str]],
) -> dict[str, int]:
    """Compute counts of each support type in the evidence bank.

    Iterates through the selected bank keys and counts how many results
    belong to each support type category.

    Args:
        bank_keys: List of result keys in the evidence bank.
        combined: Dictionary mapping result keys to result objects.
        lane_queries_by_key: Dictionary mapping result keys to list of matched queries.

    Returns:
        A dictionary mapping support type strings to their counts.
    """
    counts: dict[str, int] = {}
    for key in bank_keys:
        support_type = _support_type_for_result(combined[key], matched_queries=lane_queries_by_key.get(key, []))
        counts[support_type] = int(counts.get(support_type, 0)) + 1
    return counts


def _single_lane_search_kwargs(search_kwargs: dict[str, Any], *, query: str, lane_search_top_k: int) -> dict[str, Any]:
    """Prepare search kwargs for a single lane search.

    Filters and prepares the search keyword arguments for a single-lane
    search, removing internal parameters (those starting with '_') and
    setting the query and top_k values.

    Args:
        search_kwargs: Base search keyword arguments.
        query: The query string for this lane.
        lane_search_top_k: The top_k value for this lane's search.

    Returns:
        A filtered dictionary of search kwargs suitable for the retriever.
    """
    return {
        key: value
        for key, value in {**search_kwargs, "query": query, "top_k": lane_search_top_k}.items()
        if not str(key).startswith("_")
    }


def _merge_single_lane_results(results: list[Any], *, exact_wording: bool) -> dict[str, Any]:
    """Merge results from a single lane into a combined dictionary.

    Deduplicates results by their identity key, keeping the highest-scoring
    version of each result based on the competition key.

    Args:
        results: List of search results to merge.
        exact_wording: Whether exact wording matching is requested (affects scoring).

    Returns:
        A dictionary mapping result identity keys to the best result for each key.
    """
    combined_results: dict[str, Any] = {}
    for result in results:
        key = _result_identity_key(result, fallback="lane_1")
        existing = combined_results.get(key)
        if existing is None or _result_competition_key(result, exact_wording=exact_wording) > _result_competition_key(
            existing,
            exact_wording=exact_wording,
        ):
            combined_results[key] = result
    return combined_results


def _annotate_single_lane_results(ranked_results: list[tuple[str, Any]], *, query: str) -> dict[str, list[str]]:
    """Annotate single-lane results with lane and query information.

    Adds matched_query_lanes and matched_query_queries metadata to each result,
    and returns a dictionary mapping result keys to their matched queries.

    Args:
        ranked_results: List of (key, result) tuples sorted by relevance.
        query: The query string used for this lane.

    Returns:
        A dictionary mapping result keys to list of matched query strings.
    """
    for _key, result in ranked_results:
        metadata = as_dict(result.metadata)
        metadata["matched_query_lanes"] = ["lane_1"]
        metadata["matched_query_queries"] = [query]
    return {key: [query] for key, _result in ranked_results}


def _single_lane_bank_keys(
    *,
    ranked_results: list[tuple[str, Any]],
    lane_queries_by_key: dict[str, list[str]],
    bank_limit: int,
) -> list[str]:
    """Select bank keys for a single-lane search.

    Selects result keys for the evidence bank using both lane diversity
    and support type diversity criteria.

    Args:
        ranked_results: List of (key, result) tuples sorted by relevance.
        lane_queries_by_key: Dictionary mapping result keys to list of matched queries.
        bank_limit: Maximum number of keys to select.

    Returns:
        A list of selected result keys with both lane and support type diversity.
    """
    bank_keys = _evidence_bank_keys_with_lane_diversity(
        ranked=ranked_results,
        lane_hits={key: ["lane_1"] for key, _result in ranked_results},
        bank_limit=bank_limit,
        reserve_per_lane=1,
    )
    return _evidence_bank_keys_with_support_diversity(
        ranked=ranked_results,
        selected_keys=bank_keys,
        lane_queries_by_key=lane_queries_by_key,
        bank_limit=bank_limit,
    )


def _single_lane_payload(context: SingleLanePayloadInput) -> dict[str, Any]:
    """Build the payload for a single-lane search result.

    Creates a structured payload containing evidence bank, support type
    diversity information, expansion attribution, and other metadata.

    Args:
        context: SingleLanePayloadInput dataclass containing all payload data.

    Returns:
        A dictionary containing the complete single-lane payload.
    """
    support_type_counts = _compute_support_type_counts(
        bank_keys=context.bank_keys,
        combined=context.combined_results,
        lane_queries_by_key=context.lane_queries_by_key,
    )
    evidence_bank = _build_evidence_bank(
        bank_keys=context.bank_keys,
        combined=context.combined_results,
        lane_hits={},
        lane_queries_by_key=context.lane_queries_by_key,
        is_single_lane=True,
        single_query=context.query,
    )
    return {
        "candidate_pool_count": len(context.ranked_results),
        "selected_result_count": min(len(context.ranked_results), context.top_k),
        "lane_top_k": context.lane_search_top_k,
        "merge_budget": context.bank_limit,
        "support_diversity": {
            "selected_support_types": sorted(support_type_counts.keys()),
            "counts_by_support_type": support_type_counts,
        },
        "expansion_attribution": [
            {
                "lane_id": "lane_1",
                "query": context.query,
                "new_key_count": len(context.ranked_results),
                "expansion_terms": context.expansion_terms,
                "recovered_expansion_terms": context.recovered_terms,
                "recovered_expansion_key_count": context.recovered_key_count,
            }
        ],
        "evidence_bank": evidence_bank[: context.bank_limit],
        "evidence_results": [result for _key, result in context.ranked_results[: context.bank_limit]],
    }


def _single_lane_runtime_context(
    *,
    retriever: Any,
    search_kwargs: dict[str, Any],
    query: str,
    scan_id: str | None,
    lane_search_top_k: int,
    bank_limit: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    """Execute a single-lane search and return runtime context.

    Performs the actual search using the retriever, applies scan filtering,
    extracts expansion terms, runs segment search, builds diagnostics,
    and merges results.

    Args:
        retriever: The retriever object used for searching.
        search_kwargs: Base search keyword arguments.
        query: The query string for this lane.
        scan_id: Optional identifier for the scan session.
        lane_search_top_k: The top_k value for this lane's search.
        bank_limit: Maximum number of results to include in the evidence bank.

    Returns:
        A tuple of (combined_results, lane_diagnostics, expansion_terms).
    """
    results = retriever.search_filtered(
        **_single_lane_search_kwargs(search_kwargs, query=query, lane_search_top_k=lane_search_top_k)
    )
    results, scan_meta = _apply_filter_seen(scan_id, results)
    debug = dict(getattr(retriever, "last_search_debug", getattr(retriever, "_last_search_debug", None)) or {})
    executed_query = str(debug.get("executed_query") or query)
    expansion_terms = _lane_expansion_terms(
        base_query=query,
        lane_query=query,
        executed_query=executed_query,
        query_expansion_suffix=str(debug.get("query_expansion_suffix") or ""),
    )
    segment_results, segment_diag = _segment_search_results(
        retriever=retriever,
        lane_query=query,
        lane_id="lane_1",
        limit=max(4, min(bank_limit, lane_search_top_k // 2 or 4)),
        scan_id=scan_id,
    )
    lane_diagnostics = [
        _build_lane_diagnostics_item(
            LaneDiagnosticsInput(
                lane_id="lane_1",
                query=query,
                executed_query=executed_query,
                results=results,
                scan_id=scan_id,
                scan_meta=scan_meta,
                lane_search_top_k=lane_search_top_k,
                expansion_terms=expansion_terms,
                debug=debug,
                segment_diag=segment_diag,
            )
        )
    ]
    exact_wording = bool(search_kwargs.get("_exact_wording_requested"))
    combined_results = _merge_single_lane_results([*results, *segment_results], exact_wording=exact_wording)
    return combined_results, lane_diagnostics, expansion_terms


def _search_single_lane(
    *,
    retriever: Any,
    search_kwargs: dict[str, Any],
    query_lanes: list[str],
    top_k: int,
    scan_id: str | None,
    lane_search_top_k: int,
    bank_limit: int,
) -> tuple[list[Any], list[dict[str, Any]], dict[str, Any]]:
    """Search a single lane and return results with diagnostics and payload.

    Main entry point for single-lane search. Executes the runtime context
    and assembles the final results.

    Args:
        retriever: The retriever object used for searching.
        search_kwargs: Base search keyword arguments.
        query_lanes: List of query lane strings (only the first is used).
        top_k: Maximum number of results to return.
        scan_id: Optional identifier for the scan session.
        lane_search_top_k: The top_k value for this lane's search.
        bank_limit: Maximum number of results to include in the evidence bank.

    Returns:
        A tuple of (results, lane_diagnostics, payload).
    """
    exact_wording = bool(search_kwargs.get("_exact_wording_requested"))
    query = query_lanes[0]
    combined_results, lane_diagnostics, expansion_terms = _single_lane_runtime_context(
        retriever=retriever,
        search_kwargs=search_kwargs,
        query=query,
        scan_id=scan_id,
        lane_search_top_k=lane_search_top_k,
        bank_limit=bank_limit,
    )
    return _assemble_single_lane_results(
        combined_results=combined_results,
        exact_wording=exact_wording,
        lane_diagnostics=lane_diagnostics,
        expansion_terms=expansion_terms,
        query_lanes=query_lanes,
        top_k=top_k,
        bank_limit=bank_limit,
        lane_search_top_k=lane_search_top_k,
    )


def _assemble_single_lane_results(
    *,
    combined_results: dict[str, Any],
    exact_wording: bool,
    lane_diagnostics: list[dict[str, Any]],
    expansion_terms: list[str],
    query_lanes: list[str],
    top_k: int,
    bank_limit: int,
    lane_search_top_k: int,
) -> tuple[list[Any], list[dict[str, Any]], dict[str, Any]]:
    """Assemble final results from combined single-lane results.

    Ranks results, computes expansion term recovery, annotates with lane
    information, selects bank keys, and builds the final payload.

    Args:
        combined_results: Dictionary of merged results from all sources.
        exact_wording: Whether exact wording matching is requested.
        lane_diagnostics: List of diagnostics items for each lane.
        expansion_terms: List of query expansion terms to track.
        query_lanes: List of query lane strings.
        top_k: Maximum number of results to return.
        bank_limit: Maximum number of results to include in the evidence bank.
        lane_search_top_k: The top_k value used for lane searches.

    Returns:
        A tuple of (results, lane_diagnostics, payload).
    """
    ranked_results = sorted(
        combined_results.items(),
        key=lambda item: _result_competition_key(item[1], exact_wording=exact_wording),
        reverse=True,
    )
    lane_diagnostics[0]["new_key_count"] = len(ranked_results)
    recovered_terms, recovered_key_count = _lane_recovered_expansion_terms(
        expansion_terms=expansion_terms,
        new_keys=[key for key, _result in ranked_results],
        result_lookup=combined_results,
    )
    lane_diagnostics[0]["recovered_expansion_terms"] = recovered_terms
    lane_diagnostics[0]["recovered_expansion_key_count"] = recovered_key_count
    query = query_lanes[0]
    lane_queries_by_key = _annotate_single_lane_results(ranked_results, query=query)
    bank_keys = _single_lane_bank_keys(
        ranked_results=ranked_results,
        lane_queries_by_key=lane_queries_by_key,
        bank_limit=bank_limit,
    )
    return (
        [result for _key, result in ranked_results[:top_k]],
        lane_diagnostics,
        _single_lane_payload(
            SingleLanePayloadInput(
                ranked_results=ranked_results,
                combined_results=combined_results,
                lane_queries_by_key=lane_queries_by_key,
                bank_keys=bank_keys,
                query=query,
                expansion_terms=expansion_terms,
                recovered_terms=recovered_terms,
                recovered_key_count=recovered_key_count,
                bank_limit=bank_limit,
                lane_search_top_k=lane_search_top_k,
                top_k=top_k,
            )
        ),
    )


"""Multi-lane retrieval, merging, and diagnostics for answer-context payloads."""


@dataclass(slots=True)
class MultiLanePayloadInput:
    """Collect merged lane results and selection limits for payload construction."""

    ranked: list[tuple[str, Any]]
    combined: dict[str, Any]
    lane_hits: dict[str, list[str]]
    lane_queries_by_key: dict[str, list[str]]
    lane_diagnostics: list[dict[str, Any]]
    bank_limit: int
    reserve_per_lane: int
    lane_search_top_k: int
    reserved_keys: list[str]
    merged: list[Any]


@dataclass(slots=True)
class LaneCollectionState:
    """Accumulate deduplicated lane hits, diagnostics, and reserved evidence keys."""

    combined: dict[str, Any]
    lane_hits: dict[str, list[str]]
    lane_queries_by_key: dict[str, list[str]]
    reserved_keys: list[str]
    lane_diagnostics: list[dict[str, Any]]


@dataclass(slots=True)
class LaneProcessingInput:
    """Provide one lane's retrieval request and merge policy to the worker."""

    retriever: Any
    search_kwargs: dict[str, Any]
    lane_query: str
    lane_id: str
    scan_id: str | None
    lane_search_top_k: int
    bank_limit: int
    reserve_per_lane: int
    exact_wording: bool
    base_lane_query: str


def _lane_search_kwargs(search_kwargs: dict[str, Any], *, lane_query: str, lane_search_top_k: int) -> dict[str, Any]:
    """Create search kwargs for a specific lane.

    Combines base search kwargs with lane-specific query and top_k,
    filtering out keys that start with underscore.

    Args:
        search_kwargs: Base search keyword arguments.
        lane_query: The query string for this lane.
        lane_search_top_k: The top_k value for this lane.

    Returns:
        A dictionary of search kwargs for the lane.
    """
    return {
        key: value
        for key, value in {**search_kwargs, "query": lane_query, "top_k": lane_search_top_k}.items()
        if not str(key).startswith("_")
    }


def _remember_best_result(
    combined: dict[str, Any],
    *,
    key: str,
    result: Any,
    exact_wording: bool,
) -> None:
    """Store the best result for a given key in the combined results dict.

    Compares the new result against any existing result for the same key
    using the competition key, and keeps the better one.

    Args:
        combined: The dictionary storing combined results.
        key: The key for this result.
        result: The result to potentially store.
        exact_wording: Whether exact wording is requested.
    """
    existing = combined.get(key)
    if existing is None or _result_competition_key(result, exact_wording=exact_wording) > _result_competition_key(
        existing,
        exact_wording=exact_wording,
    ):
        combined[key] = result


def _lane_runtime_results(
    *,
    retriever: Any,
    search_kwargs: dict[str, Any],
    lane_query: str,
    lane_id: str,
    scan_id: str | None,
    lane_search_top_k: int,
    bank_limit: int,
    base_lane_query: str,
) -> tuple[list[Any], list[Any], list[Any], dict[str, Any], list[str], dict[str, Any] | None]:
    """Execute search for a single lane and return results with diagnostics.

    Performs the main search, applies seen filters, extracts segment results,
    and builds lane diagnostics.

    Args:
        retriever: The retriever instance to use for search.
        search_kwargs: Base search keyword arguments.
        lane_query: The query string for this lane.
        lane_id: Identifier for this lane.
        scan_id: Optional scan identifier.
        lane_search_top_k: Top k for lane search.
        bank_limit: Maximum items in the evidence bank.
        base_lane_query: The base query for this lane.

    Returns:
        A tuple of (raw_lane_results, lane_results, segment_results,
        diagnostics, expansion_terms, lane_scan_meta).
    """
    lane_results = retriever.search_filtered(
        **_lane_search_kwargs(
            search_kwargs,
            lane_query=lane_query,
            lane_search_top_k=lane_search_top_k,
        )
    )
    raw_lane_results = list(lane_results)
    lane_results, lane_scan_meta = _apply_filter_seen(scan_id, lane_results)
    debug = dict(getattr(retriever, "last_search_debug", getattr(retriever, "_last_search_debug", None)) or {})
    executed_query = str(debug.get("executed_query") or lane_query)
    expansion_terms = _lane_expansion_terms(
        base_query=base_lane_query,
        lane_query=lane_query,
        executed_query=executed_query,
        query_expansion_suffix=str(debug.get("query_expansion_suffix") or ""),
    )
    segment_results, segment_diag = _segment_search_results(
        retriever=retriever,
        lane_query=lane_query,
        lane_id=lane_id,
        limit=max(4, min(bank_limit, lane_search_top_k // 2 or 4)),
        scan_id=scan_id,
    )
    diagnostics = _build_lane_diagnostics_item(
        LaneDiagnosticsInput(
            lane_id=lane_id,
            query=lane_query,
            executed_query=executed_query,
            results=lane_results,
            scan_id=scan_id,
            scan_meta=lane_scan_meta,
            lane_search_top_k=lane_search_top_k,
            expansion_terms=expansion_terms,
            debug=debug,
            segment_diag=segment_diag,
        )
    )
    return raw_lane_results, lane_results, segment_results, diagnostics, expansion_terms, lane_scan_meta


def _record_raw_lane_matches(
    *,
    lane_results: list[Any],
    lane_id: str,
    lane_query: str,
    lane_hits: dict[str, list[str]],
    lane_queries_by_key: dict[str, list[str]],
) -> None:
    """Record which lane matched each result.

    Iterates through lane results and records the lane_id and lane_query
    for each result's identity key in the tracking dictionaries.

    Args:
        lane_results: List of results from the lane search.
        lane_id: Identifier for this lane.
        lane_query: The query string for this lane.
        lane_hits: Dictionary mapping keys to list of lane IDs that hit them.
        lane_queries_by_key: Dictionary mapping keys to list of queries that hit them.
    """
    for result in lane_results:
        key = _result_identity_key(result, fallback=lane_id)
        _record_lane_match(
            key=key,
            lane_id=lane_id,
            lane_query=lane_query,
            lane_hits=lane_hits,
            lane_queries_by_key=lane_queries_by_key,
        )


def _merge_lane_results_for_diagnostics(
    *,
    combined: dict[str, Any],
    lane_results: list[Any],
    segment_results: list[Any],
    lane_id: str,
    lane_query: str,
    lane_hits: dict[str, list[str]],
    lane_queries_by_key: dict[str, list[str]],
    exact_wording: bool,
) -> list[str]:
    """Merge lane results into combined dict and return reserved keys.

    Merges both regular and segment results into the combined dictionary,
    recording matches and returning the list of keys reserved by this lane.

    Args:
        combined: The shared dictionary for combined results.
        lane_results: Regular results from the lane search.
        segment_results: Segment-level results from the lane search.
        lane_id: Identifier for this lane.
        lane_query: The query string for this lane.
        lane_hits: Dictionary mapping keys to list of lane IDs that hit them.
        lane_queries_by_key: Dictionary mapping keys to list of queries that hit them.
        exact_wording: Whether exact wording is requested.

    Returns:
        List of keys reserved by this lane (including both regular and segment results).
    """
    lane_reserved_keys = _merge_lane_result_set(
        combined=combined,
        lane_results=lane_results,
        lane_id=lane_id,
        lane_query=lane_query,
        lane_hits=lane_hits,
        lane_queries_by_key=lane_queries_by_key,
        exact_wording=exact_wording,
        record_matches_for_all=False,
    )
    for key in _merge_lane_result_set(
        combined=combined,
        lane_results=segment_results,
        lane_id=lane_id,
        lane_query=lane_query,
        lane_hits=lane_hits,
        lane_queries_by_key=lane_queries_by_key,
        exact_wording=exact_wording,
        record_matches_for_all=True,
    ):
        if key not in lane_reserved_keys:
            lane_reserved_keys.append(key)
    return lane_reserved_keys


def _update_lane_recovery_diagnostics(
    *,
    diagnostics: dict[str, Any],
    combined: dict[str, Any],
    lane_initial_keys: set[str],
    expansion_terms: list[str],
) -> None:
    """Update diagnostics with information about recovered keys from expansion.

    Identifies new keys added to combined that weren't in the initial set,
    and records which expansion terms led to those recoveries.

    Args:
        diagnostics: The diagnostics dictionary to update.
        combined: The combined results dictionary.
        lane_initial_keys: Set of keys that were present before lane processing.
        expansion_terms: List of query expansion terms used for this lane.
    """
    lane_new_keys = [key for key in combined if key not in lane_initial_keys]
    diagnostics["new_key_count"] = len(lane_new_keys)
    recovered_terms, recovered_key_count = _lane_recovered_expansion_terms(
        expansion_terms=expansion_terms,
        new_keys=lane_new_keys,
        result_lookup=combined,
    )
    diagnostics["recovered_expansion_terms"] = recovered_terms
    diagnostics["recovered_expansion_key_count"] = recovered_key_count


def _remember_reserved_keys(
    *,
    reserved_keys: list[str],
    lane_reserved_keys: list[str],
    reserve_per_lane: int,
) -> None:
    """Add lane's reserved keys to the global reserved keys list.

    Takes up to reserve_per_lane keys from the lane's reserved keys and
    adds them to the global reserved_keys list if not already present.

    Args:
        reserved_keys: The global list of reserved keys.
        lane_reserved_keys: The list of keys reserved by this lane.
        reserve_per_lane: Maximum number of keys to reserve per lane.
    """
    for key in lane_reserved_keys[: max(reserve_per_lane, 0)]:
        if key not in reserved_keys:
            reserved_keys.append(key)


def _process_lane_results(context: LaneProcessingInput, state: LaneCollectionState) -> None:
    """Process results for a single lane and update collection state.

    Executes lane search, records matches, merges results, and updates diagnostics.

    Args:
        context: Input parameters for lane processing.
        state: Mutable state for collecting results across lanes.
    """
    lane_initial_keys = set(state.combined.keys())
    raw_lane_results, lane_results, segment_results, diagnostics, expansion_terms, _lane_scan_meta = _lane_runtime_results(
        retriever=context.retriever,
        search_kwargs=context.search_kwargs,
        lane_query=context.lane_query,
        lane_id=context.lane_id,
        scan_id=context.scan_id,
        lane_search_top_k=context.lane_search_top_k,
        bank_limit=context.bank_limit,
        base_lane_query=context.base_lane_query,
    )
    _record_raw_lane_matches(
        lane_results=raw_lane_results,
        lane_id=context.lane_id,
        lane_query=context.lane_query,
        lane_hits=state.lane_hits,
        lane_queries_by_key=state.lane_queries_by_key,
    )
    state.lane_diagnostics.append(diagnostics)
    lane_reserved_keys = _merge_lane_results_for_diagnostics(
        combined=state.combined,
        lane_results=lane_results,
        segment_results=segment_results,
        lane_id=context.lane_id,
        lane_query=context.lane_query,
        lane_hits=state.lane_hits,
        lane_queries_by_key=state.lane_queries_by_key,
        exact_wording=context.exact_wording,
    )
    _remember_reserved_keys(
        reserved_keys=state.reserved_keys,
        lane_reserved_keys=lane_reserved_keys,
        reserve_per_lane=context.reserve_per_lane,
    )
    _update_lane_recovery_diagnostics(
        diagnostics=state.lane_diagnostics[-1],
        combined=state.combined,
        lane_initial_keys=lane_initial_keys,
        expansion_terms=expansion_terms,
    )


def _collect_lane_results(
    *,
    retriever: Any,
    search_kwargs: dict[str, Any],
    query_lanes: list[str],
    scan_id: str | None,
    lane_search_top_k: int,
    bank_limit: int,
    reserve_per_lane: int,
    exact_wording: bool,
) -> tuple[dict[str, Any], dict[str, list[str]], dict[str, list[str]], list[str], list[dict[str, Any]]]:
    """Collect results from all query lanes.

    Processes each lane sequentially, accumulating results and diagnostics.

    Args:
        retriever: The retriever instance to use for search.
        search_kwargs: Base search keyword arguments.
        query_lanes: List of query strings, one per lane.
        scan_id: Optional scan identifier.
        lane_search_top_k: Top k for each lane search.
        bank_limit: Maximum items in the evidence bank.
        reserve_per_lane: Maximum number of keys to reserve per lane.
        exact_wording: Whether exact wording is requested.

    Returns:
        A tuple of (combined, lane_hits, lane_queries_by_key, reserved_keys,
        lane_diagnostics).
    """
    base_lane_query = str(query_lanes[0] or "")
    state = LaneCollectionState(
        combined={},
        lane_hits={},
        lane_queries_by_key={},
        reserved_keys=[],
        lane_diagnostics=[],
    )
    for index, lane_query in enumerate(query_lanes, start=1):
        _process_lane_results(
            LaneProcessingInput(
                retriever=retriever,
                search_kwargs=search_kwargs,
                lane_query=lane_query,
                lane_id=f"lane_{index}",
                scan_id=scan_id,
                lane_search_top_k=lane_search_top_k,
                bank_limit=bank_limit,
                reserve_per_lane=reserve_per_lane,
                exact_wording=exact_wording,
                base_lane_query=base_lane_query,
            ),
            state=state,
        )
    return state.combined, state.lane_hits, state.lane_queries_by_key, state.reserved_keys, state.lane_diagnostics


def _merge_lane_result_set(
    *,
    combined: dict[str, Any],
    lane_results: list[Any],
    lane_id: str,
    lane_query: str,
    lane_hits: dict[str, list[str]],
    lane_queries_by_key: dict[str, list[str]],
    exact_wording: bool,
    record_matches_for_all: bool,
) -> list[str]:
    """Merge a set of lane results into the combined dictionary.

    For each result, stores the best version in combined and optionally
    records which lane matched it.

    Args:
        combined: The shared dictionary for combined results.
        lane_results: List of results to merge.
        lane_id: Identifier for this lane.
        lane_query: The query string for this lane.
        lane_hits: Dictionary mapping keys to list of lane IDs that hit them.
        lane_queries_by_key: Dictionary mapping keys to list of queries that hit them.
        exact_wording: Whether exact wording is requested.
        record_matches_for_all: If True, record matches for all results.

    Returns:
        List of keys that were added or updated in combined.
    """
    lane_reserved_keys: list[str] = []
    for result in lane_results:
        key = _result_identity_key(result, fallback=lane_id)
        if record_matches_for_all:
            _record_lane_match(
                key=key,
                lane_id=lane_id,
                lane_query=lane_query,
                lane_hits=lane_hits,
                lane_queries_by_key=lane_queries_by_key,
            )
        _remember_best_result(combined, key=key, result=result, exact_wording=exact_wording)
        if key not in lane_reserved_keys:
            lane_reserved_keys.append(key)
    return lane_reserved_keys


def _select_merged_keys(
    *,
    combined: dict[str, Any],
    ranked: list[tuple[str, Any]],
    reserved_keys: list[str],
    top_k: int,
) -> list[str]:
    """Select the top k keys from reserved and ranked results.

    First takes keys from reserved_keys (in order), then fills remaining
    slots from ranked results.

    Args:
        combined: The combined results dictionary.
        ranked: List of (key, result) tuples sorted by competition key.
        reserved_keys: List of keys that should be prioritized.
        top_k: Maximum number of keys to select.

    Returns:
        List of up to top_k selected keys.
    """
    merged_keys: list[str] = []
    for key in reserved_keys:
        if key in combined and key not in merged_keys:
            merged_keys.append(key)
        if len(merged_keys) >= top_k:
            return merged_keys
    for key, _result in ranked:
        if key not in merged_keys:
            merged_keys.append(key)
        if len(merged_keys) >= top_k:
            break
    return merged_keys


def _annotate_merged_results(
    *,
    merged: list[Any],
    lane_hits: dict[str, list[str]],
    lane_queries_by_key: dict[str, list[str]],
) -> None:
    """Annotate merged results with lane matching information.

    Adds metadata to each result's metadata indicating which lanes and
    queries matched it.

    Args:
        merged: List of merged result objects.
        lane_hits: Dictionary mapping keys to list of lane IDs that hit them.
        lane_queries_by_key: Dictionary mapping keys to list of queries that hit them.
    """
    for result in merged:
        metadata = as_dict(result.metadata)
        key = _result_identity_key(result, fallback="")
        metadata["matched_query_lanes"] = lane_hits.get(key, [])
        metadata["matched_query_queries"] = lane_queries_by_key.get(key, [])


def _string_list(value: Any) -> list[str]:
    """Convert a value to a list of non-empty strings.

    If the value is a list, converts each element to string and filters
    out empty strings. Otherwise returns an empty list.

    Args:
        value: The value to convert.

    Returns:
        A list of non-empty strings.
    """
    return [str(term) for term in as_list(value) if str(term).strip()]


def _expansion_attribution_item(item: dict[str, Any]) -> dict[str, Any]:
    """Extract expansion attribution fields from a lane diagnostics item.

    Creates a compact dictionary with the most relevant expansion
    attribution information.

    Args:
        item: A lane diagnostics dictionary.

    Returns:
        A dictionary with lane_id, query, new_key_count, expansion_terms,
        recovered_expansion_terms, and recovered_expansion_key_count.
    """
    return {
        "lane_id": str(item.get("lane_id") or ""),
        "query": str(item.get("query") or ""),
        "new_key_count": int(item.get("new_key_count") or 0),
        "expansion_terms": _string_list(item.get("expansion_terms")),
        "recovered_expansion_terms": _string_list(item.get("recovered_expansion_terms")),
        "recovered_expansion_key_count": int(item.get("recovered_expansion_key_count") or 0),
    }


def _expansion_attribution(lane_diagnostics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract expansion attribution from all lane diagnostics.

    Converts each lane diagnostics item to an expansion attribution item.

    Args:
        lane_diagnostics: List of lane diagnostics dictionaries.

    Returns:
        List of expansion attribution dictionaries.
    """
    return [_expansion_attribution_item(item) for item in lane_diagnostics if isinstance(item, dict)]


def _multi_lane_payload(context: MultiLanePayloadInput) -> dict[str, Any]:
    """Build the multi-lane payload from collected results.

    Constructs the evidence bank, computes support diversity metrics,
    and assembles the final payload with all diagnostic information.

    Args:
        context: Input containing all collected lane results and parameters.

    Returns:
        A dictionary with candidate pool stats, selected results, lane
        parameters, support diversity info, expansion attribution, evidence
        bank, and evidence results.
    """
    bank_keys = _evidence_bank_keys_with_lane_diversity(
        ranked=context.ranked,
        lane_hits=context.lane_hits,
        bank_limit=context.bank_limit,
        reserve_per_lane=context.reserve_per_lane,
    )
    bank_keys = _evidence_bank_keys_with_support_diversity(
        ranked=context.ranked,
        selected_keys=bank_keys,
        lane_queries_by_key=context.lane_queries_by_key,
        bank_limit=context.bank_limit,
    )
    support_type_counts = _compute_support_type_counts(
        bank_keys=bank_keys,
        combined=context.combined,
        lane_queries_by_key=context.lane_queries_by_key,
    )
    return {
        "candidate_pool_count": len(context.ranked),
        "selected_result_count": len(context.merged),
        "lane_top_k": context.lane_search_top_k,
        "merge_budget": context.bank_limit,
        "reserved_per_lane": context.reserve_per_lane,
        "reserved_key_count": len(context.reserved_keys),
        "support_diversity": {
            "selected_support_types": sorted(support_type_counts.keys()),
            "counts_by_support_type": support_type_counts,
        },
        "expansion_attribution": _expansion_attribution(context.lane_diagnostics),
        "evidence_bank": _build_evidence_bank(
            bank_keys=bank_keys,
            combined=context.combined,
            lane_hits=context.lane_hits,
            lane_queries_by_key=context.lane_queries_by_key,
        ),
        "evidence_results": [context.combined[key] for key in bank_keys],
    }


def _search_multi_lane(
    *,
    retriever: Any,
    search_kwargs: dict[str, Any],
    query_lanes: list[str],
    top_k: int,
    scan_id: str | None,
    lane_search_top_k: int,
    bank_limit: int,
    reserve_per_lane: int,
) -> tuple[list[Any], list[dict[str, Any]], dict[str, Any]]:
    """Execute multi-lane search and return merged results with diagnostics.

    Orchestrates the complete multi-lane search process: collects results
    from all lanes, ranks them, selects the top k, annotates with lane info,
    and builds the payload.

    Args:
        retriever: The retriever instance to use for search.
        search_kwargs: Base search keyword arguments.
        query_lanes: List of query strings, one per lane.
        top_k: Maximum number of results to return.
        scan_id: Optional scan identifier.
        lane_search_top_k: Top k for each individual lane search.
        bank_limit: Maximum items in the evidence bank.
        reserve_per_lane: Maximum number of keys to reserve per lane.

    Returns:
        A tuple of (merged_results, lane_diagnostics, multi_lane_payload).
    """
    exact_wording = bool(search_kwargs.get("_exact_wording_requested"))
    combined, lane_hits, lane_queries_by_key, reserved_keys, lane_diagnostics = _collect_lane_results(
        retriever=retriever,
        search_kwargs=search_kwargs,
        query_lanes=query_lanes,
        scan_id=scan_id,
        lane_search_top_k=lane_search_top_k,
        bank_limit=bank_limit,
        reserve_per_lane=reserve_per_lane,
        exact_wording=exact_wording,
    )
    ranked = sorted(
        combined.items(), key=lambda item: _result_competition_key(item[1], exact_wording=exact_wording), reverse=True
    )
    merged_keys = _select_merged_keys(combined=combined, ranked=ranked, reserved_keys=reserved_keys, top_k=top_k)
    merged = [combined[key] for key in merged_keys[:top_k]]
    _annotate_merged_results(merged=merged, lane_hits=lane_hits, lane_queries_by_key=lane_queries_by_key)
    return (
        merged,
        lane_diagnostics,
        _multi_lane_payload(
            MultiLanePayloadInput(
                ranked=ranked,
                combined=combined,
                lane_hits=lane_hits,
                lane_queries_by_key=lane_queries_by_key,
                lane_diagnostics=lane_diagnostics,
                bank_limit=bank_limit,
                reserve_per_lane=reserve_per_lane,
                lane_search_top_k=lane_search_top_k,
                reserved_keys=reserved_keys,
                merged=merged,
            )
        ),
    )


"""Query-lane dispatcher for answer-context retrieval."""


def _search_across_query_lanes(
    *,
    retriever: Any,
    search_kwargs: dict[str, Any],
    query_lanes: list[str],
    top_k: int,
    scan_id: str | None = None,
    lane_top_k: int | None = None,
    reserve_per_lane: int = 1,
    bank_limit: int = 20,
) -> tuple[list[Any], list[dict[str, Any]], dict[str, Any]]:
    """Route empty, single-lane, and multi-lane searches while enforcing lane and merge budgets."""
    if not query_lanes:
        return (
            [],
            [],
            {
                "candidate_pool_count": 0,
                "selected_result_count": 0,
                "lane_top_k": 0,
                "merge_budget": bank_limit,
                "evidence_bank": [],
                "evidence_results": [],
            },
        )
    lane_search_top_k = max(top_k, int(lane_top_k or top_k))
    if len(query_lanes) == 1:
        return _search_single_lane(
            retriever=retriever,
            search_kwargs=search_kwargs,
            query_lanes=query_lanes,
            top_k=top_k,
            scan_id=scan_id,
            lane_search_top_k=lane_search_top_k,
            bank_limit=bank_limit,
        )
    return _search_multi_lane(
        retriever=retriever,
        search_kwargs=search_kwargs,
        query_lanes=query_lanes,
        top_k=top_k,
        scan_id=scan_id,
        lane_search_top_k=lane_search_top_k,
        bank_limit=bank_limit,
        reserve_per_lane=reserve_per_lane,
    )
