"""Precision-first inferred parent/thread matching."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            return parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None


def _participant_set(email: Email) -> set[str]:
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
    participants: set[str] = set()
    if getattr(email, "reply_context_from", ""):
        participants.add(email.reply_context_from.strip().lower())
    for identity in getattr(email, "reply_context_to", []):
        normalized = identity.strip().lower()
        if normalized:
            participants.add(normalized)
    return participants


def _snippet(text: str, limit: int = 120) -> str:
    return " ".join(text.lower().split())[:limit]


def _score_candidate(email: Email, candidate: Email) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0

    child_dt = _parse_dt(getattr(email, "date", "") or "")
    parent_dt = _parse_dt(getattr(candidate, "date", "") or "")
    if child_dt and parent_dt:
        if parent_dt >= child_dt:
            return 0.0, []
        delta_hours = (child_dt - parent_dt).total_seconds() / 3600
        if delta_hours <= 72:
            score += 0.10
            reasons.append("recent_date")
        elif delta_hours <= 24 * 30:
            score += 0.05
            reasons.append("date_window")
        else:
            return 0.0, []

    email_base_subject = getattr(email, "base_subject", "") or ""
    candidate_base_subject = getattr(candidate, "base_subject", "") or ""
    if email_base_subject and candidate_base_subject and email_base_subject == candidate_base_subject:
        score += 0.30
        reasons.append("base_subject")

    reply_context_subject = getattr(email, "reply_context_subject", "").strip()
    candidate_subject = getattr(candidate, "subject", "") or ""
    if reply_context_subject and reply_context_subject == candidate_subject:
        score += 0.20
        reasons.append("reply_context_subject")
    elif reply_context_subject and reply_context_subject == candidate_base_subject:
        score += 0.15
        reasons.append("reply_context_base_subject")

    reply_context_from = getattr(email, "reply_context_from", "").strip().lower()
    candidate_sender_email = getattr(candidate, "sender_email", "") or ""
    if reply_context_from and candidate_sender_email and reply_context_from == candidate_sender_email.lower():
        score += 0.25
        reasons.append("reply_context_from")

    reply_context_to = _reply_context_participants(email)
    candidate_participants = _participant_set(candidate)
    if reply_context_to and reply_context_to & candidate_participants:
        score += 0.10
        reasons.append("reply_context_to")

    child_participants = _participant_set(email)
    email_sender_email = getattr(email, "sender_email", "") or ""
    if email_sender_email and email_sender_email.lower() in candidate_participants:
        score += 0.12
        reasons.append("sender_in_parent_participants")
    if candidate_sender_email and candidate_sender_email.lower() in child_participants:
        score += 0.12
        reasons.append("parent_sender_in_child_participants")

    child_snippet = _snippet(getattr(email, "clean_body", "") or "")
    parent_snippet = _snippet(getattr(candidate, "clean_body", "") or "")
    if child_snippet and parent_snippet and child_snippet[:40] and child_snippet[:40] in parent_snippet:
        score += 0.08
        reasons.append("snippet_overlap")

    return score, reasons


def infer_parent_candidate(email: Email, candidate_messages: list[Email]) -> InferredThreadMatch | None:
    """Infer a likely parent without mutating canonical thread fields."""
    if getattr(email, "in_reply_to", "") or getattr(email, "references", []):
        return None
    if getattr(email, "email_type", "original") == "original":
        return None

    scored: list[tuple[float, list[str], Email]] = []
    for candidate in candidate_messages:
        if getattr(candidate, "uid", "") == getattr(email, "uid", ""):
            continue
        score, reasons = _score_candidate(email, candidate)
        if score > 0:
            scored.append((score, reasons, candidate))

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
