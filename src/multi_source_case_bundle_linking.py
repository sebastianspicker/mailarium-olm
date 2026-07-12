# mypy: disable-error-code=name-defined
# pylint: disable=too-many-branches,too-many-locals,too-many-statements


# pylint: disable=E0602  # cross-module names injected by compatibility facade
"""Split multi-source case-bundle helpers (multi_source_case_bundle_linking)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, cast

from .multi_source_case_bundle_common import (
    _date_key,
    _identity_tokens_for_source,
    _issue_tokens,
    _link_confidence,
    _normalized_subject,
    _normalized_text,
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


@dataclass(frozen=True)
class _LinkFacts:
    source_id: str
    uid: str
    subject: str
    date: str
    identity_tokens: set[str]
    issue_tokens: set[str]
    message_keys: set[str]
    search_text: str


def _link_facts(source: dict[str, Any]) -> _LinkFacts:
    provenance = cast(dict[str, Any], source.get("provenance") or {})
    message_keys = {
        _normalized_text(provenance.get("message_id")),
        _normalized_text(provenance.get("in_reply_to")),
        _normalized_text(provenance.get("references")),
        _normalized_text(source.get("conversation_id")),
    } - {""}
    search_text = " ".join(
        part
        for part in (
            str(source.get("searchable_text") or ""),
            str(source.get("snippet") or ""),
            str(source.get("title") or ""),
        )
        if part
    )
    return _LinkFacts(
        source_id=str(source.get("source_id") or ""),
        uid=str(source.get("uid") or ""),
        subject=_normalized_subject(source.get("title")),
        date=_date_key(source.get("date")),
        identity_tokens=_identity_tokens_for_source(source),
        issue_tokens=_issue_tokens(source.get("snippet")) | _issue_tokens(source.get("title")),
        message_keys=message_keys,
        search_text=search_text,
    )


def _link_match_basis(
    source: dict[str, Any],
    source_facts: _LinkFacts,
    email_facts: _LinkFacts,
) -> tuple[list[str], int, bool]:
    basis: list[str] = []
    score = 0
    explicit_uid = bool(source_facts.uid and email_facts.uid and source_facts.uid == email_facts.uid)
    checks = (
        (explicit_uid, "explicit_related_email_uid", 10),
        (bool(source_facts.message_keys & email_facts.message_keys), "message_or_thread_key_overlap", 5),
        (bool(source_facts.subject and source_facts.subject == email_facts.subject), "normalized_subject_match", 3),
        (bool(source_facts.date and source_facts.date == email_facts.date), "same_day_match", 2),
        (bool(source_facts.identity_tokens & email_facts.identity_tokens), "participant_overlap", 2),
        (len(source_facts.issue_tokens & email_facts.issue_tokens) >= 2, "issue_token_overlap", 1),
    )
    for matched, label, weight in checks:
        if matched:
            basis.append(label)
            score += weight
    if _has_search_text_overlap(source, source_facts, email_facts):
        basis.append("quoted_or_body_similarity")
        score += 2
    if str(source.get("source_type") or "") == "chat_log" and "same_day_match" in basis and "participant_overlap" in basis:
        basis.append("parallel_record_timing_overlap")
        score += 1
    return basis, score, explicit_uid


def _has_search_text_overlap(
    source: dict[str, Any],
    source_facts: _LinkFacts,
    email_facts: _LinkFacts,
) -> bool:
    if not source_facts.search_text or not email_facts.search_text:
        return False
    terms = (_issue_tokens(source_facts.search_text) | _identity_tokens_for_source(source)) & _issue_tokens(
        email_facts.search_text
    )
    return len([term for term in sorted(terms) if term]) >= 2


def _link_candidate(
    source: dict[str, Any],
    source_facts: _LinkFacts,
    email_source: dict[str, Any],
) -> dict[str, Any] | None:
    email_facts = _link_facts(email_source)
    if email_facts.source_id == source_facts.source_id:
        return None
    basis, score, explicit_uid = _link_match_basis(source, source_facts, email_facts)
    if not basis:
        return None
    return {
        "source_id": source_facts.source_id,
        "candidate_email_source_id": email_facts.source_id,
        "confidence": _link_confidence(score, explicit_uid=explicit_uid),
        "match_basis": basis,
        "score": score,
        "status": "candidate_link",
    }


def _candidate_sort_key(item: dict[str, Any]) -> tuple[int, str]:
    return (-int(item.get("score") or 0), str(item.get("candidate_email_source_id") or ""))


def _rank_link_diagnostics(diagnostics: list[dict[str, Any]]) -> None:
    diagnostics.sort(key=_candidate_sort_key)
    for index, item in enumerate(diagnostics, start=1):
        item["candidate_rank"] = index


def _ambiguous_link_diagnostics(candidates: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    best = candidates[0]
    tied = [item for item in candidates[1:] if int(item.get("score") or 0) == int(best.get("score") or 0)]
    if not tied or str(best.get("confidence") or "") == "high":
        return None
    ambiguous_ids = _candidate_ids([best, *tied])
    result: list[dict[str, Any]] = []
    for item in sorted(candidates, key=_candidate_sort_key):
        result.append(_ambiguous_diagnostic(item, ambiguous_ids, rank=len(result) + 1))
    return result


def _candidate_ids(candidates: list[dict[str, Any]]) -> set[str]:
    return {candidate_id for item in candidates if (candidate_id := str(item.get("candidate_email_source_id") or ""))}


def _ambiguous_diagnostic(item: dict[str, Any], ambiguous_ids: set[str], *, rank: int) -> dict[str, Any]:
    candidate_id = str(item.get("candidate_email_source_id") or "")
    status = "ambiguous_candidate_link" if candidate_id in ambiguous_ids else str(item.get("status") or "candidate_link")
    return {
        **item,
        "status": status,
        "ambiguity_state": "tied_medium_confidence_candidates",
        "candidate_rank": rank,
    }


def _resolved_source_link(source_id: str, best: dict[str, Any]) -> dict[str, Any]:
    explicit = "explicit_related_email_uid" in best["match_basis"]
    return {
        "from_source_id": source_id,
        "to_source_id": str(best.get("candidate_email_source_id") or ""),
        "link_type": "declared_related_record" if explicit else "related_to_email",
        "relationship": "matter_manifest_cross_reference" if explicit else "conservative_document_email_correlation",
        "confidence": str(best.get("confidence") or ""),
        "match_basis": list(best.get("match_basis") or []),
    }


def resolve_manifest_email_links(
    source: dict[str, Any],
    *,
    email_sources: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return conservative manifest-to-email links plus visible diagnostics."""
    facts = _link_facts(source)
    if not facts.source_id:
        return ([], [])
    diagnostics = [
        candidate for email_source in email_sources if (candidate := _link_candidate(source, facts, email_source)) is not None
    ]
    candidates = [item for item in diagnostics if str(item.get("confidence") or "") in {"high", "medium"}]
    if not candidates:
        return ([], diagnostics)
    candidates.sort(key=_candidate_sort_key)
    _rank_link_diagnostics(diagnostics)
    ambiguous = _ambiguous_link_diagnostics(candidates)
    if ambiguous is not None:
        return ([], ambiguous)
    return ([_resolved_source_link(facts.source_id, candidates[0])], diagnostics)


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
