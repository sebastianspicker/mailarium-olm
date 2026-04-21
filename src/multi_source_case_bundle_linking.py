# mypy: disable-error-code=name-defined
"""Split multi-source case-bundle helpers (multi_source_case_bundle_linking)."""

from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from .attachment_extractor import (
    attachment_format_profile,
    extraction_quality_profile,
)

MULTI_SOURCE_CASE_BUNDLE_VERSION = "1"
_DECLARED_SOURCE_TYPES = (
    "email",
    "attachment",
    "meeting_note",
    "chat_log",
    "formal_document",
    "note_record",
    "time_record",
    "participation_record",
)
_FORMAL_DOCUMENT_EXTENSIONS = {".doc", ".docx", ".md", ".odt", ".pdf", ".rtf", ".txt"}
_FORMAL_DOCUMENT_MIME_MARKERS = (
    "application/pdf",
    "application/msword",
    "application/rtf",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "text/rtf",
)
_NOTE_RECORD_KEYWORDS = (
    "notes",
    "memo",
    "minutes",
    "meeting summary",
    "protokoll",
    "gedächtnisprotokoll",
    "gedaechtnisprotokoll",
    "aktennotiz",
)
_TIME_RECORD_KEYWORDS = (
    "timesheet",
    "time sheet",
    "time record",
    "attendance",
    "arbeitszeit",
    "arbeitszeitnachweis",
    "zeiterfassung",
    "stundennachweis",
)
_PARTICIPATION_RECORD_KEYWORDS = (
    "sbv",
    "schwerbehindertenvertretung",
    "personalrat",
    "betriebsrat",
    "mitbestimmung",
    "consultation",
    "beteiligung",
    "anhoerung",
    "anhörung",
)
_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_DATE_RANGE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\s*(?:to|through|until|bis|–|-)\s*(\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)
_EU_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})[./](20\d{2})(?!\d)")
_DATE_RANGE_EU_RE = re.compile(
    r"(?<!\d)(\d{1,2}[./]\d{1,2}[./]20\d{2})\s*(?:to|through|until|bis|–|-)\s*(\d{1,2}[./]\d{1,2}[./]20\d{2})(?!\d)",
    re.IGNORECASE,
)
_SHEET_NAME_RE = re.compile(r"\[Sheet:\s*([^\]]+)\]")
_MONTH_LABEL_RE = re.compile(
    r"(?i)\b("
    r"january|february|march|april|may|june|july|august|september|october|november|december|"
    r"januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember"
    r")\b"
)
_ICAL_FIELD_RE = re.compile(
    r"(?im)^(SUMMARY|DTSTART|DTEND|LOCATION|ORGANIZER|ATTENDEE|STATUS|METHOD|SEQUENCE|UID|RECURRENCE-ID|DESCRIPTION)[^:\n]*:(.+)$"
)
_ICAL_DATETIME_RE = re.compile(r"\b(20\d{2})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})?)?")
_EMAIL_LINK_TOKEN_RE = re.compile(r"[a-z0-9äöüß]{4,}")
_TITLE_DATE_RE = re.compile(r"(?<!\d)(20\d{2})[-._](\d{2})[-._](\d{2})(?!\d)")
_EMAIL_LINK_STOPWORDS = {
    "about",
    "after",
    "before",
    "document",
    "dokument",
    "email",
    "formal",
    "from",
    "meeting",
    "message",
    "note",
    "record",
    "reply",
    "status",
    "subject",
    "summary",
    "thread",
}
_INLINE_EMAIL_RE = re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}")
_DATE_ORIGIN_PRIORITY = {
    "meeting_metadata": 60,
    "calendar_dtstart": 55,
    "time_record_range_start": 50,
    "document_text": 45,
    "time_record_range_end": 35,
    "source_timestamp": 25,
}

# ruff: noqa: F401,F821


def resolve_manifest_email_links(
    source: dict[str, Any],
    *,
    email_sources: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return conservative manifest-to-email links plus visible diagnostics."""
    source_id = str(source.get("source_id") or "")
    if not source_id:
        return ([], [])
    diagnostics: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    source_uid = str(source.get("uid") or "")
    source_subject = _normalized_subject(source.get("title"))
    source_date = _date_key(source.get("date"))
    source_identity_tokens = _identity_tokens_for_source(source)
    source_issue_tokens = _issue_tokens(source.get("snippet")) | _issue_tokens(source.get("title"))
    source_provenance: dict[str, Any] = cast(dict[str, Any], source.get("provenance") or {})
    source_message_id = _normalized_text(source_provenance.get("message_id"))
    source_in_reply_to = _normalized_text(source_provenance.get("in_reply_to"))
    source_references = _normalized_text(source_provenance.get("references"))
    source_message_keys = {
        source_message_id,
        source_in_reply_to,
        source_references,
        _normalized_text(source.get("conversation_id")),
    } - {""}
    source_search_text = " ".join(
        part
        for part in (str(source.get("searchable_text") or ""), str(source.get("snippet") or ""), str(source.get("title") or ""))
        if part
    )
    for email_source in email_sources:
        email_source_id = str(email_source.get("source_id") or "")
        if email_source_id == source_id:
            continue
        email_uid = str(email_source.get("uid") or "")
        email_subject = _normalized_subject(email_source.get("title"))
        email_date = _date_key(email_source.get("date"))
        email_identity_tokens = _identity_tokens_for_source(email_source)
        email_issue_tokens = _issue_tokens(email_source.get("snippet")) | _issue_tokens(email_source.get("title"))
        email_provenance: dict[str, Any] = cast(dict[str, Any], email_source.get("provenance") or {})
        email_message_id = _normalized_text(email_provenance.get("message_id"))
        email_in_reply_to = _normalized_text(email_provenance.get("in_reply_to"))
        email_references = _normalized_text(email_provenance.get("references"))
        email_message_keys = {
            email_message_id,
            email_in_reply_to,
            email_references,
            _normalized_text(email_source.get("conversation_id")),
        } - {""}
        email_search_text = " ".join(
            part
            for part in (
                str(email_source.get("searchable_text") or ""),
                str(email_source.get("snippet") or ""),
                str(email_source.get("title") or ""),
            )
            if part
        )
        match_basis: list[str] = []
        score = 0
        explicit_uid = bool(source_uid and email_uid and source_uid == email_uid)
        if explicit_uid:
            match_basis.append("explicit_related_email_uid")
            score += 10
        if source_message_keys and email_message_keys and source_message_keys & email_message_keys:
            match_basis.append("message_or_thread_key_overlap")
            score += 5
        if source_subject and email_subject and source_subject == email_subject:
            match_basis.append("normalized_subject_match")
            score += 3
        if source_date and email_date and source_date == email_date:
            match_basis.append("same_day_match")
            score += 2
        if source_identity_tokens and email_identity_tokens and source_identity_tokens & email_identity_tokens:
            match_basis.append("participant_overlap")
            score += 2
        issue_overlap = sorted(source_issue_tokens & email_issue_tokens)
        if len(issue_overlap) >= 2:
            match_basis.append("issue_token_overlap")
            score += 1
        if source_search_text and email_search_text:
            overlapping_terms = [
                term
                for term in sorted(
                    (_issue_tokens(source_search_text) | _identity_tokens_for_source(source)) & _issue_tokens(email_search_text)
                )
                if term
            ]
            if len(overlapping_terms) >= 2:
                match_basis.append("quoted_or_body_similarity")
                score += 2
        if (
            str(source.get("source_type") or "") == "chat_log"
            and "same_day_match" in match_basis
            and "participant_overlap" in match_basis
        ):
            match_basis.append("parallel_record_timing_overlap")
            score += 1
        confidence = _link_confidence(score, explicit_uid=explicit_uid)
        if not match_basis:
            continue
        candidate = {
            "source_id": source_id,
            "candidate_email_source_id": email_source_id,
            "confidence": confidence,
            "match_basis": match_basis,
            "score": score,
            "status": "candidate_link",
        }
        diagnostics.append(candidate)
        if confidence in {"high", "medium"}:
            candidates.append(candidate)
    if not candidates:
        return ([], diagnostics)
    candidates.sort(key=lambda item: (-int(item.get("score") or 0), str(item.get("candidate_email_source_id") or "")))
    diagnostics.sort(key=lambda item: (-int(item.get("score") or 0), str(item.get("candidate_email_source_id") or "")))
    for index, item in enumerate(diagnostics, start=1):
        item["candidate_rank"] = index
    best = candidates[0]
    ambiguous = [item for item in candidates[1:] if int(item.get("score") or 0) == int(best.get("score") or 0)]
    if ambiguous and str(best.get("confidence") or "") != "high":
        ambiguous_ids = {
            str(item.get("candidate_email_source_id") or "")
            for item in [best, *ambiguous]
            if str(item.get("candidate_email_source_id") or "")
        }
        diagnostics = []
        for item in sorted(
            candidates, key=lambda row: (-int(row.get("score") or 0), str(row.get("candidate_email_source_id") or ""))
        ):
            candidate_email_source_id = str(item.get("candidate_email_source_id") or "")
            diagnostics.append(
                {
                    **item,
                    "status": "ambiguous_candidate_link"
                    if candidate_email_source_id in ambiguous_ids
                    else str(item.get("status") or "candidate_link"),
                    "ambiguity_state": "tied_medium_confidence_candidates",
                    "candidate_rank": len(diagnostics) + 1,
                }
            )
        return ([], diagnostics)
    link_type = "declared_related_record" if "explicit_related_email_uid" in best["match_basis"] else "related_to_email"
    relationship = (
        "matter_manifest_cross_reference"
        if "explicit_related_email_uid" in best["match_basis"]
        else "conservative_document_email_correlation"
    )
    return (
        [
            {
                "from_source_id": source_id,
                "to_source_id": str(best.get("candidate_email_source_id") or ""),
                "link_type": link_type,
                "relationship": relationship,
                "confidence": str(best.get("confidence") or ""),
                "match_basis": list(best.get("match_basis") or []),
            }
        ],
        diagnostics,
    )


__all__ = [
    "MULTI_SOURCE_CASE_BUNDLE_VERSION",
    "_DATE_ORIGIN_PRIORITY",
    "_DATE_RANGE_EU_RE",
    "_DATE_RANGE_RE",
    "_DECLARED_SOURCE_TYPES",
    "_EMAIL_LINK_STOPWORDS",
    "_EMAIL_LINK_TOKEN_RE",
    "_EU_DATE_RE",
    "_FORMAL_DOCUMENT_EXTENSIONS",
    "_FORMAL_DOCUMENT_MIME_MARKERS",
    "_ICAL_DATETIME_RE",
    "_ICAL_FIELD_RE",
    "_INLINE_EMAIL_RE",
    "_ISO_DATE_RE",
    "_MONTH_LABEL_RE",
    "_NOTE_RECORD_KEYWORDS",
    "_PARTICIPATION_RECORD_KEYWORDS",
    "_SHEET_NAME_RE",
    "_TIME_RECORD_KEYWORDS",
    "_TITLE_DATE_RE",
    "resolve_manifest_email_links",
]
