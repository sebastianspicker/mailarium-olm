"""Occurrence-level entity extraction helpers for ingest pipelines."""
# pylint: disable=too-many-locals

from __future__ import annotations

import re
from typing import Any

from .surface_candidates import attachment_surface_candidates as _attachment_surface_candidates
from .surface_candidates import clean_text as _clean_text
from .surface_candidates import segment_surface_candidates as _segment_surface_candidates


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
    """Expand extracted entities into provenance-aware occurrence rows."""
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
