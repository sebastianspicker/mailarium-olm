# mypy: disable-error-code=name-defined
# pylint: disable=too-many-branches,too-many-return-statements


# pylint: disable=E0602  # cross-module names injected by compatibility facade
"""Split helpers for search answer-context runtime (search_answer_context_runtime_ranking)."""

from __future__ import annotations

import re
from typing import Any

from .._utils import _as_dict
from . import search_answer_context_impl as impl


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
    metadata = _as_dict(result.metadata)
    text_preview = impl._snippet(_text(getattr(result, "text", "")))
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


def _metadata_terms(metadata: dict[str, Any], key: str) -> set[str]:
    value = metadata.get(key)
    values = value if isinstance(value, list) else [value]
    terms: set[str] = set()
    for item in values:
        if item is not None:
            terms.update(re.findall(r"[\w-]+", str(item).lower()))
    return terms


def _support_metadata_tokens(metadata: dict[str, Any]) -> set[str]:
    terms: set[str] = set()
    for key in ("issue_tags", "main_issue_tags", "all_issue_tags", "role_hints", "support_tags", "source_tags"):
        terms.update(_metadata_terms(metadata, key))
    return terms


def _contains_signal(text: str, tokens: set[str], signals: set[str]) -> bool:
    return bool(signals & tokens) or any(signal in text for signal in signals)


def _basic_support_type(metadata: dict[str, Any], text: str) -> str | None:
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

    Classifies a result into one of several support types (body, segment, attachment,
    calendar, comparator, counterevidence) based on metadata and content analysis.
    Checks explicit metadata first, then falls back to content-based classification.

    Args:
        result: The search result object to classify.
        matched_queries: List of queries that matched this result (currently unused
            but kept for API compatibility).

    Returns:
        A string representing the support type classification.
    """
    metadata = _as_dict(result.metadata)
    explicit_support_type = _text(metadata.get("support_type")).strip().lower()
    if explicit_support_type in {"body", "segment", "attachment", "calendar", "comparator", "counterevidence"}:
        return explicit_support_type

    text = " ".join(
        part
        for part in (
            _text(getattr(result, "text", "")),
            _text(metadata.get("subject")),
            _text(metadata.get("body_render_source")),
            _text(metadata.get("segment_type")),
            _text(metadata.get("issue_type")),
            _text(metadata.get("issue_category")),
            _text(metadata.get("source_type")),
        )
        if part
    ).lower()

    del matched_queries
    basic = _basic_support_type(metadata, text)
    if basic is not None:
        return basic
    metadata_tokens = _support_metadata_tokens(metadata)

    comparator_signals = {
        "vergleich",
        "comparator",
        "peer",
        "gleichbehandlung",
        "ungleichbehandlung",
        "vergleichsgruppe",
        "vergleichsperson",
    }
    if _contains_signal(text, metadata_tokens, comparator_signals):
        return "comparator"

    counterevidence_signals = {
        "widerspruch",
        "contradiction",
        "counterevidence",
        "gegenbeleg",
        "omission",
        "unterlassen",
        "nichtantwort",
        "silence",
    }
    if _contains_signal(text, metadata_tokens, counterevidence_signals):
        return "counterevidence"
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
    if declared:
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
    metadata = _as_dict(result.metadata)
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
    filename = _text(metadata.get("attachment_filename") or metadata.get("filename")).strip()
    if not filename:
        return None
    marker = _text(metadata.get("attachment_id") or chunk_id or metadata.get("source_surface"), "attachment")
    return f"attachment:{uid or fallback}:{filename}:{marker}"


def _segment_identity(metadata: dict[str, Any], uid: str, chunk_id: str, fallback: str) -> str | None:
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
    metadata = _as_dict(result.metadata)
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
    keys = ("attachment_id", "content_sha256", "segment_ordinal", "snippet_start", "snippet_end", "char_start", "char_end")
    count = sum(1 for key in keys if metadata.get(key) not in (None, "", 0))
    if count >= 2:
        return 0.012
    return 0.006 if count == 1 else 0.0


def _verification_score_adjustment(metadata: dict[str, Any], *, exact_wording: bool) -> float:
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
    metadata = _as_dict(result.metadata)
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
    metadata = _as_dict(result.metadata)
    return (
        _result_competition_score(result, exact_wording=exact_wording),
        float(getattr(result, "score", 0.0) or 0.0),
        str(getattr(result, "chunk_id", "") or metadata.get("uid") or ""),
    )


def _lane_order(ranked: list[tuple[str, Any]], lane_hits: dict[str, list[str]]) -> list[str]:
    order: list[str] = []
    for key, _result in ranked:
        for lane_id in lane_hits.get(key, []):
            if lane_id.startswith("lane_") and lane_id not in order:
                order.append(lane_id)
    return order


def _reserve_lane_keys(
    selected: list[str], ranked: list[tuple[str, Any]], lane_hits: dict[str, list[str]], lane_id: str, limit: int
) -> None:
    reserved = 0
    for key, _result in ranked:
        if key in selected or lane_id not in lane_hits.get(key, []):
            continue
        selected.append(key)
        reserved += 1
        if reserved >= limit:
            return


def _fill_ranked_keys(selected: list[str], ranked: list[tuple[str, Any]], bank_limit: int) -> None:
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

    Ensures the evidence bank includes results from all support types
    (body, segment, attachment, calendar, comparator, counterevidence).
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
    for required_type in ("body", "segment", "attachment", "calendar", "comparator", "counterevidence"):
        if required_type in support_types_present:
            continue
        if _add_support_type(selected, ranked, lane_queries_by_key, required_type):
            support_types_present.add(required_type)
        if len(selected) >= bank_limit:
            break
    return selected[:bank_limit]


__all__ = [
    "_bank_entry",
    "_evidence_bank_keys_with_lane_diversity",
    "_evidence_bank_keys_with_support_diversity",
    "_lane_expansion_terms",
    "_lane_recovered_expansion_terms",
    "_record_lane_match",
    "_result_competition_key",
    "_result_competition_score",
    "_result_identity_key",
    "_result_search_surface",
    "_support_type_for_result",
    "_support_type_for_row",
    "_term_tokens",
]
