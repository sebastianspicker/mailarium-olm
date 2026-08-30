"""Structured semantics derived from durable attachment metadata and text."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from mailarium.model.data_shapes import compact

from .attachment_profiles import attachment_format_profile, extraction_quality_profile

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
    "time system",
    "nova time",
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
_DATE_RANGE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\s*(?:to|through|until|bis|-)\s*(\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)
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


def _normalized_text(value: Any) -> str:
    """Normalize attachment text for stable classification and comparison."""
    return " ".join(str(value or "").lower().split())


def _attachment_filename(attachment: dict[str, Any]) -> str:
    """Return a normalized filename from mapping or object attachment records."""
    return str(attachment.get("filename") or attachment.get("name") or "").strip()


def _attachment_text(attachment: dict[str, Any], *, snippet: str = "") -> str:
    """Return the best extracted-text field available on an attachment record."""
    for value in (
        attachment.get("extracted_text"),
        attachment.get("text_preview"),
        snippet,
    ):
        raw = str(value or "")
        if compact(raw):
            return raw
    return ""


def _is_formal_document(filename: str, mime_type: str) -> bool:
    if Path(filename).suffix.lower() in _FORMAL_DOCUMENT_EXTENSIONS:
        return True
    normalized_mime = mime_type.lower()
    return any(marker in normalized_mime for marker in _FORMAL_DOCUMENT_MIME_MARKERS)


def attachment_source_type_hint(
    *,
    filename: str,
    mime_type: str,
    title: str = "",
    snippet: str = "",
    text: str = "",
) -> str:
    """Classify an attachment's source type from its metadata and content.

    Uses keyword matching on normalized filename, title, snippet, and text
    to categorize the attachment as time_record, participation_record,
    note_record, formal_document, or generic attachment.

    Args:
        filename: The attachment filename.
        mime_type: The attachment MIME type.
        title: Optional attachment title. Defaults to "".
        snippet: Optional content snippet. Defaults to "".
        text: Optional extracted text (first 4000 chars used). Defaults to "".

    Returns:
        A source type string: "time_record", "participation_record",
        "note_record", "formal_document", or "attachment".
    """
    classification_text = " ".join(
        part
        for part in (
            _normalized_text(filename),
            _normalized_text(title),
            _normalized_text(snippet),
            _normalized_text(text[:4000]),
        )
        if part
    )
    if any(keyword in classification_text for keyword in _TIME_RECORD_KEYWORDS):
        return "time_record"
    if any(keyword in classification_text for keyword in _PARTICIPATION_RECORD_KEYWORDS):
        return "participation_record"
    if any(keyword in classification_text for keyword in _NOTE_RECORD_KEYWORDS):
        return "note_record"
    if _is_formal_document(filename, mime_type):
        return "formal_document"
    return "attachment"


def attachment_review_recommendation(
    *,
    extraction_state: str,
    evidence_strength: str,
    ocr_used: bool,
    source_type: str,
    format_profile: dict[str, Any],
    extraction_quality: dict[str, Any],
) -> str:
    """Produce a human-readable review recommendation for an attachment.

    Evaluates extraction state, evidence strength, OCR usage, source type,
    format profile, and extraction quality to generate context-specific
    guidance for manual review.

    Args:
        extraction_state: The extraction state (e.g., "text_extracted", "ocr_failed").
        evidence_strength: The evidence strength classification.
        ocr_used: Whether OCR was used during extraction.
        source_type: The classified source type (e.g., "formal_document").
        format_profile: Format metadata dict with keys like format_label,
            handling_mode, and support_level.
        extraction_quality: Quality metadata dict, optionally including
            manual_review_required flag.

    Returns:
        A human-readable recommendation string for manual review.
    """
    format_label = str(format_profile.get("format_label") or "source").strip()
    handling_mode = str(format_profile.get("handling_mode") or "").strip()
    support_level = str(format_profile.get("support_level") or "").strip()
    if support_level == "unsupported":
        return (
            f"{format_label} is not currently supported for reliable extraction; keep it as a visible reference "
            "and review the original file directly."
        )
    if _is_native_extraction(evidence_strength, extraction_state):
        return _native_text_recommendation(format_label, handling_mode, source_type)
    if _is_ocr_extraction(evidence_strength, ocr_used):
        return "OCR-recovered text is usable, but the original page image should be checked before relying on fine wording."
    if extraction_state in {"ocr_failed", "ocr_failure", "binary_only", "image_embedding_only", "extraction_failed"}:
        return "Treat this source as a weak documentary reference until the original file is reviewed manually."
    if extraction_quality.get("manual_review_required"):
        return "Manual review is still required before treating this source as strong documentary proof."
    return "Review the original file before treating this source as strong documentary proof."


def _is_native_extraction(evidence_strength: str, extraction_state: str) -> bool:
    return evidence_strength == "strong_text" and extraction_state == "text_extracted"


def _is_ocr_extraction(evidence_strength: str, ocr_used: bool) -> bool:
    return evidence_strength == "strong_text" and ocr_used


def _native_text_recommendation(format_label: str, handling_mode: str, source_type: str) -> str:
    """Explain when native extraction is preferable to OCR-derived text."""
    by_handling_mode = {
        "flattened_tabular_text": (
            f"{format_label} text is usable, but sheet structure and formulas were flattened during extraction."
        ),
        "calendar_text_flattened": (
            f"{format_label} text is usable, but richer calendar structure was flattened and should be checked "
            "against the original file when timing detail matters."
        ),
    }
    by_source_type = {
        "note_record": "Extracted note text can support chronology, summary comparison, and follow-up directly.",
        "time_record": "Extracted time-record text can support chronology and attendance follow-up directly.",
        "participation_record": "Extracted participation-record text can support process and consultation follow-up directly.",
        "formal_document": "Native extracted document text can support chronology and exhibit follow-up directly.",
    }
    return by_handling_mode.get(handling_mode) or by_source_type.get(
        source_type, "Extracted attachment text can support downstream follow-up directly."
    )


def documentary_support_for_attachment(
    attachment: dict[str, Any],
    *,
    source_type: str,
    snippet: str = "",
) -> dict[str, Any]:
    """Build a documentary support summary for an attachment.

    Retrieves or computes format profile, extraction quality, and review
    recommendation for the given attachment, returning a structured
    dictionary with all documentary metadata.

    Args:
        attachment: The attachment dictionary with keys like mime_type,
            extraction_state, evidence_strength, ocr_used, text_preview,
            extracted_text, format_profile, extraction_quality, and
            review_recommendation.
        source_type: The classified source type string.
        snippet: Optional content snippet. Defaults to "".

    Returns:
        A dict with keys: filename, mime_type, text_available,
        evidence_strength, extraction_state, ocr_used, failure_reason,
        text_preview, format_profile, extraction_quality, and
        review_recommendation.
    """
    fields = _documentary_fields(attachment, snippet)
    filename = fields["filename"]
    mime_type = fields["mime_type"]
    extraction_state = fields["extraction_state"]
    evidence_strength = fields["evidence_strength"]
    ocr_used = fields["ocr_used"]
    text_preview = fields["text_preview"]
    text_available = fields["text_available"]
    format_profile = dict(attachment.get("format_profile") or {})
    if not format_profile:
        format_profile = attachment_format_profile(
            filename=filename,
            mime_type=mime_type,
            extraction_state=extraction_state,
            evidence_strength=evidence_strength,
            ocr_used=ocr_used,
            text_available=text_available,
        )
    extraction_quality = dict(attachment.get("extraction_quality") or {})
    if not extraction_quality:
        extraction_quality = extraction_quality_profile(
            extraction_state=extraction_state,
            evidence_strength=evidence_strength,
            ocr_used=ocr_used,
            format_profile=format_profile,
        )
    review_recommendation = str(attachment.get("review_recommendation") or "").strip()
    if not review_recommendation:
        review_recommendation = attachment_review_recommendation(
            extraction_state=extraction_state,
            evidence_strength=evidence_strength,
            ocr_used=ocr_used,
            source_type=source_type,
            format_profile=format_profile,
            extraction_quality=extraction_quality,
        )
    return {
        "filename": filename,
        "mime_type": mime_type,
        "text_available": text_available,
        "evidence_strength": evidence_strength,
        "extraction_state": extraction_state,
        "ocr_used": ocr_used,
        "failure_reason": str(attachment.get("failure_reason") or ""),
        "text_preview": text_preview,
        "format_profile": format_profile,
        "extraction_quality": extraction_quality,
        "review_recommendation": review_recommendation,
    }


def _documentary_fields(attachment: dict[str, Any], snippet: str) -> dict[str, Any]:
    """Derive document-type and evidentiary fields from attachment metadata."""
    text_preview = compact(attachment.get("text_preview") or _attachment_text(attachment, snippet=snippet))
    return {
        "filename": _attachment_filename(attachment),
        "mime_type": str(attachment.get("mime_type") or ""),
        "extraction_state": str(attachment.get("extraction_state") or ""),
        "evidence_strength": str(attachment.get("evidence_strength") or ""),
        "ocr_used": bool(attachment.get("ocr_used")),
        "text_preview": text_preview,
        "text_available": bool(compact(attachment.get("extracted_text")) or text_preview or compact(snippet)),
    }


def _chronology_text(*, title: str, snippet: str, text_preview: str, extracted_text: str) -> str:
    """Join non-empty text fields before date extraction."""
    return "\n".join(part for part in (title, snippet, text_preview, extracted_text[:4000]) if part)


def _date_range_from_text(text: str) -> dict[str, str] | None:
    """Return the earliest and latest parseable dates found in text."""
    match = _DATE_RANGE_RE.search(text)
    if not match:
        return None
    start, end = match.group(1), match.group(2)
    if start > end:
        start, end = end, start
    return {"start": start, "end": end}


def _ical_to_iso(value: str) -> str:
    """Convert an iCalendar date value to normalized ISO text when possible."""
    compacted = compact(value)
    match = _ICAL_DATETIME_RE.search(compacted)
    if not match:
        return ""
    year, month, day, hour, minute, second = match.groups()
    if hour and minute:
        return f"{year}-{month}-{day}T{hour}:{minute}:{second or '00'}"
    return f"{year}-{month}-{day}"


def spreadsheet_semantics_for_attachment(
    attachment: dict[str, Any],
    *,
    title: str = "",
    snippet: str = "",
) -> dict[str, Any] | None:
    """Analyze spreadsheet semantics for an attachment.

    Extracts date signals, sheet names, month labels, and record type
    from spreadsheet attachments. Returns None if the attachment is not
    a spreadsheet.

    Args:
        attachment: The attachment dictionary.
        title: Optional attachment title. Defaults to "".
        snippet: Optional content snippet. Defaults to "".

    Returns:
        A dict with spreadsheet semantics (record_type, sheet_names,
        sheet_count, explicit_dates, date_range, month_labels,
        date_signal_strength, structure_signal), or None if not a
        spreadsheet.
    """
    documentary_support = documentary_support_for_attachment(
        attachment,
        source_type="time_record",
        snippet=snippet,
    )
    format_profile = dict(documentary_support.get("format_profile") or {})
    if str(format_profile.get("format_family") or "") != "spreadsheet":
        return None
    chronology_text = _attachment_chronology_text(attachment, documentary_support, title, snippet)
    explicit_dates = [match.group(1) for match in _ISO_DATE_RE.finditer(chronology_text)]
    date_range = _date_range_from_text(chronology_text)
    month_labels = sorted({match.group(1).lower() for match in _MONTH_LABEL_RE.finditer(chronology_text)})
    sheet_names = [match.group(1).strip() for match in _SHEET_NAME_RE.finditer(chronology_text) if match.group(1).strip()]
    record_type = _spreadsheet_record_type(chronology_text)
    return {
        "record_type": record_type,
        "sheet_names": sheet_names,
        "sheet_count": len(sheet_names),
        "explicit_dates": list(dict.fromkeys(explicit_dates)),
        "date_range": date_range,
        "month_labels": month_labels,
        "date_signal_strength": "range" if date_range else "dates" if explicit_dates else "weak",
        "structure_signal": "sheeted" if sheet_names else "flattened_rows_only",
    }


def _attachment_chronology_text(attachment: dict[str, Any], support: dict[str, Any], title: str, snippet: str) -> str:
    """Collect attachment fields that may carry chronology signals."""
    return _chronology_text(
        title=title,
        snippet=snippet,
        text_preview=str(support.get("text_preview") or ""),
        extracted_text=str(attachment.get("extracted_text") or ""),
    )


def _spreadsheet_record_type(text: str) -> str:
    """Infer a spreadsheet record type from headers and filename hints."""
    lower_text = text.lower()
    if any(token in lower_text for token in ("time system", "nova time")):
        return "time system_export"
    if "attendance" in lower_text:
        return "attendance_export"
    if any(token in lower_text for token in ("arbeitszeit", "timesheet", "time sheet", "zeiterfassung")):
        return "time_tracking_export"
    return "generic_time_record"


def calendar_semantics_for_attachment(
    attachment: dict[str, Any],
    *,
    title: str = "",
    snippet: str = "",
) -> dict[str, Any] | None:
    """Analyze calendar/iCal semantics for an attachment.

    Parses iCalendar fields (DTSTART, DTEND, ATTENDEE, ORGANIZER, STATUS,
    etc.) from the attachment text and extracts structured calendar metadata.
    Returns None if the attachment is not a calendar.

    Args:
        attachment: The attachment dictionary.
        title: Optional attachment title. Defaults to "".
        snippet: Optional content snippet. Defaults to "".

    Returns:
        A dict with calendar semantics (calendar_summary, dtstart, dtend,
        location, organizer, attendees, attendee_count, status, method,
        sequence, uid, recurrence_id, description_preview, schedule_signal,
        cancellation_signal, update_signal, field_count), or None if not a
        calendar.
    """
    documentary_support = documentary_support_for_attachment(
        attachment,
        source_type="attachment",
        snippet=snippet,
    )
    format_profile = dict(documentary_support.get("format_profile") or {})
    if str(format_profile.get("format_family") or "") != "calendar":
        return None
    chronology_text = _attachment_chronology_text(attachment, documentary_support, title, snippet)
    return _calendar_semantics_payload(_ical_field_map(chronology_text), chronology_text)


def _ical_field_map(text: str) -> dict[str, list[str]]:
    """Parse unfolded iCalendar lines into a multi-value field mapping."""
    field_map: dict[str, list[str]] = {}
    for match in _ICAL_FIELD_RE.finditer(text):
        key, value = match.group(1).upper(), compact(match.group(2))
        field_map.setdefault(key, [])
        if value and value not in field_map[key]:
            field_map[key].append(value)
    return field_map


def _ical_first(field_map: dict[str, list[str]], key: str) -> str:
    """Return the first non-empty value for an iCalendar field."""
    return field_map.get(key, [""])[0]


def _calendar_semantics_payload(field_map: dict[str, list[str]], text: str) -> dict[str, Any]:
    """Derive normalized event timing and participants from iCalendar fields."""
    status, method, sequence = (_ical_first(field_map, key) for key in ("STATUS", "METHOD", "SEQUENCE"))
    recurrence_id = _ical_to_iso(_ical_first(field_map, "RECURRENCE-ID"))
    cancellation, update = _calendar_signals(status, method, sequence, recurrence_id, text)
    attendees = list(dict.fromkeys(field_map.get("ATTENDEE", [])))
    return {
        "calendar_summary": _ical_first(field_map, "SUMMARY"),
        "dtstart": _ical_to_iso(_ical_first(field_map, "DTSTART")),
        "dtend": _ical_to_iso(_ical_first(field_map, "DTEND")),
        "location": _ical_first(field_map, "LOCATION"),
        "organizer": _ical_first(field_map, "ORGANIZER"),
        "attendees": attendees,
        "attendee_count": len(attendees),
        "status": status,
        "method": method,
        "sequence": sequence,
        "uid": _ical_first(field_map, "UID"),
        "recurrence_id": recurrence_id,
        "description_preview": compact(_ical_first(field_map, "DESCRIPTION"))[:240],
        "schedule_signal": "cancellation" if cancellation else "update" if update else "invite",
        "cancellation_signal": cancellation,
        "update_signal": update,
        "field_count": sum(len(values) for values in field_map.values()),
    }


def _calendar_signals(status: str, method: str, sequence: str, recurrence_id: str, text: str) -> tuple[bool, bool]:
    """Extract structured calendar signals from an attachment record."""
    normalized = text.lower()
    cancellation = (
        status.upper() == "CANCELLED"
        or method.upper() == "CANCEL"
        or any(token in normalized for token in ("abgesagt", "storniert", "cancelled", "canceled"))
    )
    update = bool(
        recurrence_id
        or (sequence.isdigit() and int(sequence) > 0)
        or any(token in normalized for token in ("aktualisiert", "update", "geaendert", "geändert"))
    )
    return cancellation, update


def weak_format_semantics_for_attachment(
    attachment: dict[str, Any],
    *,
    title: str = "",
    snippet: str = "",
) -> dict[str, Any] | None:
    """Analyze weak-format recovery semantics for an attachment.

    Determines the recovery mode for attachments that could not be fully
    extracted (e.g., flattened tabular text, flattened calendar text,
    OCR-not-available images, unsupported formats). Returns None if the
    attachment does not fall into a weak-format recovery category.

    Args:
        attachment: The attachment dictionary.
        title: Optional attachment title. Defaults to "".
        snippet: Optional content snippet. Defaults to "".

    Returns:
        A dict with recovery_mode, original_format_family, and
        support_level, or None if strong extraction is available.
    """
    documentary_support = documentary_support_for_attachment(
        attachment,
        source_type=attachment_source_type_hint(
            filename=_attachment_filename(attachment),
            mime_type=str(attachment.get("mime_type") or ""),
            title=title,
            snippet=snippet,
            text=_attachment_text(attachment, snippet=snippet),
        ),
        snippet=snippet,
    )
    format_profile = dict(documentary_support.get("format_profile") or {})
    handling_mode = str(format_profile.get("handling_mode") or "")
    support_level = str(format_profile.get("support_level") or "")
    extraction_state = str(attachment.get("extraction_state") or "")
    format_family = str(format_profile.get("format_family") or "unknown")
    if handling_mode == "flattened_tabular_text":
        return {
            "recovery_mode": "flattened_tabular_text",
            "original_format_family": format_family,
            "support_level": support_level,
        }
    if handling_mode == "calendar_text_flattened":
        return {
            "recovery_mode": "calendar_text_flattened",
            "original_format_family": format_family,
            "support_level": support_level,
        }
    if extraction_state in {"binary_only", "image_embedding_only"} and format_family in {"image", "pdf"}:
        return {
            "recovery_mode": "ocr_not_available",
            "original_format_family": format_family,
            "support_level": support_level,
        }
    if support_level == "unsupported":
        return {
            "recovery_mode": "unsupported_format",
            "original_format_family": format_family,
            "support_level": support_level,
        }
    return None


def enrich_attachment_record(
    attachment: dict[str, Any],
    *,
    title: str = "",
    snippet: str = "",
) -> dict[str, Any]:
    """Enrich an attachment record with derived semantics.

    Computes source type, documentary support, and format-specific
    semantics (spreadsheet, calendar, or weak format) and merges them
    into a single enriched attachment dictionary.

    Args:
        attachment: The attachment dictionary to enrich.
        title: Optional attachment title. Defaults to "".
        snippet: Optional content snippet. Defaults to "".

    Returns:
        An enriched copy of the attachment dict with added keys:
        source_type, documentary_support, and optionally
        spreadsheet_semantics, calendar_semantics, or
        weak_format_semantics.
    """
    enriched = dict(attachment)
    filename = _attachment_filename(enriched)
    mime_type = str(enriched.get("mime_type") or "")
    text = _attachment_text(enriched, snippet=snippet)
    source_type_hint = str(enriched.get("source_type_hint") or "")
    if not source_type_hint:
        source_type_hint = attachment_source_type_hint(
            filename=filename,
            mime_type=mime_type,
            title=title,
            snippet=snippet,
            text=text,
        )
    enriched["source_type_hint"] = source_type_hint
    if not isinstance(enriched.get("documentary_support"), dict):
        enriched["documentary_support"] = documentary_support_for_attachment(
            enriched,
            source_type=source_type_hint,
            snippet=snippet,
        )
    if not isinstance(enriched.get("spreadsheet_semantics"), dict):
        spreadsheet_semantics = spreadsheet_semantics_for_attachment(
            enriched,
            title=title,
            snippet=snippet,
        )
        if spreadsheet_semantics is not None:
            enriched["spreadsheet_semantics"] = spreadsheet_semantics
    if not isinstance(enriched.get("calendar_semantics"), dict):
        calendar_semantics = calendar_semantics_for_attachment(
            enriched,
            title=title,
            snippet=snippet,
        )
        if calendar_semantics is not None:
            enriched["calendar_semantics"] = calendar_semantics
    if not isinstance(enriched.get("weak_format_semantics"), dict):
        weak_semantics = weak_format_semantics_for_attachment(
            enriched,
            title=title,
            snippet=snippet,
        )
        if weak_semantics is not None:
            enriched["weak_format_semantics"] = weak_semantics
    return enriched
