# mypy: disable-error-code=name-defined
# pylint: disable=E0602  # cross-module names injected by compatibility facade
"""Split helpers for search answer-context runtime (search_answer_context_runtime_budgeting)."""

from __future__ import annotations

from typing import Any

from .search_answer_context_case_payloads import (
    _compact_language_rhetoric_payload,
    _compact_message_findings_payload,
)


def _trim_snippet_for_budget(text: Any, *, max_chars: int) -> str:
    """Trim a text snippet to fit within a character budget.

    Collapses whitespace and truncates the text to max_chars, appending ellipsis
    if truncation occurs.

    Args:
        text: The text to trim.
        max_chars: Maximum number of characters allowed in the output.

    Returns:
        The trimmed text with ellipsis if truncated.
    """
    collapsed = " ".join(str(text or "").split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 3].rstrip() + "..."


def _trim_provenance_for_budget(provenance: Any) -> dict[str, Any]:
    """Extract essential provenance fields for budget-constrained serialization.

    Returns a compact dictionary containing only the most critical provenance
    fields needed for evidence citation.

    Args:
        provenance: The provenance dictionary to trim.

    Returns:
        A dictionary with only evidence_handle, visible_excerpt_start,
        visible_excerpt_end, and visible_excerpt_compacted fields.
    """
    if not isinstance(provenance, dict):
        return {}
    return {
        "evidence_handle": provenance.get("evidence_handle"),
        "visible_excerpt_start": provenance.get("visible_excerpt_start"),
        "visible_excerpt_end": provenance.get("visible_excerpt_end"),
        "visible_excerpt_compacted": provenance.get("visible_excerpt_compacted"),
    }


def _trim_candidate_for_budget(item: Any) -> dict[str, Any]:
    """Create a budget-constrained compact representation of a candidate item.

    Extracts essential fields from a candidate evidence item, trimming text
    fields and nested structures to reduce memory and serialization overhead.

    Args:
        item: The candidate item dictionary to compact.

    Returns:
        A dictionary with only the most essential fields for evidence
        representation, with snippets trimmed and nested structures compacted.
    """
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
    if isinstance(item.get("language_rhetoric"), dict):
        trimmed["language_rhetoric"] = _compact_language_rhetoric_payload(item.get("language_rhetoric"))
    if isinstance(item.get("message_findings"), dict):
        trimmed["message_findings"] = _compact_message_findings_payload(item.get("message_findings"))
    reply_pairing = item.get("reply_pairing")
    if isinstance(reply_pairing, dict):
        trimmed["reply_pairing"] = {
            "response_status": reply_pairing.get("response_status"),
            "supports_selective_non_response_inference": reply_pairing.get("supports_selective_non_response_inference"),
        }
    return trimmed


__all__ = [
    "_trim_candidate_for_budget",
    "_trim_provenance_for_budget",
    "_trim_snippet_for_budget",
]
