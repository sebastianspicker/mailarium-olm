"""Shared public identity fields for answer-context evidence candidates."""

from __future__ import annotations

from typing import Any


def candidate_summary(
    metadata: dict[str, Any],
    result: Any,
    *,
    rank: int,
    uid: str,
    snippet: str,
    match_reason: str,
) -> dict[str, Any]:
    """Project the common ranked email fields used by every evidence lane."""
    return {
        "rank": rank,
        "uid": uid,
        "subject": metadata.get("subject", ""),
        "sender_email": metadata.get("sender_email", ""),
        "sender_name": metadata.get("sender_name", ""),
        "date": metadata.get("date", ""),
        "conversation_id": metadata.get("conversation_id", ""),
        "score": result.score,
        "snippet": snippet,
        "match_reason": match_reason,
    }
