"""Shared helpers for language and sentiment analytics body selection."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from typing import Any

from .language_detector import detect_language_details
from .sentiment_analyzer import analyze as analyze_sentiment

_ENTITY_TEXT_MAX_CHARS = max(2_000, int(os.environ.get("ENTITY_TEXT_MAX_CHARS", "12000")))


def _normalized_text(value: Any) -> str:
    """Normalize a value to a compact string.

    Args:
        value: The value to normalize.

    Returns:
        The value converted to string with whitespace collapsed and stripped.
    """
    return " ".join(str(value or "").split()).strip()


def _mapping_value(row: Mapping[str, Any], key: str) -> Any:
    """Safely get a value from a mapping, returning empty string on error.

    Args:
        row: The mapping to query.
        key: The key to look up.

    Returns:
        The value at the key, or empty string if the key is missing or an error occurs.
    """
    try:
        return row[key]
    except KeyError, IndexError, TypeError:
        return ""


def _attachment_text_from_attachments(attachments: Any) -> str:
    """Extract text from a list of attachments.

    Args:
        attachments: A list of attachment dictionaries or other objects.

    Returns:
        A newline-joined string of text from the first valid text field of each
        attachment, or empty string if no valid text is found.
    """
    values: list[str] = []
    if not isinstance(attachments, list):
        return ""
    for attachment in attachments:
        if not isinstance(attachment, Mapping):
            continue
        for key in ("normalized_text", "extracted_text", "text_preview", "name"):
            text = _normalized_text(attachment.get(key))
            if text:
                values.append(text)
                break
    return "\n".join(values)


def _segment_surface_text(segments: Any, *, segment_types: set[str] | None = None) -> tuple[str, str, int | None]:
    """Extract text from message segments of specified types.

    Args:
        segments: A list of segment dictionaries or objects.
        segment_types: Optional set of segment types to filter by.

    Returns:
        A tuple of (combined_text, source_surface, first_ordinal) where:
        - combined_text: Newline-joined text from matching segments.
        - source_surface: The source surface identifier from the first valid segment.
        - first_ordinal: The ordinal of the first valid segment, or None.
    """
    if not isinstance(segments, list):
        return "", "", None
    parts: list[str] = []
    source_surface = ""
    first_ordinal: int | None = None
    for index, segment in enumerate(segments):
        segment_type, segment_text, segment_source_surface, segment_ordinal_raw = _segment_fields(segment, index)
        if segment_types is not None and segment_type not in segment_types:
            continue
        text = _normalized_text(segment_text)
        if not text:
            continue
        if not source_surface:
            source_surface = _normalized_text(segment_source_surface) or "body_text"
        if first_ordinal is None:
            first_ordinal = _ordinal_or_default(segment_ordinal_raw, index)
        parts.append(text)
    return "\n".join(parts), source_surface, first_ordinal


def _segment_fields(segment: Any, index: int) -> tuple[str, Any, Any, Any]:
    """Read common segment fields from mappings and legacy attribute objects."""
    getter = segment.get if isinstance(segment, Mapping) else lambda key, default="": getattr(segment, key, default)
    return str(getter("segment_type") or "").strip(), getter("text"), getter("source_surface"), getter("ordinal", index)


def _ordinal_or_default(value: Any, default: int) -> int:
    """Convert an ordinal when possible; retain the caller's source-order fallback."""
    try:
        return int(value or default)
    except TypeError, ValueError:
        return default


def _optional_ordinal(value: Any) -> int | None:
    """Convert persisted ordinals without turning malformed values into positions."""
    if value is None:
        return None
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _surface_hash(text: str) -> str:
    """Generate a SHA-256 hash for text surface identification.

    Args:
        text: The text to hash.

    Returns:
        A hexadecimal SHA-256 hash string of the text.
    """
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _best_available_text(
    *,
    subject: Any,
    forensic_body_text: Any,
    forensic_body_source: Any,
    normalized_body_text: Any,
    normalized_body_source: Any,
    raw_body_text: Any,
    attachment_text: Any = "",
) -> tuple[str, str]:
    """Select the best available text from multiple sources.

    Args:
        subject: The email subject text.
        forensic_body_text: The forensic body text.
        forensic_body_source: The source identifier for forensic body text.
        normalized_body_text: The normalized/clean body text.
        normalized_body_source: The source identifier for normalized body text.
        raw_body_text: The raw body text.
        attachment_text: Text extracted from attachments.

    Returns:
        A tuple of (selected_text, source_identifier) with the best available text
        and its source. If subject text is available and the body text is short
        (< 8 words), the subject is prepended to the body text.
    """
    subject_text = _normalized_text(subject)
    candidates = (
        (forensic_body_text, forensic_body_source, "forensic_body_text", "subject_plus_forensic_body_text"),
        (normalized_body_text, normalized_body_source, "body_text", "subject_plus_body_text"),
        (raw_body_text, "raw_body_text", "raw_body_text", "subject_plus_raw_body_text"),
    )
    for body, source, default_source, subject_source in candidates:
        selected = _body_text_candidate(subject_text, body, source, default_source, subject_source)
        if selected:
            return selected

    attachment_preview = _normalized_text(attachment_text)
    if subject_text and attachment_preview:
        return f"{subject_text}\n{attachment_preview}", "subject_plus_attachment_text"
    if subject_text:
        return subject_text, "subject"
    if attachment_preview:
        return attachment_preview, "attachment_text"

    return "", ""


def _body_text_candidate(subject, body, source, default_source, subject_source) -> tuple[str, str] | None:
    """Preserve short-body context by pairing it with the message subject."""
    text = _normalized_text(body)
    if not text:
        return None
    if subject and len(text.split()) < 8:
        return f"{subject}\n{text}", _normalized_text(source) or subject_source
    return text, _normalized_text(source) or default_source


def select_analytics_text_from_email(email: Any) -> tuple[str, str]:
    """Prefer authored segments so analytics do not score quoted message history."""
    authored_text, _source_surface, _ordinal = _segment_surface_text(
        getattr(email, "segments", None),
        segment_types={"authored_body"},
    )
    if authored_text:
        return authored_text, "segment:authored_body"
    return _best_available_text(
        subject=getattr(email, "subject", ""),
        forensic_body_text=getattr(email, "forensic_body_text", ""),
        forensic_body_source=getattr(email, "forensic_body_source", ""),
        normalized_body_text=getattr(email, "clean_body", ""),
        normalized_body_source=getattr(email, "clean_body_source", ""),
        raw_body_text=getattr(email, "raw_body_text", ""),
        attachment_text=_attachment_text_from_attachments(getattr(email, "attachments", None)),
    )


def select_analytics_text_from_row(row: Mapping[str, Any]) -> tuple[str, str]:
    """Choose the stored authored segment before falling back to legacy row surfaces."""
    authored_segment_text = _normalized_text(_mapping_value(row, "authored_segment_text"))
    if authored_segment_text:
        return authored_segment_text, "segment:authored_body"
    return _best_available_text(
        subject=_mapping_value(row, "subject"),
        forensic_body_text=_mapping_value(row, "forensic_body_text"),
        forensic_body_source=_mapping_value(row, "forensic_body_source"),
        normalized_body_text=_mapping_value(row, "body_text"),
        normalized_body_source=_mapping_value(row, "normalized_body_source"),
        raw_body_text=_mapping_value(row, "raw_body_text"),
        attachment_text=_mapping_value(row, "attachment_text"),
    )


def _best_entity_text(
    *,
    subject: Any,
    forensic_body_text: Any,
    normalized_body_text: Any,
    raw_body_text: Any,
    attachment_text: Any = "",
) -> tuple[str, str]:
    """Select and combine the best text sources for entity extraction.

    Args:
        subject: The email subject text.
        forensic_body_text: The forensic body text.
        normalized_body_text: The normalized/clean body text.
        raw_body_text: The raw body text.
        attachment_text: Text extracted from attachments.

    Returns:
        A tuple of (combined_text, source_tags) where:
        - combined_text: Newline-joined text from all valid, unique sources.
        - source_tags: A plus-joined string of source identifiers.
        The combined text is truncated if it exceeds _ENTITY_TEXT_MAX_CHARS.
    """
    parts: list[str] = []
    source_tags: list[str] = []
    seen: set[str] = set()
    for source_name, raw_value in (
        ("subject", subject),
        ("forensic_body_text", forensic_body_text),
        ("body_text", normalized_body_text),
        ("raw_body_text", raw_body_text),
        ("attachment_text", attachment_text),
    ):
        normalized = _normalized_text(raw_value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        parts.append(normalized)
        source_tags.append(source_name)
    combined = "\n".join(parts)
    if len(combined) > _ENTITY_TEXT_MAX_CHARS:
        original = combined
        head_chars = int(_ENTITY_TEXT_MAX_CHARS * 0.67)
        tail_chars = max(_ENTITY_TEXT_MAX_CHARS - head_chars, 0)
        separator = "\n[... entity text truncated for extraction ...]\n"
        combined = original[:head_chars].rstrip()
        if tail_chars > 0:
            combined = combined + separator + original[-tail_chars:].lstrip()
    return combined, "+".join(source_tags)


def select_entity_text_from_email(email: Any) -> tuple[str, str]:
    """Build the de-duplicated entity-extraction surface for an in-memory email."""
    return _best_entity_text(
        subject=getattr(email, "subject", ""),
        forensic_body_text=getattr(email, "forensic_body_text", ""),
        normalized_body_text=getattr(email, "clean_body", ""),
        raw_body_text=getattr(email, "raw_body_text", ""),
        attachment_text=_attachment_text_from_attachments(getattr(email, "attachments", None)),
    )


def select_entity_text_from_row(row: Mapping[str, Any]) -> tuple[str, str]:
    """Build the de-duplicated entity-extraction surface for a database row."""
    return _best_entity_text(
        subject=_mapping_value(row, "subject"),
        forensic_body_text=_mapping_value(row, "forensic_body_text"),
        normalized_body_text=_mapping_value(row, "body_text"),
        raw_body_text=_mapping_value(row, "raw_body_text"),
        attachment_text=_mapping_value(row, "attachment_text"),
    )


def build_analytics_update_row(*, uid: str, text: str, source: str) -> tuple[Any, ...]:
    """Produce the persistence row that couples language and sentiment results to one email."""
    normalized_text = _normalized_text(text)
    if not normalized_text:
        raise ValueError("text is required")
    language_details = detect_language_details(normalized_text)
    sentiment = analyze_sentiment(normalized_text)
    language = str(language_details.get("language") or "unknown")
    confidence = _normalized_text(language_details.get("confidence", ""))
    reason = _normalized_text(language_details.get("reason", ""))
    token_count = int(language_details.get("token_count") or 0)
    return (
        language,
        confidence or None,
        reason or None,
        source or None,
        token_count,
        sentiment.sentiment,
        sentiment.score,
        uid,
    )


def _build_surface_language_rows(
    *,
    uid: str,
    candidates: tuple[tuple[str, str, str, int | None], ...],
) -> list[tuple[Any, ...]]:
    """Create traceable language records for each non-empty message surface."""
    rows: list[tuple[Any, ...]] = []
    for surface_scope, text, source_surface, ordinal in candidates:
        normalized_text = _normalized_text(text)
        if not normalized_text:
            continue
        details = detect_language_details(normalized_text)
        rows.append(
            (
                uid,
                surface_scope,
                source_surface or "",
                ordinal,
                _surface_hash(normalized_text),
                len(normalized_text),
                str(details.get("language") or "unknown"),
                _normalized_text(details.get("confidence")),
                _normalized_text(details.get("reason")),
                int(details.get("token_count") or 0),
            )
        )
    return rows


def build_surface_language_rows_from_email(email: Any) -> list[tuple[Any, ...]]:
    """Analyze authored, quoted, header, attachment, and aggregate email surfaces separately."""
    uid = str(getattr(email, "uid", "") or "")
    if not uid:
        return []

    authored_text, authored_source_surface, authored_ordinal = _segment_surface_text(
        getattr(email, "segments", None),
        segment_types={"authored_body"},
    )
    quoted_text, quoted_source_surface, quoted_ordinal = _segment_surface_text(
        getattr(email, "segments", None),
        segment_types={"quoted_reply", "forwarded_message"},
    )
    forwarded_header_text, forwarded_header_surface, forwarded_header_ordinal = _segment_surface_text(
        getattr(email, "segments", None),
        segment_types={"header_block"},
    )
    segment_text, segment_source_surface, segment_ordinal = _segment_surface_text(getattr(email, "segments", None))
    attachment_text = _attachment_text_from_attachments(getattr(email, "attachments", None))

    candidates = (
        ("authored_body", authored_text, authored_source_surface, authored_ordinal),
        ("quoted_body", quoted_text, quoted_source_surface, quoted_ordinal),
        ("forwarded_header", forwarded_header_text, forwarded_header_surface, forwarded_header_ordinal),
        ("attachment_text", attachment_text, "attachments", None),
        ("segment_text", segment_text, segment_source_surface, segment_ordinal),
    )

    return _build_surface_language_rows(uid=uid, candidates=candidates)


def build_surface_language_rows_from_row(row: Mapping[str, Any]) -> list[tuple[Any, ...]]:
    """Reconstruct per-surface language records from persisted email fields."""
    uid = str(_mapping_value(row, "uid") or "")
    if not uid:
        return []

    authored_segment_text = _normalized_text(_mapping_value(row, "authored_segment_text"))
    authored_segment_ordinal = _optional_ordinal(_mapping_value(row, "authored_segment_ordinal"))

    authored_text = authored_segment_text or _normalized_text(
        _mapping_value(row, "forensic_body_text") or _mapping_value(row, "body_text") or _mapping_value(row, "raw_body_text")
    )

    quoted_segment_text = _normalized_text(_mapping_value(row, "quoted_segment_text"))
    quoted_segment_ordinal = _optional_ordinal(_mapping_value(row, "quoted_segment_ordinal"))

    header_segment_text = _normalized_text(_mapping_value(row, "forwarded_header_text"))
    header_segment_ordinal = _optional_ordinal(_mapping_value(row, "forwarded_header_ordinal"))

    segment_text = _normalized_text(_mapping_value(row, "segment_text"))
    segment_ordinal = _optional_ordinal(_mapping_value(row, "segment_ordinal"))

    attachment_text = _normalized_text(_mapping_value(row, "attachment_text"))
    candidates = (
        (
            "authored_body",
            authored_text,
            "message_segments"
            if authored_segment_text
            else (_normalized_text(_mapping_value(row, "forensic_body_source")) or "body_text"),
            authored_segment_ordinal,
        ),
        ("quoted_body", quoted_segment_text, "message_segments", quoted_segment_ordinal),
        ("forwarded_header", header_segment_text, "message_segments", header_segment_ordinal),
        ("attachment_text", attachment_text, "attachments", None),
        ("segment_text", segment_text, "message_segments", segment_ordinal),
    )
    return _build_surface_language_rows(uid=uid, candidates=candidates)
