# mypy: disable-error-code=name-defined
"""Split multi-source case-bundle helpers (multi_source_case_bundle_chronology)."""

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


def _chronology_text(source: dict[str, Any]) -> str:
    documentary = (
        cast(dict[str, Any], source.get("documentary_support")) if isinstance(source.get("documentary_support"), dict) else {}
    )
    return " ".join(
        part
        for part in (
            str(source.get("title") or ""),
            str(source.get("snippet") or ""),
            str(source.get("searchable_text") or ""),
            str(documentary.get("text_preview") or ""),
        )
        if part
    )


def _date_range_from_text(text: str) -> dict[str, str] | None:
    match = _DATE_RANGE_RE.search(text)
    if match:
        start, end = match.group(1), match.group(2)
    else:
        eu_match = _DATE_RANGE_EU_RE.search(text)
        if not eu_match:
            return None
        start = _iso_date_from_eu_text(eu_match.group(1))
        end = _iso_date_from_eu_text(eu_match.group(2))
        if not (start and end):
            return None
    if start > end:
        start, end = end, start
    return {"start": start, "end": end}


def _event_date_from_text(text: str) -> str:
    candidates = _date_candidates_from_text(text)
    return candidates[0] if candidates else ""


def _ical_field_params(line: str) -> dict[str, str]:
    header = str(line or "").split(":", 1)[0]
    params: dict[str, str] = {}
    for item in header.split(";")[1:]:
        if "=" not in item:
            continue
        key, raw_value = item.split("=", 1)
        key = str(key or "").strip().upper()
        value = str(raw_value or "").strip()
        if key and value:
            params[key] = value
    return params


def _ical_to_iso(value: str, *, tzid: str = "") -> tuple[str, str]:
    compact = " ".join(str(value or "").split()).strip()
    is_utc = compact.endswith("Z")
    if is_utc:
        compact = compact[:-1]
    match = _ICAL_DATETIME_RE.search(compact)
    if not match:
        return "", "unparseable"
    year, month, day, hour, minute, second = match.groups()
    if hour and minute:
        naive = datetime(int(year), int(month), int(day), int(hour), int(minute), int(second or "00"))
        if is_utc:
            return naive.replace(tzinfo=UTC).isoformat(timespec="seconds"), "utc"
        if tzid:
            try:
                return naive.replace(tzinfo=ZoneInfo(tzid)).isoformat(timespec="seconds"), "resolved_tzid"
            except Exception:
                return f"{year}-{month}-{day}T{hour}:{minute}:{second or '00'}", "invalid_tzid"
        return f"{year}-{month}-{day}T{hour}:{minute}:{second or '00'}", "floating"
    return f"{year}-{month}-{day}", "date_only"


def _calendar_semantics(source: dict[str, Any]) -> dict[str, Any] | None:
    explicit = source.get("calendar_semantics")
    if isinstance(explicit, dict) and explicit:
        return explicit
    documentary = (
        cast(dict[str, Any], source.get("documentary_support")) if isinstance(source.get("documentary_support"), dict) else {}
    )
    format_profile = documentary.get("format_profile")
    if not isinstance(format_profile, dict) or str(format_profile.get("format_family") or "") != "calendar":
        return None
    chronology_text = _chronology_text(source)
    field_map: dict[str, list[str]] = {}
    field_params: dict[str, list[dict[str, str]]] = {}
    for match in _ICAL_FIELD_RE.finditer(chronology_text):
        key = match.group(1).upper()
        value = " ".join(str(match.group(2) or "").split()).strip()
        field_map.setdefault(key, [])
        field_params.setdefault(key, [])
        if value and value not in field_map[key]:
            field_map[key].append(value)
            field_params[key].append(_ical_field_params(match.group(0)))
    attendees = list(dict.fromkeys(field_map.get("ATTENDEE", [])))
    dtstart_tzid = str((field_params.get("DTSTART") or [{}])[0].get("TZID") or "") if field_map.get("DTSTART") else ""
    dtend_tzid = str((field_params.get("DTEND") or [{}])[0].get("TZID") or "") if field_map.get("DTEND") else ""
    recurrence_tzid = (
        str((field_params.get("RECURRENCE-ID") or [{}])[0].get("TZID") or "") if field_map.get("RECURRENCE-ID") else ""
    )
    dtstart, dtstart_timezone_resolution = (
        _ical_to_iso(field_map.get("DTSTART", [""])[0], tzid=dtstart_tzid) if field_map.get("DTSTART") else ("", "")
    )
    dtend, dtend_timezone_resolution = (
        _ical_to_iso(field_map.get("DTEND", [""])[0], tzid=dtend_tzid) if field_map.get("DTEND") else ("", "")
    )
    status = field_map.get("STATUS", [""])[0] if field_map.get("STATUS") else ""
    method = field_map.get("METHOD", [""])[0] if field_map.get("METHOD") else ""
    sequence = field_map.get("SEQUENCE", [""])[0] if field_map.get("SEQUENCE") else ""
    recurrence_id, recurrence_timezone_resolution = (
        _ical_to_iso(field_map.get("RECURRENCE-ID", [""])[0], tzid=recurrence_tzid)
        if field_map.get("RECURRENCE-ID")
        else ("", "")
    )
    timezone_statuses = {
        status for status in (dtstart_timezone_resolution, dtend_timezone_resolution, recurrence_timezone_resolution) if status
    }
    timezone_resolution = ""
    if "invalid_tzid" in timezone_statuses:
        timezone_resolution = "invalid_tzid"
    elif "resolved_tzid" in timezone_statuses:
        timezone_resolution = "resolved_tzid"
    elif "utc" in timezone_statuses:
        timezone_resolution = "utc"
    elif "floating" in timezone_statuses:
        timezone_resolution = "floating"
    elif "date_only" in timezone_statuses:
        timezone_resolution = "date_only"
    description = field_map.get("DESCRIPTION", [""])[0] if field_map.get("DESCRIPTION") else ""
    normalized_text = chronology_text.lower()
    cancellation_signal = bool(
        str(status).upper() == "CANCELLED"
        or str(method).upper() == "CANCEL"
        or any(token in normalized_text for token in ("abgesagt", "storniert", "cancelled", "canceled"))
    )
    update_signal = bool(
        recurrence_id
        or (sequence.isdigit() and int(sequence) > 0)
        or any(token in normalized_text for token in ("aktualisiert", "update", "geaendert", "geändert"))
    )
    schedule_signal = "cancellation" if cancellation_signal else "update" if update_signal else "invite"
    return {
        "calendar_summary": field_map.get("SUMMARY", [""])[0] if field_map.get("SUMMARY") else "",
        "dtstart": dtstart,
        "dtend": dtend,
        "dtstart_tzid": dtstart_tzid,
        "dtend_tzid": dtend_tzid,
        "dtstart_timezone_resolution": dtstart_timezone_resolution,
        "dtend_timezone_resolution": dtend_timezone_resolution,
        "location": field_map.get("LOCATION", [""])[0] if field_map.get("LOCATION") else "",
        "organizer": field_map.get("ORGANIZER", [""])[0] if field_map.get("ORGANIZER") else "",
        "attendees": attendees,
        "attendee_count": len(attendees),
        "status": status,
        "method": method,
        "sequence": sequence,
        "uid": field_map.get("UID", [""])[0] if field_map.get("UID") else "",
        "recurrence_id": recurrence_id,
        "recurrence_tzid": recurrence_tzid,
        "recurrence_timezone_resolution": recurrence_timezone_resolution,
        "timezone_resolution": timezone_resolution,
        "description_preview": " ".join(str(description or "").split())[:240],
        "schedule_signal": schedule_signal,
        "cancellation_signal": cancellation_signal,
        "update_signal": update_signal,
        "field_count": sum(len(values) for values in field_map.values()),
    }


def _meeting_event_date(source: dict[str, Any]) -> str:
    provenance = cast(dict[str, Any], source.get("provenance")) if isinstance(source.get("provenance"), dict) else {}
    if str(provenance.get("meeting_source") or "") == "meeting_data":
        text = str(source.get("snippet") or "")
        for key in ("OPFMeetingStartDate", "startTime", "start"):
            marker = f"{key}="
            if marker in text:
                value = text.split(marker, 1)[1].split(";", 1)[0].strip()
                if value:
                    return value
    return ""


def _chronology_anchor_for_source(source: dict[str, Any]) -> dict[str, Any] | None:
    source_type = str(source.get("source_type") or "")
    source_date = str(source.get("date") or "").strip()
    chronology_text = _chronology_text(source)
    event_date = source_date
    date_origin = "source_timestamp"
    anchor_confidence = "medium"
    date_range = None
    date_candidates: list[dict[str, str]] = []
    spreadsheet = _spreadsheet_semantics(source)
    if source_type == "meeting_note":
        meeting_date = _meeting_event_date(source)
        if meeting_date:
            event_date = meeting_date
            date_origin = "meeting_metadata"
            anchor_confidence = "high"
            date_candidates.append({"date": meeting_date, "origin": "meeting_metadata", "confidence": "high"})
    calendar = _calendar_semantics(source)
    if calendar and str(calendar.get("dtstart") or ""):
        event_date = str(calendar.get("dtstart") or "")
        date_origin = "calendar_dtstart"
        timezone_resolution = str(calendar.get("timezone_resolution") or "")
        anchor_confidence = "medium" if timezone_resolution == "invalid_tzid" else "high"
        date_candidates.append(
            {
                "date": event_date,
                "origin": "calendar_dtstart",
                "confidence": "medium" if timezone_resolution == "invalid_tzid" else "high",
            }
        )
    if source_type in {"formal_document", "note_record", "time_record", "participation_record", "attachment"}:
        explicit_range = (
            cast(dict[str, Any], spreadsheet.get("date_range"))
            if source_type == "time_record" and isinstance(spreadsheet, dict) and isinstance(spreadsheet.get("date_range"), dict)
            else None
        )
        detected_range = explicit_range or _date_range_from_text(chronology_text)
        if detected_range is not None and source_type == "time_record":
            date_range = {"start": str(detected_range.get("start") or ""), "end": str(detected_range.get("end") or "")}
            event_date = date_range["start"]
            date_origin = "time_record_range_start"
            anchor_confidence = "high"
            date_candidates.append({"date": date_range["start"], "origin": "time_record_range_start", "confidence": "high"})
            if date_range.get("end"):
                date_candidates.append({"date": date_range["end"], "origin": "time_record_range_end", "confidence": "medium"})
        else:
            extracted_dates = _date_candidates_from_text(chronology_text)
            document_date = extracted_dates[0] if extracted_dates else ""
            if document_date:
                event_date = document_date
                date_origin = "document_text"
                anchor_confidence = "medium"
                date_candidates.extend(
                    {"date": value, "origin": "document_text", "confidence": "medium"} for value in extracted_dates if value
                )
    if not event_date:
        return None
    if source_date and not any(str(item.get("date") or "") == source_date for item in date_candidates):
        date_candidates.append({"date": source_date, "origin": "source_timestamp", "confidence": "medium"})
    ranked_candidates = [item for item in date_candidates if str(item.get("date") or "")]
    if ranked_candidates:

        def _candidate_key(indexed_candidate: tuple[int, dict[str, str]]) -> tuple[int, int, int, int]:
            index, candidate = indexed_candidate
            origin = str(candidate.get("origin") or "")
            confidence = str(candidate.get("confidence") or "")
            confidence_rank = {"high": 3, "medium": 2, "low": 1}.get(confidence, 0)
            precision_rank = 2 if "T" in str(candidate.get("date") or "") else 1
            return (
                int(_DATE_ORIGIN_PRIORITY.get(origin, 0)),
                confidence_rank,
                precision_rank,
                -index,
            )

        best_index, best_candidate = max(enumerate(ranked_candidates), key=_candidate_key)
        event_date = str(best_candidate.get("date") or event_date)
        date_origin = str(best_candidate.get("origin") or date_origin)
        anchor_confidence = str(best_candidate.get("confidence") or anchor_confidence)
        rejected_candidates = [
            {**candidate, "rejected_reason": "lower_rank_than_selected"}
            for index, candidate in enumerate(ranked_candidates)
            if index != best_index
        ]
    else:
        best_candidate = {"date": event_date, "origin": date_origin, "confidence": anchor_confidence}
        rejected_candidates = []
    anchor: dict[str, Any] = {
        "source_id": str(source.get("source_id") or ""),
        "source_type": source_type,
        "document_kind": str(source.get("document_kind") or ""),
        "date": event_date,
        "title": str(source.get("title") or ""),
        "reliability_level": str((source.get("source_reliability") or {}).get("level") or ""),
        "date_origin": date_origin,
        "anchor_confidence": anchor_confidence,
        "date_choice_reason": f"selected_{date_origin}",
    }
    if date_range is not None:
        anchor["date_range"] = date_range
    if date_candidates:
        anchor["date_candidates"] = ranked_candidates
    if rejected_candidates:
        anchor["rejected_date_candidates"] = rejected_candidates
    if source_date and source_date != event_date:
        anchor["source_recorded_date"] = source_date
    if calendar is not None:
        timezone_resolution = str(calendar.get("timezone_resolution") or "")
        if timezone_resolution:
            anchor["calendar_timezone_resolution"] = timezone_resolution
            if timezone_resolution == "invalid_tzid":
                anchor["calendar_timezone_degraded"] = True
                anchor["calendar_tzid"] = str(calendar.get("dtstart_tzid") or calendar.get("dtend_tzid") or "")
    return anchor


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
    "_calendar_semantics",
    "_chronology_anchor_for_source",
    "_chronology_text",
    "_date_range_from_text",
    "_event_date_from_text",
    "_ical_field_params",
    "_ical_to_iso",
    "_meeting_event_date",
]
