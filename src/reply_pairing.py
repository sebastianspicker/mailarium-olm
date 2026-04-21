"""Conservative reply-pairing helpers for workplace case analysis."""

from __future__ import annotations

import re
from datetime import datetime
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
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _extract_emails(values: list[Any]) -> list[str]:
    emails: list[str] = []
    for value in values:
        match = _EMAIL_RE.search(str(value or ""))
        if not match:
            continue
        email = match.group(1).lower()
        if email not in emails:
            emails.append(email)
    return emails


def _normalized_subject(value: str) -> str:
    subject = str(value or "").strip().lower()
    while True:
        updated = _SUBJECT_PREFIX_RE.sub("", subject)
        if updated == subject:
            break
        subject = updated
    return re.sub(r"\s+", " ", subject).strip()


def _best_text(candidate: dict[str, Any], full_email: dict[str, Any] | None) -> str:
    for source in (
        str(candidate.get("snippet") or ""),
        str((full_email or {}).get("body_text") or ""),
        str((full_email or {}).get("normalized_body_text") or ""),
    ):
        if source.strip():
            return source
    return ""


def _request_expected(text: str) -> tuple[bool, list[str], str, float, bool]:
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
    recipients = _extract_emails(
        [
            *list((full_email or {}).get("to") or []),
            *list((full_email or {}).get("cc") or []),
            *list((full_email or {}).get("bcc") or []),
        ]
    )
    return {
        "uid": str(candidate.get("uid") or ""),
        "date": str(candidate.get("date") or ""),
        "parsed_date": _parse_iso_like(str(candidate.get("date") or "")),
        "sender_email": str(candidate.get("sender_email") or "").lower(),
        "subject": str(candidate.get("subject") or ""),
        "normalized_subject": _normalized_subject(str(candidate.get("subject") or "")),
        "conversation_id": str(candidate.get("conversation_id") or (full_email or {}).get("conversation_id") or ""),
        "thread_key": _thread_key(candidate, full_email),
        "recipients": recipients,
        "text": _best_text(candidate, full_email),
    }


def build_reply_pairing_index(
    *,
    candidates: list[dict[str, Any]],
    full_map: dict[str, Any],
    case_scope: Any,
) -> dict[str, dict[str, Any]]:
    """Return conservative reply-pairing metadata for target-authored requests."""
    target_email = str(getattr(getattr(case_scope, "target_person", None), "email", "") or "").strip().lower()
    suspected_actor_emails = {
        str(getattr(actor, "email", "") or "").strip().lower()
        for actor in list(getattr(case_scope, "suspected_actors", []) or [])
        if str(getattr(actor, "email", "") or "").strip()
    }
    rows = [
        _row_for_candidate(candidate, full_map.get(str(candidate.get("uid") or "")) if isinstance(full_map, dict) else None)
        for candidate in candidates
    ]
    rows = [row for row in rows if row["uid"]]
    rows.sort(key=lambda row: (row["parsed_date"] or datetime.max, row["uid"]))

    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        request_expected, request_reasons, detection_status, detection_confidence, format_limited = _request_expected(row["text"])
        target_authored_request = bool(target_email and row["sender_email"] == target_email)
        if suspected_actor_emails:
            relevant_actor_emails = [email for email in row["recipients"] if email in suspected_actor_emails]
        else:
            relevant_actor_emails = [email for email in row["recipients"] if email and email != target_email]
        summary: dict[str, Any] = {
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
        index[row["uid"]] = summary
        if not request_expected:
            if format_limited:
                summary["counter_indicators"].append(
                    "Quoted-wrapper formatting is visible, but the visible text does not expose a bounded reply request."
                )
            else:
                summary["counter_indicators"].append("The message did not contain a bounded reply-expected cue.")
            continue
        if not target_authored_request:
            summary["counter_indicators"].append("Selective non-response checks are limited to target-authored requests.")
            continue
        if not relevant_actor_emails:
            summary["counter_indicators"].append("No relevant recipient actor was visible for reply-pairing checks.")
            continue

        later_rows = []
        for later in rows:
            if later["uid"] == row["uid"]:
                continue
            if later["parsed_date"] is None or row["parsed_date"] is None or later["parsed_date"] <= row["parsed_date"]:
                continue
            if later["sender_email"] not in relevant_actor_emails:
                continue
            same_thread = bool(row["thread_key"] and later["thread_key"] and row["thread_key"] == later["thread_key"])
            same_subject = bool(row["normalized_subject"] and row["normalized_subject"] == later["normalized_subject"])
            if not same_thread and not same_subject:
                continue
            later_rows.append(later)

        summary["later_activity_uids"] = [later["uid"] for later in later_rows]
        summary["later_activity_by_relevant_actor"] = bool(later_rows)
        direct_reply = next((later for later in later_rows if target_email in later["recipients"]), None)
        if direct_reply is not None and row["parsed_date"] is not None and direct_reply["parsed_date"] is not None:
            delay_hours = round((direct_reply["parsed_date"] - row["parsed_date"]).total_seconds() / 3600, 2)
            summary["direct_reply_uid"] = direct_reply["uid"]
            summary["direct_reply_sender_email"] = direct_reply["sender_email"]
            summary["response_delay_hours"] = delay_hours
            summary["response_status"] = "delayed_reply" if delay_hours > _REPLY_DELAY_HOURS else "direct_reply"
            summary["counter_indicators"].append("A direct reply from a relevant actor is visible in the current evidence set.")
            continue
        if later_rows:
            summary["response_status"] = "indirect_activity_without_direct_reply"
            summary["supports_selective_non_response_inference"] = True
            continue
        summary["response_status"] = "no_reply_observed"
        summary["counter_indicators"].append(
            "No later activity from a relevant actor is visible in the current evidence set, "
            "so non-response remains context-limited."
        )
    return index
