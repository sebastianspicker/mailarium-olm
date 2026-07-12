# mypy: disable-error-code=name-defined
# pylint: disable=too-many-locals


# pylint: disable=E0602  # cross-module names injected by compatibility facade
"""Split multi-source case-bundle helpers (multi_source_case_bundle_sources)."""

from __future__ import annotations

from collections import Counter
from typing import Any, cast

from .multi_source_case_bundle_chronology import _chronology_anchor_for_source
from .multi_source_case_bundle_common import (
    _DATE_ORIGIN_PRIORITY,
    _DATE_RANGE_EU_RE,
    _DATE_RANGE_RE,
    _DECLARED_SOURCE_TYPES,
    _EMAIL_LINK_STOPWORDS,
    _EMAIL_LINK_TOKEN_RE,
    _EU_DATE_RE,
    _FORMAL_DOCUMENT_EXTENSIONS,
    _FORMAL_DOCUMENT_MIME_MARKERS,
    _ICAL_DATETIME_RE,
    _ICAL_FIELD_RE,
    _INLINE_EMAIL_RE,
    _ISO_DATE_RE,
    _MONTH_LABEL_RE,
    _NOTE_RECORD_KEYWORDS,
    _PARTICIPATION_RECORD_KEYWORDS,
    _SHEET_NAME_RE,
    _TIME_RECORD_KEYWORDS,
    _TITLE_DATE_RE,
    MULTI_SOURCE_CASE_BUNDLE_VERSION,
)
from .multi_source_case_bundle_linking import resolve_manifest_email_links
from .multi_source_case_bundle_reliability import (
    _source_reliability_for_chat_log,
    _source_reliability_for_meeting,
    _string_list,
    _weighting_metadata,
)


def _meeting_note_sources(uid: str, full_email: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Extract meeting note sources from email metadata.

    Creates meeting_note sources from:
    - meeting_data: calendar metadata attached to the email
    - exchange_extracted_meetings: Exchange meeting references

    Each source includes reliability and weighting metadata.
    Returns a list of meeting note source dicts.
    """
    email = full_email or {}
    sources = _meeting_data_note(uid, email)
    return sources + _exchange_meeting_notes(uid, email)


def _meeting_data_note(uid: str, email: dict[str, Any]) -> list[dict[str, Any]]:
    meeting_data = email.get("meeting_data")
    if not isinstance(meeting_data, dict) or not meeting_data:
        return []
    return [_meeting_note(uid, email, meeting_data, "meeting_data", "calendar_metadata", 0)]


def _exchange_meeting_notes(uid: str, email: dict[str, Any]) -> list[dict[str, Any]]:
    meetings = email.get("exchange_extracted_meetings")
    if not isinstance(meetings, list):
        return []
    return [
        _meeting_note(uid, email, meeting, "exchange_extracted_meetings", "exchange_meeting_reference", index)
        for index, meeting in enumerate(meetings, start=1)
        if isinstance(meeting, dict) and meeting
    ]


def _meeting_note(
    uid: str, email: dict[str, Any], meeting: dict[str, Any], origin: str, document_kind: str, index: int
) -> dict[str, Any]:
    source_id = f"meeting:{uid}:exchange:{index}" if index else f"meeting:{uid}:meeting_data"
    provenance: dict[str, Any] = {"uid": uid, "meeting_source": origin}
    if index:
        provenance["index"] = index
    note: dict[str, Any] = {
        "source_id": source_id,
        "source_type": "meeting_note",
        "document_kind": document_kind,
        "uid": uid,
        "parent_source_id": f"email:{uid}",
        "title": str(meeting.get("subject") or email.get("subject") or ""),
        "snippet": "; ".join(f"{key}={value}" for key, value in sorted(meeting.items())[:3]),
        "date": str(email.get("date") or ""),
        "provenance": provenance,
        "_extracted_from": origin,
    }
    reliability = _source_reliability_for_meeting(note)
    note["source_reliability"] = reliability
    note["source_weighting"] = _weighting_metadata(
        source_type="meeting_note", reliability_level=str(reliability["level"]), text_available=True
    )
    return note


def _chat_log_sources(
    chat_log_entries: list[dict[str, Any]] | None,
    *,
    email_source_ids_by_uid: dict[str, str],
    email_sources: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], Counter[str]]:
    """Extract chat log sources from chat log entries.

    Processes each chat log entry to create chat_log sources with:
    - Reliability and weighting metadata
    - Chronology anchors
    - Links to related email sources
    - Diagnostics for source linking

    Returns a tuple of:
    - chat_sources: list of chat log source dicts
    - chat_links: list of source link dicts
    - chat_diagnostics: list of diagnostic dicts
    - chat_counts: Counter of source types
    """
    context = _chat_context()
    for index, entry in enumerate(chat_log_entries or [], start=1):
        if isinstance(entry, dict):
            _append_chat_entry(context, entry, index, email_source_ids_by_uid, email_sources)
    return context["sources"], context["links"], context["diagnostics"], context["counts"]


def _chat_context() -> dict[str, Any]:
    return {"sources": [], "links": [], "diagnostics": [], "counts": Counter()}


def _append_chat_entry(
    context: dict[str, Any], entry: dict[str, Any], index: int, email_ids: dict[str, str], email_sources: list[dict[str, Any]]
) -> None:
    source = _chat_source(entry, index)
    cast(list[dict[str, Any]], context["sources"]).append(source)
    cast(Counter[str], context["counts"])["chat_log"] += 1
    _append_chat_links(context, source, email_ids, email_sources)


def _chat_source(entry: dict[str, Any], index: int) -> dict[str, Any]:
    source = {**_chat_identity(entry, index), **_chat_content(entry), **_chat_reliability(entry)}
    anchor = _chronology_anchor_for_source(source)
    if anchor is not None:
        source["chronology_anchor"] = anchor
    return source


def _chat_identity(entry: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "source_id": str(entry.get("source_id") or f"chat:{index}"),
        "source_type": "chat_log",
        "document_kind": "operator_chat_log",
        "uid": str(entry.get("uid") or entry.get("related_email_uid") or ""),
        "title": str(entry.get("title") or "Chat export"),
        "date": str(entry.get("date") or ""),
    }


def _chat_content(entry: dict[str, Any]) -> dict[str, Any]:
    messages = [item for item in entry.get("parsed_messages", []) if isinstance(item, dict)]
    count = int(entry.get("chat_message_count") or entry.get("message_count") or len(messages) or 0)
    return {
        "snippet": str(entry.get("snippet") or entry.get("text") or ""),
        "participants": _string_list(entry.get("participants")),
        "parsed_messages": messages,
        "chat_message_units": messages,
        "message_count": count,
        "chat_message_count": count,
        "provenance": dict(entry.get("provenance") or {}),
    }


def _chat_reliability(entry: dict[str, Any]) -> dict[str, Any]:
    reliability = _source_reliability_for_chat_log(entry)
    return {
        "source_reliability": reliability,
        "source_weighting": _weighting_metadata(
            source_type="chat_log",
            reliability_level=str(reliability["level"]),
            text_available=bool(str(entry.get("snippet") or entry.get("text") or "").strip()),
        ),
    }


def _append_chat_links(
    context: dict[str, Any], source: dict[str, Any], email_ids: dict[str, str], emails: list[dict[str, Any]]
) -> None:
    uid = str(source.get("uid") or "")
    if uid in email_ids:
        _append_explicit_chat_link(context, source, email_ids[uid])
        return
    links, diagnostics = resolve_manifest_email_links(source, email_sources=emails)
    cast(list[dict[str, Any]], context["diagnostics"]).extend(diagnostics)
    if links:
        link = dict(links[0])
        link["relationship"] = (
            "operator_supplied_parallel_record"
            if link.get("link_type") == "declared_related_record"
            else "conservative_chat_email_correlation"
        )
        cast(list[dict[str, Any]], context["links"]).append(link)


def _append_explicit_chat_link(context: dict[str, Any], source: dict[str, Any], email_source_id: str) -> None:
    source_id = str(source.get("source_id") or "")
    cast(list[dict[str, Any]], context["links"]).append(
        {
            "from_source_id": source_id,
            "to_source_id": email_source_id,
            "link_type": "related_to_email",
            "relationship": "operator_supplied_parallel_record",
        }
    )
    cast(list[dict[str, Any]], context["diagnostics"]).append(
        {
            "source_id": source_id,
            "candidate_email_source_id": email_source_id,
            "confidence": "high",
            "match_basis": ["explicit_related_email_uid"],
            "score": 10,
            "status": "candidate_link",
        }
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
    "_chat_log_sources",
    "_meeting_note_sources",
]
