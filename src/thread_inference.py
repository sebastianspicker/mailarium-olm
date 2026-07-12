"""Precision-first inferred parent/thread matching."""
# pylint: disable=too-many-branches,too-many-locals,too-many-statements

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .parse_olm import Email


@dataclass(frozen=True)
class InferredThreadMatch:
    parent_uid: str
    thread_id: str
    reason: str
    confidence: float


def _parse_dt(value: str) -> datetime | None:
    """Parse a date string into a timezone-naive UTC datetime."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _participant_set(email: Email) -> set[str]:
    """Extract the set of normalized participant email addresses from an email."""
    sender_email = getattr(email, "sender_email", "") or ""
    participants = {sender_email.lower()} if sender_email else set()
    for identities in (
        getattr(email, "to_identities", []),
        getattr(email, "cc_identities", []),
        getattr(email, "bcc_identities", []),
    ):
        for identity in identities:
            normalized = identity.strip().lower()
            if normalized:
                participants.add(normalized)
    return participants


def _reply_context_participants(email: Email) -> set[str]:
    """Extract the set of normalized participants from reply context (from/to)."""
    participants: set[str] = set()
    if getattr(email, "reply_context_from", ""):
        participants.add(email.reply_context_from.strip().lower())
    for identity in getattr(email, "reply_context_to", []):
        normalized = identity.strip().lower()
        if normalized:
            participants.add(normalized)
    return participants


def _snippet(text: str, limit: int = 120) -> str:
    """Create a normalized snippet of text limited to the specified character count."""
    return " ".join(text.lower().split())[:limit]


def _score_candidate(email: Email, candidate: Email) -> tuple[float, list[str]]:
    """Score a candidate parent email against a child email, returning score and reasons."""
    date_signal = _date_signal(email, candidate)
    if date_signal is None:
        return 0.0, []
    signals = [
        date_signal,
        _subject_signal(email, candidate),
        _participant_signal(email, candidate),
        _snippet_signal(email, candidate),
    ]
    return sum(score for score, _ in signals), [reason for _, reasons in signals for reason in reasons]


def _date_signal(email: Email, candidate: Email) -> tuple[float, list[str]] | None:
    child = _parse_dt(getattr(email, "date", "") or "")
    parent = _parse_dt(getattr(candidate, "date", "") or "")
    if not child or not parent:
        return 0.0, []
    if parent >= child:
        return None
    hours = (child - parent).total_seconds() / 3600
    if hours <= 72:
        return 0.10, ["recent_date"]
    return (0.05, ["date_window"]) if hours <= 24 * 30 else None


def _subject_signal(email: Email, candidate: Email) -> tuple[float, list[str]]:
    child_base = getattr(email, "base_subject", "") or ""
    parent_base = getattr(candidate, "base_subject", "") or ""
    context = getattr(email, "reply_context_subject", "").strip()
    parent_subject = getattr(candidate, "subject", "") or ""
    score, reasons = (0.30, ["base_subject"]) if child_base and parent_base and child_base == parent_base else (0.0, [])
    if context and context == parent_subject:
        return score + 0.20, [*reasons, "reply_context_subject"]
    if context and context == parent_base:
        return score + 0.15, [*reasons, "reply_context_base_subject"]
    return score, reasons


def _participant_signal(email: Email, candidate: Email) -> tuple[float, list[str]]:
    context_from = getattr(email, "reply_context_from", "").strip().lower()
    parent_sender = getattr(candidate, "sender_email", "") or ""
    context_to = _reply_context_participants(email)
    parent_participants = _participant_set(candidate)
    child_participants = _participant_set(email)
    child_sender = getattr(email, "sender_email", "") or ""
    checks = (
        (context_from and parent_sender and context_from == parent_sender.lower(), 0.25, "reply_context_from"),
        (context_to and bool(context_to & parent_participants), 0.10, "reply_context_to"),
        (child_sender and child_sender.lower() in parent_participants, 0.12, "sender_in_parent_participants"),
        (parent_sender and parent_sender.lower() in child_participants, 0.12, "parent_sender_in_child_participants"),
    )
    return sum(weight for matched, weight, _ in checks if matched), [reason for matched, _, reason in checks if matched]


def _snippet_signal(email: Email, candidate: Email) -> tuple[float, list[str]]:
    child = _snippet(getattr(email, "clean_body", "") or "")
    parent = _snippet(getattr(candidate, "clean_body", "") or "")
    matched = bool(child and parent and child[:40] and child[:40] in parent)
    return (0.08, ["snippet_overlap"]) if matched else (0.0, [])


def infer_parent_candidate(email: Email, candidate_messages: list[Email]) -> InferredThreadMatch | None:
    """Infer a likely parent without mutating canonical thread fields."""
    if getattr(email, "in_reply_to", "") or getattr(email, "references", []):
        return None
    if getattr(email, "email_type", "original") == "original":
        return None

    scored = _scored_parent_candidates(email, candidate_messages)

    if not scored:
        return None

    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_reasons, best = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0

    if best_score < 0.80:
        return None
    if second_score and best_score - second_score < 0.15:
        return None

    thread_id = getattr(best, "conversation_id", "") or getattr(best, "thread_topic", "") or getattr(best, "uid", "")
    return InferredThreadMatch(
        parent_uid=getattr(best, "uid", ""),
        thread_id=thread_id,
        reason=",".join(best_reasons),
        confidence=round(min(best_score, 1.0), 3),
    )


def _scored_parent_candidates(email: Email, candidates: list[Email]) -> list[tuple[float, list[str], Email]]:
    scored = []
    for candidate in candidates:
        if getattr(candidate, "uid", "") != getattr(email, "uid", ""):
            score, reasons = _score_candidate(email, candidate)
            if score > 0:
                scored.append((score, reasons, candidate))
    return scored
