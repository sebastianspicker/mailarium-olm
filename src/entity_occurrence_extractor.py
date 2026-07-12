"""Occurrence-level entity extraction helpers for ingest pipelines."""
# pylint: disable=too-many-locals

from __future__ import annotations

import re
from typing import Any


def _clean_text(value: Any) -> str:
    """Normalize and clean text by collapsing whitespace and stripping.

    Args:
        value: The value to clean, will be converted to string.

    Returns:
        The cleaned text with normalized whitespace.
    """
    return " ".join(str(value or "").split()).strip()


def _segment_surface_candidates(email: Any) -> list[tuple[str, str, int | None, str]]:
    """Extract text surface candidates from email segments.

    Args:
        email: An email object with segments attribute.

    Returns:
        A list of tuples containing (source_scope, surface_scope, ordinal, text)
        for each segment that contains text.
    """
    rows: list[tuple[str, str, int | None, str]] = []
    for index, segment in enumerate(getattr(email, "segments", None) or []):
        segment_type = str(getattr(segment, "segment_type", "") or "")
        text = _clean_text(getattr(segment, "text", ""))
        if not text:
            continue
        source_scope = {
            "authored_body": "authored_body",
            "quoted_reply": "quoted_body",
            "forwarded_message": "quoted_body",
            "header_block": "forwarded_header",
        }.get(segment_type, "segment_text")
        try:
            ordinal = int(getattr(segment, "ordinal", index))
        except (TypeError, ValueError):
            ordinal = index
        rows.append((source_scope, "message_segments", ordinal, text))
    return rows


def _attachment_surface_candidates(email: Any) -> list[tuple[str, str, int | None, str]]:
    """Extract text surface candidates from email attachments.

    Args:
        email: An email object with attachments attribute.

    Returns:
        A list of tuples containing (source_scope, surface_scope, ordinal, text)
        for each attachment that contains extractable text.
    """
    rows: list[tuple[str, str, int | None, str]] = []
    for index, attachment in enumerate(getattr(email, "attachments", None) or []):
        if not isinstance(attachment, dict):
            continue
        text = _clean_text(
            attachment.get("normalized_text") or attachment.get("extracted_text") or attachment.get("text_preview") or ""
        )
        if not text:
            continue
        rows.append(("attachment_text", "attachments", index, text))
    return rows


def _fallback_email_surface(email: Any) -> list[tuple[str, str, int | None, str]]:
    """Extract fallback text surface from email body fields.

    Args:
        email: An email object with body text fields.

    Returns:
        A list containing a single tuple with email body text if available,
        or an empty list if no body text is found.
    """
    text = _clean_text(
        getattr(email, "forensic_body_text", "") or getattr(email, "clean_body", "") or getattr(email, "raw_body_text", "")
    )
    if not text:
        return []
    return [("email_body", "email", None, text)]


def extract_entity_occurrence_rows_from_email(
    email: Any,
    entities: list[tuple[str, str, str]],
) -> list[tuple[object, ...]]:
    """Return occurrence rows as ``(text, type, norm, scope, surface, ordinal, start, end, snippet)``."""
    if not entities:
        return []
    surface_candidates = [*_segment_surface_candidates(email), *_attachment_surface_candidates(email)]
    if not surface_candidates:
        surface_candidates = _fallback_email_surface(email)
    rows: list[tuple[object, ...]] = []
    seen: set[tuple[str, str, str, int | None, int, int]] = set()
    for entity_text, entity_type, normalized_form in entities:
        term_candidates = [str(entity_text or "").strip(), str(normalized_form or "").strip()]
        terms = [term for term in term_candidates if term]
        if not terms:
            continue
        for source_scope, surface_scope, segment_ordinal, text in surface_candidates:
            if not text:
                continue
            for term in terms:
                rows.extend(
                    _occurrence_rows(
                        term, text, entity_text, entity_type, normalized_form, source_scope, surface_scope, segment_ordinal, seen
                    )
                )
    return rows


def _occurrence_rows(term, text, entity_text, entity_type, normalized, source_scope, surface_scope, ordinal, seen):
    rows = []
    for match in re.finditer(re.escape(term), text, flags=re.IGNORECASE):
        start, end = int(match.start()), int(match.end())
        key = (str(normalized or ""), source_scope, surface_scope, ordinal, start, end)
        if key not in seen:
            seen.add(key)
            rows.append(
                (
                    str(entity_text or ""),
                    str(entity_type or ""),
                    str(normalized or ""),
                    source_scope,
                    surface_scope,
                    ordinal,
                    start,
                    end,
                    _clean_text(match.group(0)),
                )
            )
    return rows
