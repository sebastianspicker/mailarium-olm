"""Budget-constrained answer-context payload helpers."""

from __future__ import annotations

from typing import Any


def _trim_snippet_for_budget(text: Any, *, max_chars: int) -> str:
    """Collapse and trim a snippet to a fixed character budget."""
    collapsed = " ".join(str(text or "").split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 3].rstrip() + "..."


def _trim_provenance_for_budget(provenance: Any) -> dict[str, Any]:
    """Retain only fields required to cite a compacted excerpt."""
    if not isinstance(provenance, dict):
        return {}
    return {
        "evidence_handle": provenance.get("evidence_handle"),
        "visible_excerpt_start": provenance.get("visible_excerpt_start"),
        "visible_excerpt_end": provenance.get("visible_excerpt_end"),
        "visible_excerpt_compacted": provenance.get("visible_excerpt_compacted"),
    }


def _trim_candidate_for_budget(item: Any) -> dict[str, Any]:
    """Create a compact representation of one evidence candidate."""
    if not isinstance(item, dict):
        return {}
    trimmed = {
        "rank": item.get("rank"),
        "uid": item.get("uid"),
        "subject": item.get("subject"),
        "sender_email": item.get("sender_email"),
        "date": item.get("date"),
        "score": item.get("score"),
        "snippet": _trim_snippet_for_budget(item.get("snippet"), max_chars=120),
        "provenance": _trim_provenance_for_budget(item.get("provenance")),
    }
    attachment = item.get("attachment")
    if isinstance(attachment, dict):
        trimmed["attachment"] = {
            "filename": attachment.get("filename"),
            "evidence_strength": attachment.get("evidence_strength"),
            "text_available": attachment.get("text_available"),
        }
    return trimmed


__all__ = ["_trim_candidate_for_budget", "_trim_provenance_for_budget", "_trim_snippet_for_budget"]
