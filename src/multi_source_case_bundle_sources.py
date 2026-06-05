# mypy: disable-error-code=name-defined
# pylint: disable=too-many-locals


# pylint: disable=E0602  # cross-module names injected by compatibility facade
"""Split multi-source case-bundle helpers (multi_source_case_bundle_sources)."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, cast

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

# ruff: noqa: F401,F821


def _meeting_note_sources(uid: str, full_email: dict[str, Any] | None) -> list[dict[str, Any]]:
    email = full_email or {}
    sources: list[dict[str, Any]] = []
    meeting_data = email.get("meeting_data")
    if isinstance(meeting_data, dict) and meeting_data:
        note = {
            "source_id": f"meeting:{uid}:meeting_data",
            "source_type": "meeting_note",
            "document_kind": "calendar_metadata",
            "uid": uid,
            "parent_source_id": f"email:{uid}",
            "title": str(email.get("subject") or meeting_data.get("subject") or ""),
            "snippet": "; ".join(f"{key}={value}" for key, value in sorted(meeting_data.items())[:3]),
            "date": str(email.get("date") or ""),
            "provenance": {"uid": uid, "meeting_source": "meeting_data"},
            "_extracted_from": "meeting_data",
        }
        reliability = _source_reliability_for_meeting(note)
        note["source_reliability"] = reliability
        note["source_weighting"] = _weighting_metadata(
            source_type="meeting_note", reliability_level=str(reliability["level"]), text_available=True
        )
        sources.append(note)
    exchange_meetings = email.get("exchange_extracted_meetings")
    if isinstance(exchange_meetings, list):
        for index, meeting in enumerate(exchange_meetings, start=1):
            if not isinstance(meeting, dict) or not meeting:
                continue
            note = {
                "source_id": f"meeting:{uid}:exchange:{index}",
                "source_type": "meeting_note",
                "document_kind": "exchange_meeting_reference",
                "uid": uid,
                "parent_source_id": f"email:{uid}",
                "title": str(meeting.get("subject") or email.get("subject") or ""),
                "snippet": "; ".join(f"{key}={value}" for key, value in sorted(meeting.items())[:3]),
                "date": str(email.get("date") or ""),
                "provenance": {"uid": uid, "meeting_source": "exchange_extracted_meetings", "index": index},
                "_extracted_from": "exchange_extracted_meetings",
            }
            reliability = _source_reliability_for_meeting(note)
            note["source_reliability"] = reliability
            note["source_weighting"] = _weighting_metadata(
                source_type="meeting_note", reliability_level=str(reliability["level"]), text_available=True
            )
            sources.append(note)
    return sources


def _chat_log_sources(
    chat_log_entries: list[dict[str, Any]] | None,
    *,
    email_source_ids_by_uid: dict[str, str],
    email_sources: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], Counter[str]]:
    chat_sources: list[dict[str, Any]] = []
    chat_links: list[dict[str, Any]] = []
    chat_diagnostics: list[dict[str, Any]] = []
    chat_counts: Counter[str] = Counter()
    for index, entry in enumerate(chat_log_entries or [], start=1):
        if not isinstance(entry, dict):
            continue
        source_id = str(entry.get("source_id") or f"chat:{index}")
        parsed_messages = [item for item in entry.get("parsed_messages", []) if isinstance(item, dict)]
        message_count = int(entry.get("chat_message_count") or entry.get("message_count") or len(parsed_messages) or 0)
        reliability = _source_reliability_for_chat_log(entry)
        source = {
            "source_id": source_id,
            "source_type": "chat_log",
            "document_kind": "operator_chat_log",
            "uid": str(entry.get("uid") or entry.get("related_email_uid") or ""),
            "title": str(entry.get("title") or "Chat export"),
            "date": str(entry.get("date") or ""),
            "snippet": str(entry.get("snippet") or entry.get("text") or ""),
            "participants": _string_list(entry.get("participants")),
            "parsed_messages": parsed_messages,
            "chat_message_units": parsed_messages,
            "message_count": message_count,
            "chat_message_count": message_count,
            "provenance": dict(entry.get("provenance") or {}),
            "source_reliability": reliability,
            "source_weighting": _weighting_metadata(
                source_type="chat_log",
                reliability_level=str(reliability["level"]),
                text_available=bool(str(entry.get("snippet") or entry.get("text") or "").strip()),
            ),
        }
        chronology_anchor = _chronology_anchor_for_source(source)
        if chronology_anchor is not None:
            source["chronology_anchor"] = chronology_anchor
        chat_sources.append(source)
        chat_counts["chat_log"] += 1
        uid = str(source.get("uid") or "")
        if uid and uid in email_source_ids_by_uid:
            chat_links.append(
                {
                    "from_source_id": source_id,
                    "to_source_id": email_source_ids_by_uid[uid],
                    "link_type": "related_to_email",
                    "relationship": "operator_supplied_parallel_record",
                }
            )
            chat_diagnostics.append(
                {
                    "source_id": source_id,
                    "candidate_email_source_id": email_source_ids_by_uid[uid],
                    "confidence": "high",
                    "match_basis": ["explicit_related_email_uid"],
                    "score": 10,
                    "status": "candidate_link",
                }
            )
            continue
        links, diagnostics = resolve_manifest_email_links(source, email_sources=email_sources)
        chat_diagnostics.extend(diagnostics)
        if links:
            best_link = dict(links[0])
            best_link["relationship"] = (
                "operator_supplied_parallel_record"
                if best_link.get("link_type") == "declared_related_record"
                else "conservative_chat_email_correlation"
            )
            chat_links.append(best_link)
    return chat_sources, chat_links, chat_diagnostics, chat_counts


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
