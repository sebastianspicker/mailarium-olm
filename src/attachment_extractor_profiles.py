"""Attachment source-format and extraction-quality profiles."""
# pylint: disable=too-many-arguments,too-many-branches,too-many-return-statements

from __future__ import annotations

from typing import Any

from .image_embedder import _IMAGE_EXTENSIONS

SOURCE_FORMAT_INGESTION_MATRIX_VERSION = "1"

_ARCHIVE_EXTENSIONS = frozenset({".zip", ".gz", ".tar", ".rar", ".7z"})
_TRANSCRIPT_TEXT_EXTENSIONS = frozenset({".txt", ".md", ".log", ".json", ".xml", ".yaml", ".yml", ".rst"})
_SPREADSHEET_EXTENSIONS = frozenset({".csv", ".tsv", ".xlsx", ".xls", ".xlsm", ".ods"})
_CALENDAR_EXTENSIONS = frozenset({".ics", ".ical", ".vcs"})


def _get_extension(filename: str) -> str:
    dot_pos = filename.rfind(".")
    if dot_pos == -1:
        return ""
    return filename[dot_pos:].lower()


def _is_degraded(normalized_state: str, normalized_strength: str) -> bool:
    """Return True when the attachment has no usable extracted text."""
    return normalized_state in {"binary_only", "extraction_failed"} or normalized_strength == "weak_reference"


def _apply_degraded_reference(
    profile: dict[str, Any],
    *,
    handling_mode: str,
    degrade_reason: str,
    limitations: list[str],
) -> None:
    """Mark a format profile as degraded reference-only when text is unavailable."""
    profile.update(
        {
            "handling_mode": handling_mode,
            "support_level": "reference_only",
            "lossiness": "high",
            "manual_review_required": True,
            "degrade_reason": degrade_reason,
            "limitations": limitations,
        }
    )


def attachment_format_profile(
    *,
    filename: str,
    mime_type: str = "",
    extraction_state: str = "",
    evidence_strength: str = "",
    ocr_used: bool = False,
    text_available: bool = False,
) -> dict[str, Any]:
    """Return a stable source-format ingestion profile for one attachment."""
    ext = _get_extension(filename)
    normalized_mime = str(mime_type or "").strip().lower()
    normalized_state = str(extraction_state or "").strip().lower()
    normalized_strength = str(evidence_strength or "").strip().lower()

    handler = _format_profile_handler(ext, normalized_mime)
    return handler(normalized_state, normalized_strength, ocr_used, text_available)


def _format_profile_handler(ext: str, mime_type: str):
    if _is_pdf_format(ext, mime_type):
        return _pdf_handler
    if _is_docx_format(ext, mime_type):
        return _docx_handler
    if _is_portable_word_format(ext, mime_type):
        return _portable_handler
    if _is_spreadsheet_format(ext, mime_type):
        return _spreadsheet_handler
    if _is_calendar_format(ext, mime_type):
        return _calendar_handler
    if ext in _IMAGE_EXTENSIONS:
        return _image_handler
    if ext in _TRANSCRIPT_TEXT_EXTENSIONS:
        return _text_handler
    if ext in _ARCHIVE_EXTENSIONS:
        return _archive_handler
    if _is_email_format(ext, mime_type):
        return _email_handler
    if ext == ".pptx":
        return _presentation_handler
    return _other_handler


def _is_pdf_format(ext: str, mime_type: str) -> bool:
    return ext == ".pdf" or "application/pdf" in mime_type


def _is_docx_format(ext: str, mime_type: str) -> bool:
    return ext == ".docx" or "wordprocessingml.document" in mime_type


def _is_spreadsheet_format(ext: str, mime_type: str) -> bool:
    return ext in _SPREADSHEET_EXTENSIONS or "spreadsheetml.sheet" in mime_type


def _is_calendar_format(ext: str, mime_type: str) -> bool:
    return ext in _CALENDAR_EXTENSIONS or "text/calendar" in mime_type


def _is_email_format(ext: str, mime_type: str) -> bool:
    return ext == ".eml" or "message/rfc822" in mime_type


def _docx_handler(state: str, strength: str, _ocr_used: bool, _text_available: bool) -> dict[str, Any]:
    return _degradable_profile("docx", state, strength)


def _pdf_handler(state: str, strength: str, ocr_used: bool, _text_available: bool) -> dict[str, Any]:
    return _pdf_profile(state, strength, ocr_used)


def _portable_handler(state: str, strength: str, _ocr_used: bool, _text_available: bool) -> dict[str, Any]:
    return _degradable_profile("portable", state, strength)


def _spreadsheet_handler(state: str, strength: str, _ocr_used: bool, _text_available: bool) -> dict[str, Any]:
    return _degradable_profile("spreadsheet", state, strength)


def _calendar_handler(state: str, strength: str, _ocr_used: bool, _text_available: bool) -> dict[str, Any]:
    return _degradable_profile("calendar", state, strength)


def _image_handler(state: str, _strength: str, _ocr_used: bool, text_available: bool) -> dict[str, Any]:
    return _image_profile(state, text_available)


def _text_handler(_state: str, _strength: str, _ocr_used: bool, _text_available: bool) -> dict[str, Any]:
    return _profile(
        "transcript_text_bundle", "text_bundle", "Transcript-like text bundle", "plain_text_ingestion", "supported", "low", False
    )


def _archive_handler(state: str, _strength: str, _ocr_used: bool, text_available: bool) -> dict[str, Any]:
    return _archive_profile(state, text_available)


def _email_handler(_state: str, _strength: str, _ocr_used: bool, text_available: bool) -> dict[str, Any]:
    return _email_profile(text_available)


def _presentation_handler(_state: str, _strength: str, _ocr_used: bool, _text_available: bool) -> dict[str, Any]:
    return _profile(
        "presentation_document",
        "presentation",
        "Presentation deck",
        "slide_text_extraction",
        "degraded_supported",
        "medium",
        False,
        "slide_layout_and_visual_context_flattened",
        ["Slide layout and visual emphasis are flattened to text."],
    )


def _other_handler(_state: str, _strength: str, _ocr_used: bool, _text_available: bool) -> dict[str, Any]:
    return _profile(
        "other_attachment",
        "other",
        "Other attachment",
        "unsupported_or_unclassified",
        "unsupported",
        "high",
        True,
        "unsupported_or_unclassified_format",
        ["This file type is not explicitly supported by the current extraction matrix."],
    )


def _profile(
    format_id: str,
    family: str,
    label: str,
    handling_mode: str,
    support_level: str,
    lossiness: str,
    manual_review_required: bool,
    degrade_reason: str = "",
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "format_id": format_id,
        "format_family": family,
        "format_label": label,
        "handling_mode": handling_mode,
        "support_level": support_level,
        "lossiness": lossiness,
        "manual_review_required": manual_review_required,
        "degrade_reason": degrade_reason,
        "limitations": limitations or [],
    }


def _is_portable_word_format(ext: str, mime_type: str) -> bool:
    return ext in {".doc", ".odt", ".rtf"} or any(
        marker in mime_type
        for marker in ("application/msword", "application/rtf", "application/vnd.oasis.opendocument.text", "text/rtf")
    )


def _pdf_profile(state: str, strength: str, ocr_used: bool) -> dict[str, Any]:
    profile = _profile("pdf_document", "pdf", "PDF document", "native_pdf_text_extraction", "supported", "low", False)
    if state == "ocr_text_extracted" or ocr_used:
        return _profile(
            "scanned_pdf",
            "pdf",
            "Scanned PDF",
            "ocr_recovered_text",
            "degraded_supported",
            "medium",
            True,
            "ocr_required_for_scanned_pdf",
            [
                "Text depends on OCR recovery rather than native PDF text.",
                "Fine wording and page placement should be checked against the original PDF.",
            ],
        )
    if state == "sidecar_text_extracted":
        return _profile(
            "pdf_sidecar_transcript",
            "pdf",
            "PDF with sidecar transcript",
            "sidecar_transcript_text",
            "degraded_supported",
            "medium",
            True,
            "pdf_text_recovered_from_sidecar_transcript",
            [
                "Text came from a sidecar transcript rather than direct PDF extraction.",
                "The sidecar transcript should be checked against the original PDF before exact wording is relied on.",
            ],
        )
    if state in {"ocr_failed", "ocr_failure"}:
        return _profile(
            "ocr_poor_pdf",
            "pdf",
            "OCR-poor PDF",
            "reference_only_after_ocr_failure",
            "reference_only",
            "high",
            True,
            "ocr_failed_for_pdf",
            [
                "No reliable extracted PDF text is available.",
                "The original PDF must be reviewed manually before it can support serious legal outputs.",
            ],
        )
    if _is_degraded(state, strength):
        _apply_degraded_reference(
            profile,
            handling_mode="reference_only_document",
            degrade_reason=state or "pdf_text_not_available",
            limitations=["The PDF is present, but the current pipeline did not recover reliable text."],
        )
    return profile


def _degradable_profile(kind: str, state: str, strength: str) -> dict[str, Any]:
    profiles = {
        "docx": (
            "docx_document",
            "word_processing",
            "DOCX document",
            "native_docx_text_extraction",
            "supported",
            "low",
            "",
            [],
            "reference_only_document",
            "docx_text_not_available",
            "The DOCX exists, but reliable extracted text is not currently available.",
        ),
        "portable": (
            "portable_word_processing_document",
            "word_processing",
            "Portable word-processing document",
            "document_text_extraction_or_plain_text_fallback",
            "degraded_supported",
            "medium",
            "legacy_or_portable_word_processor_structure_flattened",
            ["Richer layout and tracked-change context may be flattened during extraction."],
            "reference_only_document",
            "portable_document_text_not_available",
            "The document exists, but reliable extracted text is not currently available.",
        ),
        "spreadsheet": (
            "spreadsheet_export",
            "spreadsheet",
            "Spreadsheet or time export",
            "flattened_tabular_text",
            "degraded_supported",
            "medium",
            "sheet_structure_flattened_to_text",
            ["Cell formulas, formatting, and workbook structure are flattened into plain text."],
            "reference_only_spreadsheet",
            "spreadsheet_text_not_available",
            "Structured spreadsheet content could not be rendered into usable text.",
        ),
        "calendar": (
            "calendar_file",
            "calendar",
            "Calendar file",
            "calendar_text_flattened",
            "degraded_supported",
            "medium",
            "calendar_structure_flattened_to_text",
            ["Calendar fields remain readable, but recurrence and richer calendar semantics are flattened."],
            "reference_only_calendar",
            "calendar_text_not_available",
            "Calendar metadata is not currently recoverable as reliable text.",
        ),
    }
    format_id, family, label, handling, support, lossiness, reason, limits, degraded_handling, fallback_reason, fallback_limit = (
        profiles[kind]
    )
    profile = _profile(format_id, family, label, handling, support, lossiness, False, reason, limits)
    if _is_degraded(state, strength):
        _apply_degraded_reference(
            profile, handling_mode=degraded_handling, degrade_reason=state or fallback_reason, limitations=[fallback_limit]
        )
    return profile


def _image_profile(state: str, text_available: bool) -> dict[str, Any]:
    if state == "sidecar_text_extracted" and text_available:
        return _profile(
            "image_sidecar_transcript",
            "image",
            "Image exhibit with sidecar transcript",
            "sidecar_transcript_text",
            "degraded_supported",
            "medium",
            True,
            "image_text_recovered_from_sidecar_transcript",
            [
                "Text came from a sidecar transcript rather than direct OCR over the image.",
                "Visual layout and emphasis still need to be checked against the original image.",
            ],
        )
    return _profile(
        "image_only_exhibit",
        "image",
        "Screenshot or image-only exhibit",
        "image_embedding_or_reference_only",
        "reference_only",
        "high",
        True,
        state or "image_only_source",
        [
            "The current pipeline does not recover full authored text from images by default.",
            "Image-only exhibits need manual visual review before exact wording is relied on.",
        ],
    )


def _archive_profile(state: str, text_available: bool) -> dict[str, Any]:
    if state == "archive_contents_extracted" and text_available:
        return _profile(
            "archive_bundle_text_recovered",
            "archive",
            "Archive bundle with extracted member text",
            "archive_member_text_recovered",
            "degraded_supported",
            "medium",
            True,
            "archive_member_text_recovered",
            [
                "Only safe and text-like archive members were extracted.",
                "Nested or binary archive contents may still require manual review.",
            ],
        )
    if state == "archive_inventory_extracted" and text_available:
        return _profile(
            "archive_inventory_bundle",
            "archive",
            "Archive bundle with member inventory",
            "archive_member_inventory_only",
            "degraded_supported",
            "high",
            True,
            "archive_contents_not_extracted_only_inventory_available",
            [
                "Only the archive member inventory is available; archive contents were not unpacked into evidence text.",
                "The original archive contents still need manual extraction or review before serious reliance.",
            ],
        )
    return _profile(
        "archive_bundle",
        "archive",
        "Archive bundle",
        "unsupported_archive_container",
        "unsupported",
        "high",
        True,
        "archive_contents_not_extracted",
        ["Archive contents are not unpacked by the current attachment extraction path."],
    )


def _email_profile(text_available: bool) -> dict[str, Any]:
    return _profile(
        "attached_email",
        "email",
        "Attached email message",
        "embedded_email_text_extraction",
        "degraded_supported" if text_available else "reference_only",
        "medium" if text_available else "high",
        not text_available,
        "" if text_available else "attached_email_text_not_available",
        [] if text_available else ["The attached email exists, but its readable content could not be extracted."],
    )


def extraction_quality_profile(
    *,
    extraction_state: str,
    evidence_strength: str,
    ocr_used: bool,
    format_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return normalized extraction-quality semantics for one attachment."""
    normalized_state = str(extraction_state or "").strip().lower()
    normalized_strength = str(evidence_strength or "").strip().lower()
    format_profile = format_profile if isinstance(format_profile, dict) else {}
    limitations = [str(item) for item in format_profile.get("limitations", []) if str(item).strip()]

    profile = _base_quality_profile(format_profile, limitations)

    if _is_native_text(normalized_strength, normalized_state, ocr_used):
        profile.update(_quality_update("native_text_extracted", "high", profile["manual_review_required"]))
        return profile

    if _is_ocr_text(normalized_strength, normalized_state, ocr_used):
        profile.update(_quality_update("ocr_text_recovered", "medium", True))
        return profile

    if state_quality := _state_quality(normalized_state):
        profile.update(_quality_update(*state_quality))
    elif format_profile.get("support_level") == "unsupported":
        profile.update(_quality_update("unsupported_format", "low", True))
    return profile


def _is_native_text(strength: str, state: str, ocr_used: bool) -> bool:
    return strength == "strong_text" and state == "text_extracted" and not ocr_used


def _is_ocr_text(strength: str, state: str, ocr_used: bool) -> bool:
    return strength == "strong_text" and (state == "ocr_text_extracted" or ocr_used)


def _base_quality_profile(format_profile: dict[str, Any], limitations: list[str]) -> dict[str, Any]:
    return {
        "quality_label": "reference_only",
        "quality_rank": "low",
        "lossiness": str(format_profile.get("lossiness") or "high"),
        "visible_limitations": limitations,
        "manual_review_required": bool(format_profile.get("manual_review_required")),
    }


def _quality_update(label: str, rank: str, manual_review_required: bool) -> dict[str, Any]:
    return {
        "quality_label": label,
        "quality_rank": rank,
        "manual_review_required": manual_review_required,
    }


def _state_quality(state: str) -> tuple[str, str, bool] | None:
    labels = {
        "sidecar_text_extracted": ("sidecar_text_recovered", "medium", True),
        "archive_inventory_extracted": ("archive_inventory_extracted", "low", True),
        "archive_contents_extracted": ("archive_contents_extracted", "medium", True),
        "binary_only": ("binary_reference_only", "low", True),
        "image_embedding_only": ("binary_reference_only", "low", True),
        "ocr_failed": ("ocr_failed", "low", True),
        "ocr_failure": ("ocr_failed", "low", True),
        "extraction_failed": ("extraction_failed", "low", True),
    }
    return labels.get(state)
