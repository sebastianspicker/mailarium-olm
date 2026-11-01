"""Result identity keys, competition scoring, and lane- and support-diverse evidence-bank selection."""

from __future__ import annotations

from typing import Any

from mailarium.model.data_shapes import as_dict

from .text import _float, _int, _text


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
