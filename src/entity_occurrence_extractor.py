"""Occurrence-level entity extraction helpers for ingest pipelines."""

from __future__ import annotations

import re
from typing import Any


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _segment_surface_candidates(email: Any) -> list[tuple[str, str, int | None, str]]:
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
                for match in re.finditer(re.escape(term), text, flags=re.IGNORECASE):
                    char_start = int(match.start())
                    char_end = int(match.end())
                    key = (str(normalized_form or ""), source_scope, surface_scope, segment_ordinal, char_start, char_end)
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(
                        (
                            str(entity_text or ""),
                            str(entity_type or ""),
                            str(normalized_form or ""),
                            source_scope,
                            surface_scope,
                            segment_ordinal,
                            char_start,
                            char_end,
                            _clean_text(match.group(0)),
                        )
                    )
    return rows
