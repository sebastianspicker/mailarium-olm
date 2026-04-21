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
    return " ".join(str(value or "").split()).strip()


def _mapping_value(row: Mapping[str, Any], key: str) -> Any:
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return ""


def _attachment_text_from_attachments(attachments: Any) -> str:
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
    if not isinstance(segments, list):
        return "", "", None
    parts: list[str] = []
    source_surface = ""
    first_ordinal: int | None = None
    for index, segment in enumerate(segments):
        if isinstance(segment, Mapping):
            segment_type = str(segment.get("segment_type") or "").strip()
            segment_text = segment.get("text")
            segment_source_surface = segment.get("source_surface")
            segment_ordinal_raw = segment.get("ordinal")
        else:
            segment_type = str(getattr(segment, "segment_type", "") or "").strip()
            segment_text = getattr(segment, "text", "")
            segment_source_surface = getattr(segment, "source_surface", "")
            segment_ordinal_raw = getattr(segment, "ordinal", index)
        if segment_types is not None and segment_type not in segment_types:
            continue
        text = _normalized_text(segment_text)
        if not text:
            continue
        if not source_surface:
            source_surface = _normalized_text(segment_source_surface) or "body_text"
        if first_ordinal is None:
            try:
                first_ordinal = int(segment_ordinal_raw or index)
            except (TypeError, ValueError):
                first_ordinal = index
        parts.append(text)
    return "\n".join(parts), source_surface, first_ordinal


def _surface_hash(text: str) -> str:
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
    subject_text = _normalized_text(subject)
    forensic_text = _normalized_text(forensic_body_text)
    if forensic_text:
        if subject_text and len(forensic_text.split()) < 8:
            return f"{subject_text}\n{forensic_text}", _normalized_text(forensic_body_source) or "subject_plus_forensic_body_text"
        return forensic_text, _normalized_text(forensic_body_source) or "forensic_body_text"

    normalized_text = _normalized_text(normalized_body_text)
    if normalized_text:
        if subject_text and len(normalized_text.split()) < 8:
            return f"{subject_text}\n{normalized_text}", _normalized_text(normalized_body_source) or "subject_plus_body_text"
        return normalized_text, _normalized_text(normalized_body_source) or "body_text"

    raw_text = _normalized_text(raw_body_text)
    if raw_text:
        if subject_text and len(raw_text.split()) < 8:
            return f"{subject_text}\n{raw_text}", "subject_plus_raw_body_text"
        return raw_text, "raw_body_text"

    attachment_preview = _normalized_text(attachment_text)
    if subject_text and attachment_preview:
        return f"{subject_text}\n{attachment_preview}", "subject_plus_attachment_text"
    if subject_text:
        return subject_text, "subject"
    if attachment_preview:
        return attachment_preview, "attachment_text"

    return "", ""


def select_analytics_text_from_email(email: Any) -> tuple[str, str]:
    """Return the best available analytics text and its source for one parsed email."""
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
    """Return the best available analytics text and its source for one SQLite row."""
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
    """Return the best combined entity-extraction text and a source summary for one parsed email."""
    return _best_entity_text(
        subject=getattr(email, "subject", ""),
        forensic_body_text=getattr(email, "forensic_body_text", ""),
        normalized_body_text=getattr(email, "clean_body", ""),
        raw_body_text=getattr(email, "raw_body_text", ""),
        attachment_text=_attachment_text_from_attachments(getattr(email, "attachments", None)),
    )


def select_entity_text_from_row(row: Mapping[str, Any]) -> tuple[str, str]:
    """Return the best combined entity-extraction text and a source summary for one SQLite row."""
    return _best_entity_text(
        subject=_mapping_value(row, "subject"),
        forensic_body_text=_mapping_value(row, "forensic_body_text"),
        normalized_body_text=_mapping_value(row, "body_text"),
        raw_body_text=_mapping_value(row, "raw_body_text"),
        attachment_text=_mapping_value(row, "attachment_text"),
    )


def build_analytics_update_row(*, uid: str, text: str, source: str) -> tuple[Any, ...]:
    """Return one analytics update row for ``EmailDatabase.update_analytics_batch``."""
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
    """Return per-surface language analytics rows for one parsed email."""
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
    """Return per-surface language analytics rows for one SQLite row."""
    uid = str(_mapping_value(row, "uid") or "")
    if not uid:
        return []

    authored_segment_text = _normalized_text(_mapping_value(row, "authored_segment_text"))
    authored_segment_ordinal_raw = _mapping_value(row, "authored_segment_ordinal")
    try:
        authored_segment_ordinal = int(authored_segment_ordinal_raw) if authored_segment_ordinal_raw is not None else None
    except (TypeError, ValueError):
        authored_segment_ordinal = None

    authored_text = authored_segment_text or _normalized_text(
        _mapping_value(row, "forensic_body_text") or _mapping_value(row, "body_text") or _mapping_value(row, "raw_body_text")
    )

    quoted_segment_text = _normalized_text(_mapping_value(row, "quoted_segment_text"))
    quoted_segment_ordinal_raw = _mapping_value(row, "quoted_segment_ordinal")
    try:
        quoted_segment_ordinal = int(quoted_segment_ordinal_raw) if quoted_segment_ordinal_raw is not None else None
    except (TypeError, ValueError):
        quoted_segment_ordinal = None

    header_segment_text = _normalized_text(_mapping_value(row, "forwarded_header_text"))
    header_segment_ordinal_raw = _mapping_value(row, "forwarded_header_ordinal")
    try:
        header_segment_ordinal = int(header_segment_ordinal_raw) if header_segment_ordinal_raw is not None else None
    except (TypeError, ValueError):
        header_segment_ordinal = None

    segment_text = _normalized_text(_mapping_value(row, "segment_text"))
    segment_ordinal_raw = _mapping_value(row, "segment_ordinal")
    try:
        segment_ordinal = int(segment_ordinal_raw) if segment_ordinal_raw is not None else None
    except (TypeError, ValueError):
        segment_ordinal = None

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
