"""Authored and quoted speaker attribution with explicit ambiguity state."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from mailarium.model.data_shapes import as_dict
from mailarium.model.reply_context import extract_reply_context

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase


_EMAIL_CANDIDATE_RE = re.compile(r"(?i)(?:mailto:)?([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})")
_FROM_HEADER_RE = re.compile(r"(?im)^from:\s*(.+)$")


def _segment_rows_for_uid(db: ArchiveDatabase | None, uid: str) -> list[dict[str, Any]]:
    """Return persisted conversation segments for one email, if available."""
    if db is None or not uid:
        return []
    return db.queries.message_segments_for_email(uid)


def _normalize_attributed_email(value: str) -> str:
    """Return a best-effort normalized email address for attribution output."""
    normalized = value.strip().lower()
    if not normalized:
        return ""
    match = _EMAIL_CANDIDATE_RE.search(normalized)
    if match:
        return match.group(1).lower()
    return normalized


def _quoted_block_candidates(segment_text: str, authored_email: str) -> list[str]:
    """Return unique non-authored email candidates visible in one quoted block."""
    candidates: list[str] = []
    for match in _EMAIL_CANDIDATE_RE.finditer(segment_text or ""):
        email = _normalize_attributed_email(match.group(0))
        if not email or email == authored_email:
            continue
        if email not in candidates:
            candidates.append(email)
    return candidates


def _quoted_from_header_candidate(segment_text: str, authored_email: str) -> str:
    """Return one quoted speaker email from a visible ``From:`` header, if unambiguous."""
    match = _FROM_HEADER_RE.search(segment_text or "")
    if not match:
        return ""
    candidates = _quoted_block_candidates(match.group(1), authored_email)
    if len(candidates) == 1:
        return candidates[0]
    return ""


def _reply_context_identities(full_email: dict[str, Any] | None, authored_email: str) -> tuple[str, list[str]]:
    """Return normalized reply-context identities excluding the authored speaker."""
    normalized_authored_email = authored_email.strip().lower()
    reply_context_from = _normalize_attributed_email(str((full_email or {}).get("reply_context_from") or ""))
    reply_context_to = [
        _normalize_attributed_email(identity) for identity in ((full_email or {}).get("reply_context_to") or []) if identity
    ]
    identities = [
        identity for identity in [reply_context_from, *reply_context_to] if identity and identity != normalized_authored_email
    ]
    return reply_context_from, list(dict.fromkeys(identities))


def _quoted_reply_context_identities(segment_text: str, authored_email: str) -> list[str]:
    """Return unique quoted reply-context identities visible in one segment."""
    normalized_authored_email = authored_email.strip().lower()
    quoted_reply_context = extract_reply_context(segment_text, "", "reply")
    if not quoted_reply_context or not quoted_reply_context.from_email:
        return []
    quoted_from = _normalize_attributed_email(quoted_reply_context.from_email)
    quoted_to = [_normalize_attributed_email(identity) for identity in quoted_reply_context.to_emails]
    reply_context_identities = [
        identity for identity in [quoted_from, *quoted_to] if identity and identity != normalized_authored_email
    ]
    return list(dict.fromkeys(reply_context_identities))


def _quote_attribution_details(
    *,
    full_email: dict[str, Any] | None,
    authored_email: str,
    conversation_context: dict[str, Any] | None,
    segment_text: str = "",
) -> dict[str, Any]:
    """Return one normalized quote-attribution decision with explicit ambiguity state."""
    normalized_authored_email = authored_email.strip().lower()
    quoted_from_header = _quoted_from_header_candidate(segment_text, normalized_authored_email)
    quoted_reply_context_identities = _quoted_reply_context_identities(segment_text, normalized_authored_email)
    quoted_block_emails = _quoted_block_candidates(segment_text, normalized_authored_email)
    reply_context_from, reply_context_identities = _reply_context_identities(full_email, normalized_authored_email)

    if quoted_from_header:
        return _attribution_decision(quoted_from_header, "quoted_from_header", 0.85, "explicit_header")
    if len(quoted_reply_context_identities) == 1:
        return _quoted_reply_context_decision(quoted_reply_context_identities[0], reply_context_from)
    if len(quoted_block_emails) == 1:
        return _quoted_block_decision(quoted_block_emails[0], reply_context_from)
    if reply_context_from and not quoted_block_emails and not quoted_reply_context_identities:
        return _attribution_decision(
            reply_context_from,
            "reply_context_from",
            0.8,
            "reply_context_fallback",
            "Quoted ownership is inferred from the visible reply context because "
            "the quoted block has no explicit identity markers.",
            downgraded=True,
        )
    unique_alternatives = _conversation_alternatives(conversation_context, normalized_authored_email)
    if len(unique_alternatives) == 1:
        return _attribution_decision(
            unique_alternatives[0],
            "conversation_participant_exclusion",
            0.5,
            "participant_exclusion",
            "Quoted ownership is inferred only from the remaining conversation participants, so it should be read cautiously.",
            downgraded=True,
        )
    return _attribution_decision(
        "",
        "unresolved",
        0.0,
        "unresolved",
        "Quoted ownership remains unresolved because the visible reply chain includes multiple plausible speakers.",
        candidates=list(dict.fromkeys([*quoted_block_emails, *reply_context_identities])),
        downgraded=True,
    )


def _attribution_decision(
    speaker_email: str,
    source: str,
    confidence: float,
    status: str,
    reason: str = "",
    *,
    candidates: list[str] | None = None,
    downgraded: bool = False,
) -> dict[str, Any]:
    """Package speaker identity, provenance, confidence, downgrade state, and alternatives consistently."""
    return {
        "speaker_email": speaker_email,
        "source": source,
        "confidence": confidence,
        "quote_attribution_status": status,
        "quote_attribution_reason": reason,
        "candidate_emails": candidates if candidates is not None else [speaker_email],
        "downgraded_due_to_quote_ambiguity": downgraded,
    }


def _quoted_reply_context_decision(speaker_email: str, reply_context_from: str) -> dict[str, Any]:
    """Assign high-confidence quoted ownership when reply-context identity corroborates the speaker."""
    corroborated = bool(reply_context_from and reply_context_from == speaker_email)
    return _attribution_decision(
        speaker_email,
        "reply_context_from_corroborated" if corroborated else "quoted_block_reply_context",
        0.8 if corroborated else 0.72,
        "corroborated_reply_context",
    )


def _quoted_block_decision(speaker_email: str, reply_context_from: str) -> dict[str, Any]:
    """Calibrate quoted-block ownership lower unless reply context corroborates the sole candidate."""
    corroborated = bool(reply_context_from and reply_context_from == speaker_email)
    return _attribution_decision(
        speaker_email,
        "reply_context_from_corroborated" if corroborated else "quoted_block_email",
        0.78 if corroborated else 0.6,
        "corroborated_reply_context" if corroborated else "inferred_single_candidate",
        "" if corroborated else "Only one non-authored identity is visible in the quoted block, so ownership remains inferred.",
        downgraded=not corroborated,
    )


def _conversation_alternatives(conversation_context: dict[str, Any] | None, authored_email: str) -> list[str]:
    """Return unique normalized participants other than the message author as attribution alternatives."""
    participants = as_dict(conversation_context).get("participants", [])
    alternatives = [
        str(participant).strip().lower() for participant in participants if participant and participant != authored_email
    ]
    return list(dict.fromkeys(alternatives))


def _speaker_attribution_for_candidate(
    db: ArchiveDatabase | None,
    *,
    uid: str,
    conversation_id: str,
    sender_email: str,
    sender_name: str,
    conversation_context: dict[str, Any] | None,
    full_email: dict[str, Any] | None,
    segments: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Build authored vs quoted speaker hints for one candidate."""
    if segments is None:
        segments = _segment_rows_for_uid(db, uid)
    if not segments:
        return None
    authored_email, authored_name = _canonical_sender_for_candidate(
        db, conversation_id, uid, sender_email, sender_name, full_email=full_email
    )
    return {
        "authored_speaker": {
            "email": authored_email,
            "name": authored_name,
            "source": "canonical_sender",
            "confidence": 1.0,
        },
        "quoted_blocks": _quoted_speaker_blocks(segments, full_email, sender_email, conversation_context),
    }


def _quoted_speaker_blocks(
    segments: list[dict[str, Any]],
    full_email: dict[str, Any] | None,
    sender_email: str,
    conversation_context: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Extract only quoted-reply and forwarded-message segments for speaker attribution."""
    quoted_blocks: list[dict[str, Any]] = []
    for segment in segments:
        segment_type = str(segment.get("segment_type") or "")
        if segment_type not in {"quoted_reply", "forwarded_message"}:
            continue
        quoted_blocks.append(_quoted_speaker_block(segment, segment_type, full_email, sender_email, conversation_context))
    return quoted_blocks


def _quoted_speaker_block(
    segment: dict[str, Any],
    segment_type: str,
    full_email: dict[str, Any] | None,
    sender_email: str,
    conversation_context: dict[str, Any] | None,
) -> dict[str, Any]:
    """Combine segment location and calibrated quote attribution into one public speaker block."""
    quote_attribution = _quote_attribution_details(
        full_email=full_email,
        authored_email=sender_email,
        conversation_context=conversation_context,
        segment_text=str(segment.get("text") or ""),
    )
    return {
        "segment_ordinal": int(segment.get("ordinal") or 0),
        "segment_type": segment_type,
        "speaker_email": str(quote_attribution.get("speaker_email") or ""),
        "source": str(quote_attribution.get("source") or ""),
        "confidence": float(quote_attribution.get("confidence") or 0.0),
        "quote_attribution_status": str(quote_attribution.get("quote_attribution_status") or ""),
        "quote_attribution_reason": str(quote_attribution.get("quote_attribution_reason") or ""),
        "candidate_emails": list(quote_attribution.get("candidate_emails") or []),
        "downgraded_due_to_quote_ambiguity": bool(quote_attribution.get("downgraded_due_to_quote_ambiguity", True)),
        "text": str(segment.get("text") or ""),
    }


def _canonical_sender_for_candidate(
    db: ArchiveDatabase | None,
    conversation_id: str,
    uid: str,
    sender_email: str,
    sender_name: str,
    *,
    full_email: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Recover the stored author identity from the canonical thread row when available."""
    authored_email = sender_email
    authored_name = sender_name
    if full_email:
        return (
            str(full_email.get("sender_email") or authored_email),
            str(full_email.get("sender_name") or authored_name),
        )
    if db and conversation_id:
        thread_emails = db.queries.get_thread_emails(conversation_id) or []
        for email in thread_emails:
            if str(email.get("uid") or "") != uid:
                continue
            authored_email = str(email.get("sender_email") or authored_email)
            authored_name = str(email.get("sender_name") or authored_name)
            break
    return authored_email, authored_name
