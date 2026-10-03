"""Result identity keys, competition scoring, and lane- and support-diverse evidence-bank selection."""

from __future__ import annotations

from typing import Any

from mailarium.model.data_shapes import as_dict

from .support import _support_type_for_result
from .text import _float, _int, _snippet, _text


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
    support_type = _support_type_for_result(result)
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
    required_type: str,
) -> bool:
    """Select the first unchosen result that provides the required evidence type."""
    for key, result in ranked:
        if key in selected:
            continue
        if _support_type_for_result(result) == required_type:
            selected.append(key)
            return True
    return False


def _evidence_bank_keys_with_support_diversity(
    *,
    ranked: list[tuple[str, Any]],
    selected_keys: list[str],
    bank_limit: int,
) -> list[str]:
    """Select evidence bank keys with support type diversity.

    Ensures the evidence bank includes generic body, segment, attachment, and
    calendar support when those surfaces are available.
    First includes already selected keys, then adds missing support types.

    Args:
        ranked: List of (key, result) tuples sorted by relevance.
        selected_keys: List of already selected result keys.
        bank_limit: Maximum number of keys to select.

    Returns:
        A list of selected result keys with support type diversity, limited to bank_limit.
    """
    if bank_limit <= 0:
        return []
    selected = _unique_limited(selected_keys, bank_limit)

    support_types_present = {_support_type_for_result(result) for key, result in ranked if key in selected}
    for required_type in ("body", "segment", "attachment", "calendar"):
        if required_type in support_types_present:
            continue
        if _add_support_type(selected, ranked, required_type):
            support_types_present.add(required_type)
        if len(selected) >= bank_limit:
            break
    return selected[:bank_limit]


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
) -> dict[str, int]:
    """Compute counts of each support type in the evidence bank.

    Iterates through the selected bank keys and counts how many results
    belong to each support type category.

    Args:
        bank_keys: List of result keys in the evidence bank.
        combined: Dictionary mapping result keys to result objects.

    Returns:
        A dictionary mapping support type strings to their counts.
    """
    counts: dict[str, int] = {}
    for key in bank_keys:
        support_type = _support_type_for_result(combined[key])
        counts[support_type] = int(counts.get(support_type, 0)) + 1
    return counts
