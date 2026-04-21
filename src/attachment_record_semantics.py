"""Structured semantics derived from durable attachment metadata and text."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .attachment_extractor import attachment_format_profile, extraction_quality_profile

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
_DATE_RANGE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\s*(?:to|through|until|bis|–|-)\s*(\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)
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


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def _attachment_filename(attachment: dict[str, Any]) -> str:
    return str(attachment.get("filename") or attachment.get("name") or "").strip()


def _attachment_text(attachment: dict[str, Any], *, snippet: str = "") -> str:
    for value in (
        attachment.get("extracted_text"),
        attachment.get("text_preview"),
        snippet,
    ):
        raw = str(value or "")
        if _compact(raw):
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
    format_label = str(format_profile.get("format_label") or "source").strip()
    handling_mode = str(format_profile.get("handling_mode") or "").strip()
    support_level = str(format_profile.get("support_level") or "").strip()
    if support_level == "unsupported":
        return (
            f"{format_label} is not currently supported for reliable extraction; keep it as a visible reference "
            "and review the original file directly."
        )
    if evidence_strength == "strong_text" and extraction_state == "text_extracted":
        if handling_mode == "flattened_tabular_text":
            return f"{format_label} text is usable, but sheet structure and formulas were flattened during extraction."
        if handling_mode == "calendar_text_flattened":
            return (
                f"{format_label} text is usable, but richer calendar structure was flattened and should be checked "
                "against the original file when timing detail matters."
            )
        if source_type == "note_record":
            return "Extracted note text can support chronology, summary comparison, and follow-up directly."
        if source_type == "time_record":
            return "Extracted time-record text can support chronology and attendance follow-up directly."
        if source_type == "participation_record":
            return "Extracted participation-record text can support process and consultation follow-up directly."
        if source_type == "formal_document":
            return "Native extracted document text can support chronology and exhibit follow-up directly."
        return "Extracted attachment text can support downstream follow-up directly."
    if evidence_strength == "strong_text" and ocr_used:
        return "OCR-recovered text is usable, but the original page image should be checked before relying on fine wording."
    if extraction_state in {"ocr_failed", "ocr_failure", "binary_only", "image_embedding_only", "extraction_failed"}:
        return "Treat this source as a weak documentary reference until the original file is reviewed manually."
    if extraction_quality.get("manual_review_required"):
        return "Manual review is still required before treating this source as strong documentary proof."
    return "Review the original file before treating this source as strong documentary proof."


def documentary_support_for_attachment(
    attachment: dict[str, Any],
    *,
    source_type: str,
    snippet: str = "",
) -> dict[str, Any]:
    filename = _attachment_filename(attachment)
    mime_type = str(attachment.get("mime_type") or "")
    extraction_state = str(attachment.get("extraction_state") or "")
    evidence_strength = str(attachment.get("evidence_strength") or "")
    ocr_used = bool(attachment.get("ocr_used"))
    text_preview = _compact(attachment.get("text_preview") or _attachment_text(attachment, snippet=snippet))
    text_available = bool(_compact(attachment.get("extracted_text")) or text_preview or _compact(snippet))
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


def _chronology_text(*, title: str, snippet: str, text_preview: str, extracted_text: str) -> str:
    return "\n".join(part for part in (title, snippet, text_preview, extracted_text[:4000]) if part)


def _date_range_from_text(text: str) -> dict[str, str] | None:
    match = _DATE_RANGE_RE.search(text)
    if not match:
        return None
    start, end = match.group(1), match.group(2)
    if start > end:
        start, end = end, start
    return {"start": start, "end": end}


def _ical_to_iso(value: str) -> str:
    compact = _compact(value)
    match = _ICAL_DATETIME_RE.search(compact)
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
    documentary_support = documentary_support_for_attachment(
        attachment,
        source_type="time_record",
        snippet=snippet,
    )
    format_profile = dict(documentary_support.get("format_profile") or {})
    if str(format_profile.get("format_family") or "") != "spreadsheet":
        return None
    chronology_text = _chronology_text(
        title=title,
        snippet=snippet,
        text_preview=str(documentary_support.get("text_preview") or ""),
        extracted_text=str(attachment.get("extracted_text") or ""),
    )
    explicit_dates = [match.group(1) for match in _ISO_DATE_RE.finditer(chronology_text)]
    date_range = _date_range_from_text(chronology_text)
    month_labels = sorted({match.group(1).lower() for match in _MONTH_LABEL_RE.finditer(chronology_text)})
    sheet_names = [match.group(1).strip() for match in _SHEET_NAME_RE.finditer(chronology_text) if match.group(1).strip()]
    lower_text = chronology_text.lower()
    record_type = "generic_time_record"
    if any(token in lower_text for token in ("time system", "nova time")):
        record_type = "time system_export"
    elif "attendance" in lower_text:
        record_type = "attendance_export"
    elif any(token in lower_text for token in ("arbeitszeit", "timesheet", "time sheet", "zeiterfassung")):
        record_type = "time_tracking_export"
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


def calendar_semantics_for_attachment(
    attachment: dict[str, Any],
    *,
    title: str = "",
    snippet: str = "",
) -> dict[str, Any] | None:
    documentary_support = documentary_support_for_attachment(
        attachment,
        source_type="attachment",
        snippet=snippet,
    )
    format_profile = dict(documentary_support.get("format_profile") or {})
    if str(format_profile.get("format_family") or "") != "calendar":
        return None
    chronology_text = _chronology_text(
        title=title,
        snippet=snippet,
        text_preview=str(documentary_support.get("text_preview") or ""),
        extracted_text=str(attachment.get("extracted_text") or ""),
    )
    field_map: dict[str, list[str]] = {}
    for match in _ICAL_FIELD_RE.finditer(chronology_text):
        key = match.group(1).upper()
        value = _compact(match.group(2))
        field_map.setdefault(key, [])
        if value and value not in field_map[key]:
            field_map[key].append(value)
    attendees = list(dict.fromkeys(field_map.get("ATTENDEE", [])))
    dtstart = _ical_to_iso(field_map.get("DTSTART", [""])[0]) if field_map.get("DTSTART") else ""
    dtend = _ical_to_iso(field_map.get("DTEND", [""])[0]) if field_map.get("DTEND") else ""
    status = field_map.get("STATUS", [""])[0] if field_map.get("STATUS") else ""
    method = field_map.get("METHOD", [""])[0] if field_map.get("METHOD") else ""
    sequence = field_map.get("SEQUENCE", [""])[0] if field_map.get("SEQUENCE") else ""
    recurrence_id = _ical_to_iso(field_map.get("RECURRENCE-ID", [""])[0]) if field_map.get("RECURRENCE-ID") else ""
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
        "location": field_map.get("LOCATION", [""])[0] if field_map.get("LOCATION") else "",
        "organizer": field_map.get("ORGANIZER", [""])[0] if field_map.get("ORGANIZER") else "",
        "attendees": attendees,
        "attendee_count": len(attendees),
        "status": status,
        "method": method,
        "sequence": sequence,
        "uid": field_map.get("UID", [""])[0] if field_map.get("UID") else "",
        "recurrence_id": recurrence_id,
        "description_preview": _compact(description)[:240],
        "schedule_signal": schedule_signal,
        "cancellation_signal": cancellation_signal,
        "update_signal": update_signal,
        "field_count": sum(len(values) for values in field_map.values()),
    }


def weak_format_semantics_for_attachment(
    attachment: dict[str, Any],
    *,
    title: str = "",
    snippet: str = "",
) -> dict[str, Any] | None:
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
