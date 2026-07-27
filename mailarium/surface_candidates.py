"""Shared provenance-aware text-surface selection for extractors."""

from __future__ import annotations

from typing import Any


def clean_text(value: Any) -> str:
    """Collapse whitespace and coerce an optional surface value to text."""
    return " ".join(str(value or "").split()).strip()


def segment_surface_candidates(email: Any) -> list[tuple[str, str, int | None, str]]:
    """Return non-empty message segments with stable provenance ordinals."""
    candidates: list[tuple[str, str, int | None, str]] = []
    for index, segment in enumerate(getattr(email, "segments", None) or []):
        segment_type = str(getattr(segment, "segment_type", "") or "")
        text = clean_text(getattr(segment, "text", ""))
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
        except TypeError, ValueError:
            ordinal = index
        candidates.append((source_scope, "message_segments", ordinal, text))
    return candidates


def attachment_surface_candidates(email: Any) -> list[tuple[str, str, int | None, str]]:
    """Return non-empty extracted attachment text with stable ordinals."""
    candidates: list[tuple[str, str, int | None, str]] = []
    for index, attachment in enumerate(getattr(email, "attachments", None) or []):
        if not isinstance(attachment, dict):
            continue
        text = clean_text(
            attachment.get("normalized_text") or attachment.get("extracted_text") or attachment.get("text_preview") or ""
        )
        if text:
            candidates.append(("attachment_text", "attachments", index, text))
    return candidates
