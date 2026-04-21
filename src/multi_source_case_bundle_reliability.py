# mypy: disable-error-code=name-defined
"""Split multi-source case-bundle helpers (multi_source_case_bundle_reliability)."""

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


def _attachment_source_type(candidate: dict[str, Any], attachment: dict[str, Any]) -> str:
    explicit_hint = str(attachment.get("source_type_hint") or "").strip()
    if explicit_hint in _DECLARED_SOURCE_TYPES:
        return explicit_hint
    classification_text = " ".join(
        part
        for part in (
            _normalized_text(attachment.get("filename")),
            _normalized_text(candidate.get("subject")),
            _normalized_text(candidate.get("snippet")),
        )
        if part
    )
    if any(keyword in classification_text for keyword in _TIME_RECORD_KEYWORDS):
        return "time_record"
    if any(keyword in classification_text for keyword in _PARTICIPATION_RECORD_KEYWORDS):
        return "participation_record"
    if any(keyword in classification_text for keyword in _NOTE_RECORD_KEYWORDS):
        return "note_record"
    if _is_formal_document(attachment):
        return "formal_document"
    return "attachment"


def _attachment_document_kind(source_type: str) -> str:
    if source_type == "attachment":
        return "attachment"
    if source_type == "formal_document":
        return "attached_document"
    return f"attached_{source_type}"


def _attachment_reliability_basis_prefix(source_type: str) -> str:
    return source_type


def _source_review_recommendation(
    *,
    extraction_state: str,
    evidence_strength: str,
    ocr_used: bool,
    source_type: str,
    format_profile: dict[str, Any] | None = None,
    extraction_quality: dict[str, Any] | None = None,
) -> str:
    format_profile = format_profile if isinstance(format_profile, dict) else {}
    extraction_quality = extraction_quality if isinstance(extraction_quality, dict) else {}
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
    if extraction_state in {"ocr_failed", "extraction_failed", "binary_only", "image_embedding_only"}:
        return "Treat this source as a weak documentary reference until the original file is reviewed manually."
    if extraction_quality.get("manual_review_required"):
        return "Manual review is still required before treating this source as strong documentary proof."
    return "Review the original file before treating this source as strong documentary proof."


def _source_reliability_for_chat_log(chat_log: dict[str, Any]) -> dict[str, Any]:
    participants = [str(item) for item in chat_log.get("participants", []) if str(item).strip()]
    parsed_messages = [item for item in chat_log.get("parsed_messages", []) if isinstance(item, dict)]
    if participants and parsed_messages:
        return {
            "level": "medium",
            "basis": "native_chat_export_with_parsed_messages",
            "caveats": [
                (
                    "Chat evidence is normalized from export text and should be checked against the "
                    "original export when fine timing or threading detail matters."
                )
            ],
        }
    if participants:
        return {
            "level": "medium",
            "basis": "operator_supplied_chat_log_with_participants",
            "caveats": ["Chat-log evidence is operator supplied and is not yet normalized into the behavioral-analysis layers."],
        }
    return {
        "level": "low",
        "basis": "operator_supplied_chat_log_excerpt",
        "caveats": [
            "Chat-log evidence is operator supplied and lacks structured participant context.",
            "Chat-log evidence is not yet normalized into the behavioral-analysis layers.",
        ],
    }


def _is_formal_document(attachment: dict[str, Any]) -> bool:
    filename = str(attachment.get("filename") or "").strip()
    mime_type = str(attachment.get("mime_type") or "").strip().lower()
    if Path(filename).suffix.lower() in _FORMAL_DOCUMENT_EXTENSIONS:
        return True
    return any(marker in mime_type for marker in _FORMAL_DOCUMENT_MIME_MARKERS)


def _source_reliability_for_email(candidate: dict[str, Any]) -> dict[str, Any]:
    weak_message = candidate.get("weak_message")
    verification_status = str(candidate.get("verification_status") or "")
    if weak_message:
        return {
            "level": "medium",
            "basis": "weak_message_semantics",
            "caveats": ["Email body is available, but the message was already classified as weak evidence."],
        }
    if "forensic" in verification_status:
        return {"level": "high", "basis": "forensic_body_verification", "caveats": []}
    return {"level": "high", "basis": "authored_email_body", "caveats": []}


def _source_reliability_for_attachment(candidate: dict[str, Any], *, source_type: str) -> dict[str, Any]:
    attachment = cast(dict[str, Any], candidate.get("attachment")) if isinstance(candidate.get("attachment"), dict) else {}
    evidence_strength = str(attachment.get("evidence_strength") or "")
    extraction_state = str(attachment.get("extraction_state") or "")
    ocr_used = bool(attachment.get("ocr_used"))
    basis_prefix = _attachment_reliability_basis_prefix(source_type)
    if evidence_strength == "strong_text":
        basis = f"{basis_prefix}_text_extracted"
        level = "high"
        caveats: list[str] = []
        if extraction_state == "ocr_text_extracted" or ocr_used:
            basis = f"{basis_prefix}_ocr_text_extracted"
            level = "medium"
            caveats = ["Text was recovered via OCR and should be checked against the original page or file."]
        return {"level": level, "basis": basis, "caveats": caveats}
    if extraction_state in {"ocr_failed", "ocr_failure"}:
        return {
            "level": "low",
            "basis": f"{basis_prefix}_ocr_failed",
            "caveats": ["OCR failed, so this source currently acts only as a weak documentary reference."],
        }
    if extraction_state in {"binary_only", "image_embedding_only"}:
        return {
            "level": "low",
            "basis": f"{basis_prefix}_binary_only",
            "caveats": ["No extracted text is available, so the original file must be reviewed directly."],
        }
    return {
        "level": "low",
        "basis": extraction_state or f"{basis_prefix}_reference_only",
        "caveats": ["Attachment is represented as a reference hit without extracted strong-text evidence."],
    }


def _source_reliability_for_meeting(note: dict[str, Any]) -> dict[str, Any]:
    extracted_from = str(note.get("_extracted_from") or "")
    if extracted_from == "meeting_data":
        return {"level": "high", "basis": "calendar_meeting_metadata", "caveats": []}
    return {
        "level": "medium",
        "basis": "exchange_extracted_meeting_reference",
        "caveats": ["Meeting context was extracted from Exchange metadata rather than authored narrative text."],
    }


def _weighting_metadata(*, source_type: str, reliability_level: str, text_available: bool) -> dict[str, Any]:
    base_weight = 0.4
    if reliability_level == "medium":
        base_weight = 0.7
    elif reliability_level == "high":
        base_weight = 1.0
    return {
        "weight_label": reliability_level,
        "base_weight": base_weight,
        "text_available": text_available,
        "can_corroborate_or_contradict": text_available
        and source_type in {"email", "attachment", "formal_document", "note_record", "time_record", "participation_record"},
    }


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value if str(item).strip()] if isinstance(value, list) else []


def _documentary_support_payload(candidate: dict[str, Any], *, source_type: str) -> dict[str, Any] | None:
    attachment = candidate.get("attachment") if isinstance(candidate.get("attachment"), dict) else {}
    if not attachment:
        return None
    explicit_payload = attachment.get("documentary_support")
    if isinstance(explicit_payload, dict) and explicit_payload:
        return {
            "filename": str(explicit_payload.get("filename") or attachment.get("filename") or ""),
            "mime_type": str(explicit_payload.get("mime_type") or attachment.get("mime_type") or ""),
            "text_available": bool(explicit_payload.get("text_available")),
            "evidence_strength": str(explicit_payload.get("evidence_strength") or attachment.get("evidence_strength") or ""),
            "extraction_state": str(explicit_payload.get("extraction_state") or attachment.get("extraction_state") or ""),
            "ocr_used": bool(explicit_payload.get("ocr_used") if "ocr_used" in explicit_payload else attachment.get("ocr_used")),
            "failure_reason": str(explicit_payload.get("failure_reason") or attachment.get("failure_reason") or ""),
            "text_preview": str(explicit_payload.get("text_preview") or attachment.get("text_preview") or ""),
            "format_profile": dict(explicit_payload.get("format_profile") or attachment.get("format_profile") or {}),
            "extraction_quality": dict(explicit_payload.get("extraction_quality") or attachment.get("extraction_quality") or {}),
            "review_recommendation": str(
                explicit_payload.get("review_recommendation") or attachment.get("review_recommendation") or ""
            ),
        }
    extraction_state = str(attachment.get("extraction_state") or "")
    evidence_strength = str(attachment.get("evidence_strength") or "")
    ocr_used = bool(attachment.get("ocr_used"))
    format_profile = dict(attachment.get("format_profile") or {})
    if not format_profile:
        format_profile = attachment_format_profile(
            filename=str(attachment.get("filename") or ""),
            mime_type=str(attachment.get("mime_type") or ""),
            extraction_state=extraction_state,
            evidence_strength=evidence_strength,
            ocr_used=ocr_used,
            text_available=bool(attachment.get("text_available")),
        )
    extraction_quality = dict(attachment.get("extraction_quality") or {})
    if not extraction_quality:
        extraction_quality = extraction_quality_profile(
            extraction_state=extraction_state,
            evidence_strength=evidence_strength,
            ocr_used=ocr_used,
            format_profile=format_profile,
        )
    return {
        "filename": str(attachment.get("filename") or ""),
        "mime_type": str(attachment.get("mime_type") or ""),
        "text_available": bool(attachment.get("text_available")),
        "evidence_strength": evidence_strength,
        "extraction_state": extraction_state,
        "ocr_used": ocr_used,
        "failure_reason": str(attachment.get("failure_reason") or ""),
        "text_preview": str(attachment.get("text_preview") or ""),
        "format_profile": format_profile,
        "extraction_quality": extraction_quality,
        "review_recommendation": str(attachment.get("review_recommendation") or "")
        or _source_review_recommendation(
            extraction_state=extraction_state,
            evidence_strength=evidence_strength,
            ocr_used=ocr_used,
            source_type=source_type,
            format_profile=format_profile,
            extraction_quality=extraction_quality,
        ),
    }


def _spreadsheet_semantics(source: dict[str, Any]) -> dict[str, Any] | None:
    explicit = source.get("spreadsheet_semantics")
    if isinstance(explicit, dict) and explicit:
        return explicit
    if str(source.get("source_type") or "") != "time_record":
        return None
    documentary = (
        cast(dict[str, Any], source.get("documentary_support")) if isinstance(source.get("documentary_support"), dict) else {}
    )
    format_profile = documentary.get("format_profile")
    if not isinstance(format_profile, dict) or str(format_profile.get("format_family") or "") != "spreadsheet":
        return None
    chronology_text = _chronology_text(source)
    explicit_dates = list(dict.fromkeys(match.group(1) for match in _ISO_DATE_RE.finditer(chronology_text)))
    date_range = _date_range_from_text(chronology_text)
    month_labels = sorted({match.group(1).lower() for match in _MONTH_LABEL_RE.finditer(chronology_text)})
    sheet_names = list(
        dict.fromkeys(match.group(1).strip() for match in _SHEET_NAME_RE.finditer(chronology_text) if match.group(1).strip())
    )
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


def _document_locator(candidate: dict[str, Any]) -> dict[str, Any]:
    provenance = dict(candidate.get("provenance") or {})
    return {
        "evidence_handle": str(provenance.get("evidence_handle") or ""),
        "chunk_id": str(provenance.get("chunk_id") or ""),
        "snippet_start": provenance.get("snippet_start"),
        "snippet_end": provenance.get("snippet_end"),
        "page_hint": provenance.get("page"),
        "section_hint": provenance.get("section"),
    }


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
    "_attachment_document_kind",
    "_attachment_reliability_basis_prefix",
    "_attachment_source_type",
    "_document_locator",
    "_documentary_support_payload",
    "_is_formal_document",
    "_source_reliability_for_attachment",
    "_source_reliability_for_chat_log",
    "_source_reliability_for_email",
    "_source_reliability_for_meeting",
    "_source_review_recommendation",
    "_spreadsheet_semantics",
    "_string_list",
    "_weighting_metadata",
]
