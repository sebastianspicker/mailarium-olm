"""Conservative reply-pairing helpers for workplace case analysis."""
# pylint: disable=too-many-branches,too-many-locals,too-many-statements

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

_EMAIL_RE = re.compile(r"(?i)(?:mailto:)?([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})")
_REQUEST_RE = re.compile(
    r"(?i)\b(?:please|can you|could you|would you|kindly|bitte|kannst du|koennen sie|können sie|"
    r"koennten sie|könnten sie|send|confirm|share|provide|reply|respond|acknowledge|bestätigen|bestaetigen)\b"
)
_QUESTION_RE = re.compile(r"\?")
_SUBJECT_PREFIX_RE = re.compile(r"(?i)^(?:re|fw|fwd|aw)\s*:\s*")
_FORMAT_LIMITED_RE = re.compile(r"(?im)(?:^on .+ wrote:$|^am .+ schrieb.*:$|^-+\s*original message\s*-+$)")
_REPLY_DELAY_HOURS = 48.0


def _parse_iso_like(value: str) -> datetime | None:
    """Parse an ISO-like datetime string into a datetime object.

    Handles various ISO 8601 formats including Z suffix for UTC.

    Args:
        value: The datetime string to parse.

    Returns:
        Parsed datetime object with timezone info removed, or None if parsing fails.
    """
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _extract_emails(values: list[Any]) -> list[str]:
    """Extract unique email addresses from a list of values.

    Uses regex to find email addresses in string representations of values.

    Args:
        values: List of values to search for email addresses.

    Returns:
        List of unique lowercase email addresses found.
    """
    emails: list[str] = []
    for value in values:
        for match in _EMAIL_RE.finditer(str(value or "")):
            email = match.group(1).lower()
            if email not in emails:
                emails.append(email)
    return emails


def _normalized_subject(value: str) -> str:
    """Normalize an email subject by removing common prefixes and extra whitespace.

    Removes Re:, Fw:, Fwd:, Aw: prefixes (case-insensitive) and collapses
    multiple whitespace characters.

    Args:
        value: The subject string to normalize.

    Returns:
        Normalized lowercase subject string.
    """
    subject = str(value or "").strip().lower()
    while True:
        updated = _SUBJECT_PREFIX_RE.sub("", subject)
        if updated == subject:
            break
        subject = updated
    return re.sub(r"\s+", " ", subject).strip()


def _best_text(candidate: dict[str, Any], full_email: dict[str, Any] | None) -> str:
    """Extract the best available text from a candidate or full email.

    Tries multiple sources in order of preference: candidate snippet,
    full email body_text, full email normalized_body_text.

    Args:
        candidate: The candidate dictionary with potential snippet.
        full_email: Optional full email dictionary with body text fields.

    Returns:
        The first non-empty text found, or empty string.
    """
    for source in (
        str(candidate.get("snippet") or ""),
        str((full_email or {}).get("body_text") or ""),
        str((full_email or {}).get("normalized_body_text") or ""),
    ):
        if source.strip():
            return source
    return ""


def _request_expected(text: str) -> tuple[bool, list[str], str, float, bool]:
    """Determine if a text contains a reply request and classify the detection.

    Checks for request wording patterns and question marks to identify
    if a reply is expected from the text.

    Args:
        text: The text to analyze.

    Returns:
        Tuple containing:
            - bool: True if a request is expected
            - list[str]: List of detection reason strings
            - str: Detection status ('detected', 'format_limited', 'no_clear_request')
            - float: Detection confidence score (0.0-1.0)
            - bool: True if format is limited (quoted reply wrapper)
    """
    reasons: list[str] = []
    if _REQUEST_RE.search(text):
        reasons.append("request_wording")
    if _QUESTION_RE.search(text):
        reasons.append("question_mark")
    if reasons:
        confidence = 0.95 if len(reasons) > 1 else 0.8
        return True, reasons, "detected", confidence, False
    if _FORMAT_LIMITED_RE.search(text):
        return False, ["quoted_reply_wrapper_without_clear_request"], "format_limited", 0.25, True
    return False, reasons, "no_clear_request", 0.2, False


def _thread_key(candidate: dict[str, Any], full_email: dict[str, Any] | None) -> str:
    """Extract a thread identifier from a candidate or full email.

    Tries multiple fields in order: thread_group_id, conversation_id from
    candidate, then conversation_id from full email.

    Args:
        candidate: The candidate dictionary.
        full_email: Optional full email dictionary.

    Returns:
        The first non-empty thread identifier found, or empty string.
    """
    for value in (
        str(candidate.get("thread_group_id") or ""),
        str(candidate.get("conversation_id") or ""),
        str((full_email or {}).get("conversation_id") or ""),
    ):
        if value:
            return value
    return ""


def _row_for_candidate(
    candidate: dict[str, Any],
    full_email: dict[str, Any] | None,
) -> dict[str, Any]:
    """Create a normalized row dictionary from a candidate and optional full email.

    Extracts and normalizes key fields for reply-pairing analysis.

    Args:
        candidate: The candidate dictionary with email metadata.
        full_email: Optional full email dictionary with additional fields.

    Returns:
        Dictionary containing normalized fields:
            - uid: Unique identifier
            - date: Date string
            - parsed_date: Parsed datetime object
            - sender_email: Normalized sender email
            - subject: Subject string
            - normalized_subject: Normalized subject
            - conversation_id: Conversation identifier
            - thread_key: Thread identifier
            - recipients: List of recipient emails
            - text: Best available text content
    """
    full_email = full_email or {}
    recipients = _extract_emails(
        [*list(full_email.get("to") or []), *list(full_email.get("cc") or []), *list(full_email.get("bcc") or [])]
    )
    uid = _string_value(candidate, "uid")
    date = _string_value(candidate, "date")
    sender_email = _string_value(candidate, "sender_email").lower()
    subject = _string_value(candidate, "subject")
    conversation_id = _string_value(candidate, "conversation_id") or _string_value(full_email, "conversation_id")
    return {
        "uid": uid,
        "date": date,
        "parsed_date": _parse_iso_like(date),
        "sender_email": sender_email,
        "subject": subject,
        "normalized_subject": _normalized_subject(subject),
        "conversation_id": conversation_id,
        "thread_key": _thread_key(candidate, full_email),
        "recipients": recipients,
        "text": _best_text(candidate, full_email),
    }


def _string_value(mapping, key):
    return str(mapping.get(key) or "")


def build_reply_pairing_index(
    *,
    candidates: list[dict[str, Any]],
    full_map: dict[str, Any],
    case_scope: Any,
) -> dict[str, dict[str, Any]]:
    """Return conservative reply-pairing metadata for target-authored requests."""
    target_email = _actor_email(getattr(case_scope, "target_person", None))
    suspected_actor_emails = _actor_emails(getattr(case_scope, "suspected_actors", []))
    rows = _candidate_rows(candidates, full_map)
    rows = [row for row in rows if row["uid"]]
    rows.sort(key=lambda row: (row["parsed_date"] or datetime.max, row["uid"]))

    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        summary = _pairing_summary(row, target_email, suspected_actor_emails)
        index[row["uid"]] = summary
        if _pair_request(row, rows, summary, target_email):
            continue
    return index


def _actor_email(actor):
    return str(getattr(actor, "email", "") or "").strip().lower()


def _actor_emails(actors):
    return {email for actor in list(actors or []) if (email := _actor_email(actor))}


def _candidate_rows(candidates, full_map):
    full_map = full_map if isinstance(full_map, dict) else {}
    return [_row_for_candidate(candidate, full_map.get(_string_value(candidate, "uid"))) for candidate in candidates]


def _pairing_summary(row, target_email, suspected_actor_emails):
    request_expected, request_reasons, detection_status, detection_confidence, format_limited = _request_expected(row["text"])
    target_authored_request = bool(target_email and row["sender_email"] == target_email)
    relevant_actor_emails = _relevant_actor_emails(row["recipients"], suspected_actor_emails, target_email)
    return {
        "request_expected": request_expected,
        "request_detection_reasons": request_reasons,
        "request_detection_status": detection_status,
        "request_detection_confidence": detection_confidence,
        "format_limited": format_limited,
        "target_authored_request": target_authored_request,
        "relevant_actor_emails": relevant_actor_emails,
        "response_status": "not_applicable",
        "direct_reply_uid": "",
        "direct_reply_sender_email": "",
        "response_delay_hours": None,
        "later_activity_uids": [],
        "later_activity_by_relevant_actor": False,
        "supports_selective_non_response_inference": False,
        "counter_indicators": [],
    }


def _relevant_actor_emails(recipients, suspected_actor_emails, target_email):
    if suspected_actor_emails:
        return [email for email in recipients if email in suspected_actor_emails]
    return [email for email in recipients if email and email != target_email]


def _pair_request(row, rows, summary, target_email):
    if not summary["request_expected"]:
        message = (
            "Quoted-wrapper formatting is visible, but the visible text does not expose a bounded reply request."
            if summary["format_limited"]
            else "The message did not contain a bounded reply-expected cue."
        )
        summary["counter_indicators"].append(message)
        return True
    if not summary["target_authored_request"]:
        summary["counter_indicators"].append("Selective non-response checks are limited to target-authored requests.")
        return True
    if not summary["relevant_actor_emails"]:
        summary["counter_indicators"].append("No relevant recipient actor was visible for reply-pairing checks.")
        return True

    later_rows = _later_rows(row, rows, summary["relevant_actor_emails"])

    summary["later_activity_uids"] = [later["uid"] for later in later_rows]
    summary["later_activity_by_relevant_actor"] = bool(later_rows)
    direct_reply = next((later for later in later_rows if target_email in later["recipients"]), None)
    if direct_reply is not None:
        _record_direct_reply(summary, row, direct_reply)
    elif later_rows:
        summary["response_status"] = "indirect_activity_without_direct_reply"
        summary["supports_selective_non_response_inference"] = True
    else:
        summary["response_status"] = "no_reply_observed"
        summary["counter_indicators"].append(
            "No later activity from a relevant actor is visible in the current evidence set, "
            "so non-response remains context-limited."
        )
    return True


def _later_rows(row, rows, relevant_actor_emails):
    return [later for later in rows if _is_later_related_activity(row, later, relevant_actor_emails)]


def _is_later_related_activity(row, later, relevant_actor_emails):
    if later["uid"] == row["uid"] or row["parsed_date"] is None or later["parsed_date"] is None:
        return False
    if later["parsed_date"] <= row["parsed_date"] or later["sender_email"] not in relevant_actor_emails:
        return False
    same_thread = bool(row["thread_key"] and later["thread_key"] and row["thread_key"] == later["thread_key"])
    same_subject = bool(row["normalized_subject"] and row["normalized_subject"] == later["normalized_subject"])
    return same_thread or same_subject


def _record_direct_reply(summary, row, direct_reply):
    delay_hours = round((direct_reply["parsed_date"] - row["parsed_date"]).total_seconds() / 3600, 2)
    summary["direct_reply_uid"] = direct_reply["uid"]
    summary["direct_reply_sender_email"] = direct_reply["sender_email"]
    summary["response_delay_hours"] = delay_hours
    summary["response_status"] = "delayed_reply" if delay_hours > _REPLY_DELAY_HOURS else "direct_reply"
    summary["counter_indicators"].append("A direct reply from a relevant actor is visible in the current evidence set.")
