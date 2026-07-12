# mypy: disable-error-code=name-defined
# pylint: disable=too-many-arguments,too-many-return-statements


# pylint: disable=E0602  # cross-module names injected by compatibility facade
"""Split multi-source case-bundle helpers (multi_source_case_bundle_reliability)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

from .attachment_extractor import (
    attachment_format_profile,
    extraction_quality_profile,
)
from .multi_source_case_bundle_chronology import _chronology_text, _date_range_from_text
from .multi_source_case_bundle_common import _normalized_text

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


def _attachment_source_type(candidate: dict[str, Any], attachment: dict[str, Any]) -> str:
    """Determine the source type for an attachment based on explicit hints and content analysis.

    Args:
        candidate: The candidate source dictionary containing context like subject and snippet.
        attachment: The attachment dictionary containing metadata like filename and source_type_hint.

    Returns:
        The determined source type string from _DECLARED_SOURCE_TYPES.
    """
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
    """Map an attachment source type to its document kind representation.

    Args:
        source_type: The source type string (e.g., 'attachment', 'formal_document').

    Returns:
        The document kind string, prefixed with 'attached_' for non-attachment types.
    """
    if source_type == "attachment":
        return "attachment"
    if source_type == "formal_document":
        return "attached_document"
    return f"attached_{source_type}"


def _attachment_reliability_basis_prefix(source_type: str) -> str:
    """Get the reliability basis prefix for an attachment source type.

    Args:
        source_type: The source type string.

    Returns:
        The source type string to be used as the reliability basis prefix.
    """
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
    """Generate a review recommendation based on extraction and source characteristics.

    Args:
        extraction_state: The state of text extraction (e.g., 'text_extracted', 'ocr_failed').
        evidence_strength: The strength of evidence (e.g., 'strong_text', 'weak').
        ocr_used: Whether OCR was used for text extraction.
        source_type: The type of source (e.g., 'email', 'attachment', 'note_record').
        format_profile: Optional dictionary containing format-related metadata.
        extraction_quality: Optional dictionary containing quality assessment metadata.

    Returns:
        A string recommendation for how to handle the source in review.
    """
    profile = format_profile if isinstance(format_profile, dict) else {}
    quality = extraction_quality if isinstance(extraction_quality, dict) else {}
    return _review_recommendation_stages(extraction_state, evidence_strength, ocr_used, source_type, profile, quality)


def _review_recommendation_stages(
    extraction_state: str,
    evidence_strength: str,
    ocr_used: bool,
    source_type: str,
    profile: dict[str, Any],
    quality: dict[str, Any],
) -> str:
    unsupported = _unsupported_recommendation(profile)
    if unsupported:
        return unsupported
    extracted = _extracted_text_recommendation(extraction_state, evidence_strength, source_type, profile)
    if extracted:
        return extracted
    return _fallback_review_recommendation(extraction_state, evidence_strength, ocr_used, quality)


def _unsupported_recommendation(profile: dict[str, Any]) -> str:
    if str(profile.get("support_level") or "") != "unsupported":
        return ""
    label = str(profile.get("format_label") or "source").strip()
    return (
        f"{label} is not currently supported for reliable extraction; keep it as a visible reference "
        "and review the original file directly."
    )


def _extracted_text_recommendation(
    extraction_state: str, evidence_strength: str, source_type: str, profile: dict[str, Any]
) -> str:
    if extraction_state != "text_extracted" or evidence_strength != "strong_text":
        return ""
    format_label = str(profile.get("format_label") or "source").strip()
    mode = str(profile.get("handling_mode") or "").strip()
    if mode == "flattened_tabular_text":
        return f"{format_label} text is usable, but sheet structure and formulas were flattened during extraction."
    if mode == "calendar_text_flattened":
        return (
            f"{format_label} text is usable, but richer calendar structure was flattened and should be checked "
            "against the original file when timing detail matters."
        )
    return _source_type_review(source_type)


def _source_type_review(source_type: str) -> str:
    recommendations = {
        "note_record": "Extracted note text can support chronology, summary comparison, and follow-up directly.",
        "time_record": "Extracted time-record text can support chronology and attendance follow-up directly.",
        "participation_record": "Extracted participation-record text can support process and consultation follow-up directly.",
        "formal_document": "Native extracted document text can support chronology and exhibit follow-up directly.",
    }
    return recommendations.get(source_type, "Extracted attachment text can support downstream follow-up directly.")


def _fallback_review_recommendation(
    extraction_state: str, evidence_strength: str, ocr_used: bool, quality: dict[str, Any]
) -> str:
    if evidence_strength == "strong_text" and ocr_used:
        return "OCR-recovered text is usable, but the original page image should be checked before relying on fine wording."
    if extraction_state in {"ocr_failed", "extraction_failed", "binary_only", "image_embedding_only"}:
        return "Treat this source as a weak documentary reference until the original file is reviewed manually."
    if quality.get("manual_review_required"):
        return "Manual review is still required before treating this source as strong documentary proof."
    return "Review the original file before treating this source as strong documentary proof."


def _source_reliability_for_chat_log(chat_log: dict[str, Any]) -> dict[str, Any]:
    """Determine reliability assessment for a chat log source.

    Args:
        chat_log: Dictionary containing chat log data with participants and parsed_messages.

    Returns:
        Dictionary with reliability level, basis, and caveats for the chat log.
    """
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
    """Check if an attachment should be classified as a formal document.

    Args:
        attachment: Dictionary containing attachment metadata with filename and mime_type.

    Returns:
        True if the attachment has a formal document extension or MIME type, False otherwise.
    """
    filename = str(attachment.get("filename") or "").strip()
    mime_type = str(attachment.get("mime_type") or "").strip().lower()
    if Path(filename).suffix.lower() in _FORMAL_DOCUMENT_EXTENSIONS:
        return True
    return any(marker in mime_type for marker in _FORMAL_DOCUMENT_MIME_MARKERS)


def _source_reliability_for_email(candidate: dict[str, Any]) -> dict[str, Any]:
    """Determine reliability assessment for an email source.

    Args:
        candidate: Dictionary containing email candidate data.

    Returns:
        Dictionary with reliability level, basis, and caveats for the email.
    """
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
    """Determine reliability assessment for an attachment source.

    Args:
        candidate: Dictionary containing attachment candidate data.
        source_type: The determined source type for the attachment.

    Returns:
        Dictionary with reliability level, basis, and caveats for the attachment.
    """
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
    """Determine reliability assessment for a meeting note source.

    Args:
        note: Dictionary containing meeting note data.

    Returns:
        Dictionary with reliability level, basis, and caveats for the meeting note.
    """
    extracted_from = str(note.get("_extracted_from") or "")
    if extracted_from == "meeting_data":
        return {"level": "high", "basis": "calendar_meeting_metadata", "caveats": []}
    return {
        "level": "medium",
        "basis": "exchange_extracted_meeting_reference",
        "caveats": ["Meeting context was extracted from Exchange metadata rather than authored narrative text."],
    }


def _weighting_metadata(*, source_type: str, reliability_level: str, text_available: bool) -> dict[str, Any]:
    """Generate weighting metadata for a source based on type, reliability, and text availability.

    Args:
        source_type: The type of source.
        reliability_level: The reliability level ('low', 'medium', 'high').
        text_available: Whether extracted text is available.

    Returns:
        Dictionary containing weight_label, base_weight, text_available, and
        can_corroborate_or_contradict flags.
    """
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
    """Convert a value to a list of non-empty strings.

    Args:
        value: The value to convert (typically a list or None).

    Returns:
        A list of stripped string items, or empty list if value is not a list.
    """
    return [str(item) for item in value if str(item).strip()] if isinstance(value, list) else []


def _documentary_support_payload(candidate: dict[str, Any], *, source_type: str) -> dict[str, Any] | None:
    """Extract or construct documentary support payload from a candidate.

    Args:
        candidate: Dictionary containing candidate data with optional attachment.
        source_type: The determined source type for the candidate.

    Returns:
        Dictionary with documentary support metadata, or None if no attachment exists.
    """
    attachment = _attachment_payload(candidate)
    if not attachment:
        return None
    explicit = attachment.get("documentary_support")
    if isinstance(explicit, dict) and explicit:
        return _explicit_documentary_support(explicit, attachment)
    return _derived_documentary_support(attachment, source_type)


def _attachment_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    attachment = candidate.get("attachment")
    return cast(dict[str, Any], attachment) if isinstance(attachment, dict) else {}


def _explicit_documentary_support(payload: dict[str, Any], attachment: dict[str, Any]) -> dict[str, Any]:
    return {
        "filename": _support_string(payload, attachment, "filename"),
        "mime_type": _support_string(payload, attachment, "mime_type"),
        "text_available": bool(payload.get("text_available")),
        "evidence_strength": _support_string(payload, attachment, "evidence_strength"),
        "extraction_state": _support_string(payload, attachment, "extraction_state"),
        "ocr_used": bool(payload.get("ocr_used") if "ocr_used" in payload else attachment.get("ocr_used")),
        "failure_reason": _support_string(payload, attachment, "failure_reason"),
        "text_preview": _support_string(payload, attachment, "text_preview"),
        "format_profile": _support_mapping(payload, attachment, "format_profile"),
        "extraction_quality": _support_mapping(payload, attachment, "extraction_quality"),
        "review_recommendation": _support_string(payload, attachment, "review_recommendation"),
    }


def _support_string(primary: dict[str, Any], fallback: dict[str, Any], key: str) -> str:
    return str(primary.get(key) or fallback.get(key) or "")


def _support_mapping(primary: dict[str, Any], fallback: dict[str, Any], key: str) -> dict[str, Any]:
    return dict(primary.get(key) or fallback.get(key) or {})


def _derived_documentary_support(attachment: dict[str, Any], source_type: str) -> dict[str, Any]:
    state = str(attachment.get("extraction_state") or "")
    strength = str(attachment.get("evidence_strength") or "")
    ocr_used = bool(attachment.get("ocr_used"))
    profile = _format_profile(attachment, state, strength, ocr_used)
    quality = _extraction_quality(attachment, state, strength, ocr_used, profile)
    return _derived_support_payload(attachment, source_type, state, strength, ocr_used, profile, quality)


def _format_profile(attachment: dict[str, Any], state: str, strength: str, ocr_used: bool) -> dict[str, Any]:
    profile = dict(attachment.get("format_profile") or {})
    if profile:
        return profile
    return attachment_format_profile(
        filename=str(attachment.get("filename") or ""),
        mime_type=str(attachment.get("mime_type") or ""),
        extraction_state=state,
        evidence_strength=strength,
        ocr_used=ocr_used,
        text_available=bool(attachment.get("text_available")),
    )


def _extraction_quality(
    attachment: dict[str, Any], state: str, strength: str, ocr_used: bool, profile: dict[str, Any]
) -> dict[str, Any]:
    quality = dict(attachment.get("extraction_quality") or {})
    return quality or extraction_quality_profile(
        extraction_state=state, evidence_strength=strength, ocr_used=ocr_used, format_profile=profile
    )


def _derived_support_payload(
    attachment: dict[str, Any],
    source_type: str,
    state: str,
    strength: str,
    ocr_used: bool,
    profile: dict[str, Any],
    quality: dict[str, Any],
) -> dict[str, Any]:
    review = str(attachment.get("review_recommendation") or "")
    return {
        "filename": str(attachment.get("filename") or ""),
        "mime_type": str(attachment.get("mime_type") or ""),
        "text_available": bool(attachment.get("text_available")),
        "evidence_strength": strength,
        "extraction_state": state,
        "ocr_used": ocr_used,
        "failure_reason": str(attachment.get("failure_reason") or ""),
        "text_preview": str(attachment.get("text_preview") or ""),
        "format_profile": profile,
        "extraction_quality": quality,
        "review_recommendation": review
        or _source_review_recommendation(
            extraction_state=state,
            evidence_strength=strength,
            ocr_used=ocr_used,
            source_type=source_type,
            format_profile=profile,
            extraction_quality=quality,
        ),
    }


def _spreadsheet_semantics(source: dict[str, Any]) -> dict[str, Any] | None:
    """Extract or derive spreadsheet semantics from a source.

    Args:
        source: Dictionary containing source data with optional spreadsheet_semantics.

    Returns:
        Dictionary with spreadsheet metadata (record_type, sheet_names, date_range, etc.),
        or None if not applicable (non-time_record sources without explicit semantics).
    """
    explicit = source.get("spreadsheet_semantics")
    if isinstance(explicit, dict) and explicit:
        return explicit
    if not _is_spreadsheet_time_record(source):
        return None
    return _spreadsheet_payload(_chronology_text(source))


def _is_spreadsheet_time_record(source: dict[str, Any]) -> bool:
    if str(source.get("source_type") or "") != "time_record":
        return False
    documentary = cast(dict[str, Any], source.get("documentary_support") or {})
    profile = documentary.get("format_profile")
    return isinstance(profile, dict) and str(profile.get("format_family") or "") == "spreadsheet"


def _spreadsheet_payload(chronology_text: str) -> dict[str, Any]:
    explicit_dates = list(dict.fromkeys(match.group(1) for match in _ISO_DATE_RE.finditer(chronology_text)))
    date_range = _date_range_from_text(chronology_text)
    sheet_names = _spreadsheet_sheet_names(chronology_text)
    return {
        "record_type": _spreadsheet_record_type(chronology_text),
        "sheet_names": sheet_names,
        "sheet_count": len(sheet_names),
        "explicit_dates": explicit_dates,
        "date_range": date_range,
        "month_labels": sorted({match.group(1).lower() for match in _MONTH_LABEL_RE.finditer(chronology_text)}),
        "date_signal_strength": "range" if date_range else "dates" if explicit_dates else "weak",
        "structure_signal": "sheeted" if sheet_names else "flattened_rows_only",
    }


def _spreadsheet_sheet_names(text: str) -> list[str]:
    return list(dict.fromkeys(match.group(1).strip() for match in _SHEET_NAME_RE.finditer(text) if match.group(1).strip()))


def _spreadsheet_record_type(text: str) -> str:
    lower_text = text.lower()
    if any(token in lower_text for token in ("time system", "nova time")):
        return "time system_export"
    if "attendance" in lower_text:
        return "attendance_export"
    if any(token in lower_text for token in ("arbeitszeit", "timesheet", "time sheet", "zeiterfassung")):
        return "time_tracking_export"
    return "generic_time_record"


def _document_locator(candidate: dict[str, Any]) -> dict[str, Any]:
    """Extract document locator information from a candidate's provenance.

    Args:
        candidate: Dictionary containing candidate data with provenance information.

    Returns:
        Dictionary with evidence_handle, chunk_id, snippet bounds, and page/section hints.
    """
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
