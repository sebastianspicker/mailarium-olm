# mypy: disable-error-code=name-defined
# pylint: disable=too-many-branches,too-many-locals,too-many-statements


# pylint: disable=E0602  # cross-module names injected by compatibility facade
"""Split multi-source case-bundle helpers (multi_source_case_bundle_chronology)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

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
    _date_candidates_from_text,
    _iso_date_from_eu_text,
)


def _chronology_text(source: dict[str, Any]) -> str:
    """Extract concatenated text from a source for chronology analysis.

    Args:
        source: Dictionary containing source data with title, snippet, searchable_text, etc.

    Returns:
        A space-joined string of all available text fields from the source and its documentary support.
    """
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
    """Extract a date range from text using ISO or European date range patterns.

    Args:
        text: The text to search for date range patterns.

    Returns:
        Dictionary with 'start' and 'end' ISO date strings, or None if no valid range found.
        Swaps start and end if start > end to ensure chronological order.
    """
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
    """Extract the first date candidate from text.

    Args:
        text: The text to search for dates.

    Returns:
        The first ISO date string found in the text, or empty string if none found.
    """
    candidates = _date_candidates_from_text(text)
    return candidates[0] if candidates else ""


def _ical_field_params(line: str) -> dict[str, str]:
    """Extract parameters from an iCalendar field line.

    Args:
        line: A string containing an iCalendar field with optional parameters.

    Returns:
        Dictionary mapping parameter keys (uppercase) to their values.
        Only includes parameters with both key and value present.
    """
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
    """Convert an iCalendar datetime string to ISO format with timezone resolution.

    Args:
        value: The iCalendar datetime string (e.g., '20240115T143000Z' or '20240115').
        tzid: Optional timezone ID for resolving non-UTC datetimes.

    Returns:
        Tuple of (iso_datetime_string, timezone_resolution) where resolution is one of:
        'utc', 'resolved_tzid', 'invalid_tzid', 'floating', 'date_only', or 'unparseable'.
    """
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
            except Exception:  # pylint: disable=broad-exception-caught
                return f"{year}-{month}-{day}T{hour}:{minute}:{second or '00'}", "invalid_tzid"
        return f"{year}-{month}-{day}T{hour}:{minute}:{second or '00'}", "floating"
    return f"{year}-{month}-{day}", "date_only"


def _calendar_semantics(source: dict[str, Any]) -> dict[str, Any] | None:
    """Extract or derive calendar semantics from a source with iCalendar data.

    Args:
        source: Dictionary containing source data with optional calendar_semantics.

    Returns:
        Dictionary with parsed calendar field data (dtstart, dtend, attendees, timezone info,
        schedule signals, etc.), or None if not a calendar format source.
    """
    explicit = source.get("calendar_semantics")
    if isinstance(explicit, dict) and explicit:
        return explicit
    if not _is_calendar_source(source):
        return None
    text = _chronology_text(source)
    fields, params = _ical_fields(text)
    timing = _calendar_timing(fields, params)
    signals = _calendar_signals(fields, timing, text)
    return _calendar_payload(fields, timing, signals)


def _is_calendar_source(source: dict[str, Any]) -> bool:
    documentary = cast(dict[str, Any], source.get("documentary_support") or {})
    profile = documentary.get("format_profile")
    return isinstance(profile, dict) and str(profile.get("format_family") or "") == "calendar"


def _ical_fields(text: str) -> tuple[dict[str, list[str]], dict[str, list[dict[str, str]]]]:
    fields: dict[str, list[str]] = {}
    params: dict[str, list[dict[str, str]]] = {}
    for match in _ICAL_FIELD_RE.finditer(text):
        _append_ical_field(fields, params, match.group(1).upper(), match.group(2), match.group(0))
    return fields, params


def _append_ical_field(
    fields: dict[str, list[str]], params: dict[str, list[dict[str, str]]], key: str, raw_value: str, raw_line: str
) -> None:
    value = " ".join(str(raw_value or "").split()).strip()
    if not value or value in fields.setdefault(key, []):
        return
    fields[key].append(value)
    params.setdefault(key, []).append(_ical_field_params(raw_line))


def _field_value(fields: dict[str, list[str]], key: str) -> str:
    values = fields.get(key, [])
    return values[0] if values else ""


def _field_tzid(params: dict[str, list[dict[str, str]]], key: str) -> str:
    entries = params.get(key, [])
    return str(entries[0].get("TZID") or "") if entries else ""


def _calendar_timing(fields: dict[str, list[str]], params: dict[str, list[dict[str, str]]]) -> dict[str, str]:
    start_tzid, end_tzid, recurrence_tzid = (_field_tzid(params, key) for key in ("DTSTART", "DTEND", "RECURRENCE-ID"))
    start, start_resolution = _ical_to_iso(_field_value(fields, "DTSTART"), tzid=start_tzid)
    end, end_resolution = _ical_to_iso(_field_value(fields, "DTEND"), tzid=end_tzid)
    recurrence, recurrence_resolution = _ical_to_iso(_field_value(fields, "RECURRENCE-ID"), tzid=recurrence_tzid)
    return {
        "dtstart": start,
        "dtend": end,
        "recurrence_id": recurrence,
        "dtstart_tzid": start_tzid,
        "dtend_tzid": end_tzid,
        "recurrence_tzid": recurrence_tzid,
        "dtstart_timezone_resolution": start_resolution,
        "dtend_timezone_resolution": end_resolution,
        "recurrence_timezone_resolution": recurrence_resolution,
        "timezone_resolution": _timezone_resolution(start_resolution, end_resolution, recurrence_resolution),
    }


def _timezone_resolution(*resolutions: str) -> str:
    available = set(resolutions) - {""}
    return next((value for value in ("invalid_tzid", "resolved_tzid", "utc", "floating", "date_only") if value in available), "")


def _calendar_signals(fields: dict[str, list[str]], timing: dict[str, str], text: str) -> dict[str, Any]:
    status, method, sequence, lowered = (
        _field_value(fields, "STATUS"),
        _field_value(fields, "METHOD"),
        _field_value(fields, "SEQUENCE"),
        text.lower(),
    )
    cancelled = (
        status.upper() == "CANCELLED"
        or method.upper() == "CANCEL"
        or any(token in lowered for token in ("abgesagt", "storniert", "cancelled", "canceled"))
    )
    updated = (
        bool(timing["recurrence_id"])
        or (sequence.isdigit() and int(sequence) > 0)
        or any(token in lowered for token in ("aktualisiert", "update", "geaendert", "geändert"))
    )
    return {
        "status": status,
        "method": method,
        "sequence": sequence,
        "cancellation_signal": cancelled,
        "update_signal": updated,
        "schedule_signal": "cancellation" if cancelled else "update" if updated else "invite",
    }


def _calendar_payload(fields: dict[str, list[str]], timing: dict[str, str], signals: dict[str, Any]) -> dict[str, Any]:
    attendees = list(dict.fromkeys(fields.get("ATTENDEE", [])))
    return {
        "calendar_summary": _field_value(fields, "SUMMARY"),
        **timing,
        "location": _field_value(fields, "LOCATION"),
        "organizer": _field_value(fields, "ORGANIZER"),
        "attendees": attendees,
        "attendee_count": len(attendees),
        **signals,
        "uid": _field_value(fields, "UID"),
        "description_preview": " ".join(_field_value(fields, "DESCRIPTION").split())[:240],
        "field_count": sum(len(values) for values in fields.values()),
    }


def _meeting_event_date(source: dict[str, Any]) -> str:
    """Extract the meeting event date from a source's snippet or provenance.

    Args:
        source: Dictionary containing source data with snippet and provenance.

    Returns:
        The meeting start date string if found in snippet metadata, otherwise empty string.
        Looks for markers like 'OPFMeetingStartDate=', 'startTime=', or 'start='.
    """
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


def _spreadsheet_semantics(source: dict[str, Any]) -> dict[str, Any] | None:
    """Extract time-record spreadsheet semantics from source text."""

    explicit = source.get("spreadsheet_semantics")
    if isinstance(explicit, dict) and explicit:
        return explicit
    if not _is_chronology_spreadsheet(source):
        return None
    return _chronology_spreadsheet_payload(_chronology_text(source))


def _is_chronology_spreadsheet(source: dict[str, Any]) -> bool:
    if str(source.get("source_type") or "") != "time_record":
        return False
    documentary = cast(dict[str, Any], source.get("documentary_support") or {})
    profile = documentary.get("format_profile")
    return isinstance(profile, dict) and str(profile.get("format_family") or "") == "spreadsheet"


def _chronology_spreadsheet_payload(text: str) -> dict[str, Any]:
    return {
        "record_type": "generic_time_record",
        "date_range": _date_range_from_text(text),
        "explicit_dates": list(dict.fromkeys(match.group(1) for match in _ISO_DATE_RE.finditer(text))),
        "month_labels": sorted({match.group(1).lower() for match in _MONTH_LABEL_RE.finditer(text)}),
        "sheet_names": _chronology_sheet_names(text),
    }


def _chronology_sheet_names(text: str) -> list[str]:
    return list(dict.fromkeys(match.group(1).strip() for match in _SHEET_NAME_RE.finditer(text) if match.group(1).strip()))


def _chronology_anchor_for_source(source: dict[str, Any]) -> dict[str, Any] | None:
    """Create a chronology anchor for a source based on its date information.

    Args:
        source: Dictionary containing source data with dates, type, provenance, etc.

    Returns:
        Dictionary with chronology anchor information including source_id, source_type,
        date, reliability_level, date_origin, anchor_confidence, date_candidates,
        rejected_date_candidates, and optional date_range. Returns None if no event date found.
    """
    context = _anchor_context(source)
    _add_meeting_candidate(context, source)
    _add_calendar_candidate(context, source)
    _add_document_candidates(context, source)
    return _finalize_anchor(context, source)


def _anchor_context(source: dict[str, Any]) -> dict[str, Any]:
    source_date = str(source.get("date") or "").strip()
    return {
        "source_type": str(source.get("source_type") or ""),
        "source_date": source_date,
        "text": _chronology_text(source),
        "event_date": source_date,
        "origin": "source_timestamp",
        "confidence": "medium",
        "candidates": [],
        "date_range": None,
        "calendar": _calendar_semantics(source),
        "spreadsheet": _spreadsheet_semantics(source),
    }


def _add_meeting_candidate(context: dict[str, Any], source: dict[str, Any]) -> None:
    if context["source_type"] != "meeting_note":
        return
    date_value = _meeting_event_date(source)
    if date_value:
        _select_candidate(context, date_value, "meeting_metadata", "high")


def _add_calendar_candidate(context: dict[str, Any], source: dict[str, Any]) -> None:
    calendar = context["calendar"]
    date_value = str(calendar.get("dtstart") or "") if isinstance(calendar, dict) else ""
    if date_value:
        confidence = "medium" if str(calendar.get("timezone_resolution") or "") == "invalid_tzid" else "high"
        _select_candidate(context, date_value, "calendar_dtstart", confidence)


def _add_document_candidates(context: dict[str, Any], source: dict[str, Any]) -> None:
    if context["source_type"] not in {"formal_document", "note_record", "time_record", "participation_record", "attachment"}:
        return
    detected_range = _document_date_range(context)
    if detected_range and context["source_type"] == "time_record":
        _add_time_range_candidates(context, detected_range)
        return
    for value in _date_candidates_from_text(str(context["text"])):
        _select_candidate(context, value, "document_text", "medium")


def _document_date_range(context: dict[str, Any]) -> dict[str, Any] | None:
    spreadsheet = context["spreadsheet"]
    if (
        context["source_type"] == "time_record"
        and isinstance(spreadsheet, dict)
        and isinstance(spreadsheet.get("date_range"), dict)
    ):
        return cast(dict[str, Any], spreadsheet["date_range"])
    return _date_range_from_text(str(context["text"]))


def _add_time_range_candidates(context: dict[str, Any], date_range: dict[str, Any]) -> None:
    normalized = {"start": str(date_range.get("start") or ""), "end": str(date_range.get("end") or "")}
    context["date_range"] = normalized
    _select_candidate(context, normalized["start"], "time_record_range_start", "high")
    if normalized["end"]:
        _select_candidate(context, normalized["end"], "time_record_range_end", "medium")


def _select_candidate(context: dict[str, Any], date_value: str, origin: str, confidence: str) -> None:
    if not date_value:
        return
    cast(list[dict[str, str]], context["candidates"]).append({"date": date_value, "origin": origin, "confidence": confidence})
    context.update({"event_date": date_value, "origin": origin, "confidence": confidence})


def _finalize_anchor(context: dict[str, Any], source: dict[str, Any]) -> dict[str, Any] | None:
    if not context["event_date"]:
        return None
    _append_source_date(context)
    candidates = [candidate for candidate in cast(list[dict[str, str]], context["candidates"]) if candidate["date"]]
    best_index, best = _best_candidate(candidates, context)
    context.update({"event_date": best["date"], "origin": best["origin"], "confidence": best["confidence"]})
    return _anchor_payload(context, source, candidates, best_index)


def _append_source_date(context: dict[str, Any]) -> None:
    source_date = str(context["source_date"])
    candidates = cast(list[dict[str, str]], context["candidates"])
    if source_date and not any(item["date"] == source_date for item in candidates):
        candidates.append({"date": source_date, "origin": "source_timestamp", "confidence": "medium"})


def _best_candidate(candidates: list[dict[str, str]], context: dict[str, Any]) -> tuple[int, dict[str, str]]:
    if not candidates:
        return -1, {
            "date": str(context["event_date"]),
            "origin": str(context["origin"]),
            "confidence": str(context["confidence"]),
        }
    return max(enumerate(candidates), key=_candidate_sort_key)


def _candidate_sort_key(indexed: tuple[int, dict[str, str]]) -> tuple[int, int, int, int]:
    index, candidate = indexed
    confidence = {"high": 3, "medium": 2, "low": 1}.get(candidate["confidence"], 0)
    precision = 2 if "T" in candidate["date"] else 1
    return int(_DATE_ORIGIN_PRIORITY.get(candidate["origin"], 0)), confidence, precision, -index


def _anchor_payload(
    context: dict[str, Any], source: dict[str, Any], candidates: list[dict[str, str]], best_index: int
) -> dict[str, Any]:
    origin, event_date = str(context["origin"]), str(context["event_date"])
    reliability = cast(dict[str, Any], source.get("source_reliability") or {})
    anchor: dict[str, Any] = {
        "source_id": str(source.get("source_id") or ""),
        "source_type": context["source_type"],
        "document_kind": str(source.get("document_kind") or ""),
        "date": event_date,
        "title": str(source.get("title") or ""),
        "reliability_level": str(reliability.get("level") or ""),
        "date_origin": origin,
        "anchor_confidence": context["confidence"],
        "date_choice_reason": f"selected_{origin}",
    }
    _anchor_optional_fields(anchor, context, candidates, best_index, event_date)
    return anchor


def _anchor_optional_fields(
    anchor: dict[str, Any], context: dict[str, Any], candidates: list[dict[str, str]], best_index: int, event_date: str
) -> None:
    if context["date_range"]:
        anchor["date_range"] = context["date_range"]
    if candidates:
        anchor["date_candidates"] = candidates
    rejected = [
        {**candidate, "rejected_reason": "lower_rank_than_selected"}
        for index, candidate in enumerate(candidates)
        if index != best_index
    ]
    if rejected:
        anchor["rejected_date_candidates"] = rejected
    if context["source_date"] and context["source_date"] != event_date:
        anchor["source_recorded_date"] = context["source_date"]
    _anchor_calendar_fields(anchor, context["calendar"])


def _anchor_calendar_fields(anchor: dict[str, Any], calendar: Any) -> None:
    if not isinstance(calendar, dict) or not calendar.get("timezone_resolution"):
        return
    resolution = str(calendar["timezone_resolution"])
    anchor["calendar_timezone_resolution"] = resolution
    if resolution == "invalid_tzid":
        anchor["calendar_timezone_degraded"] = True
        anchor["calendar_tzid"] = str(calendar.get("dtstart_tzid") or calendar.get("dtend_tzid") or "")


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
