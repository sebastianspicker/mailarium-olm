"""Attachment source-format and extraction-quality profiles."""

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

    if ext == ".pdf" or "application/pdf" in normalized_mime:
        profile = {
            "format_id": "pdf_document",
            "format_family": "pdf",
            "format_label": "PDF document",
            "handling_mode": "native_pdf_text_extraction",
            "support_level": "supported",
            "lossiness": "low",
            "manual_review_required": False,
            "degrade_reason": "",
            "limitations": [],
        }
        if normalized_state == "ocr_text_extracted" or ocr_used:
            profile.update(
                {
                    "format_id": "scanned_pdf",
                    "format_label": "Scanned PDF",
                    "handling_mode": "ocr_recovered_text",
                    "support_level": "degraded_supported",
                    "lossiness": "medium",
                    "manual_review_required": True,
                    "degrade_reason": "ocr_required_for_scanned_pdf",
                    "limitations": [
                        "Text depends on OCR recovery rather than native PDF text.",
                        "Fine wording and page placement should be checked against the original PDF.",
                    ],
                }
            )
        elif normalized_state == "sidecar_text_extracted":
            profile.update(
                {
                    "format_id": "pdf_sidecar_transcript",
                    "format_label": "PDF with sidecar transcript",
                    "handling_mode": "sidecar_transcript_text",
                    "support_level": "degraded_supported",
                    "lossiness": "medium",
                    "manual_review_required": True,
                    "degrade_reason": "pdf_text_recovered_from_sidecar_transcript",
                    "limitations": [
                        "Text came from a sidecar transcript rather than direct PDF extraction.",
                        "The sidecar transcript should be checked against the original PDF before exact wording is relied on.",
                    ],
                }
            )
        elif normalized_state in {"ocr_failed", "ocr_failure"}:
            profile.update(
                {
                    "format_id": "ocr_poor_pdf",
                    "format_label": "OCR-poor PDF",
                    "handling_mode": "reference_only_after_ocr_failure",
                    "support_level": "reference_only",
                    "lossiness": "high",
                    "manual_review_required": True,
                    "degrade_reason": "ocr_failed_for_pdf",
                    "limitations": [
                        "No reliable extracted PDF text is available.",
                        "The original PDF must be reviewed manually before it can support serious legal outputs.",
                    ],
                }
            )
        elif normalized_state in {"binary_only", "extraction_failed"} or normalized_strength == "weak_reference":
            profile.update(
                {
                    "handling_mode": "reference_only_document",
                    "support_level": "reference_only",
                    "lossiness": "high",
                    "manual_review_required": True,
                    "degrade_reason": normalized_state or "pdf_text_not_available",
                    "limitations": [
                        "The PDF is present, but the current pipeline did not recover reliable text.",
                    ],
                }
            )
        return profile

    if ext == ".docx" or "wordprocessingml.document" in normalized_mime:
        profile = {
            "format_id": "docx_document",
            "format_family": "word_processing",
            "format_label": "DOCX document",
            "handling_mode": "native_docx_text_extraction",
            "support_level": "supported",
            "lossiness": "low",
            "manual_review_required": False,
            "degrade_reason": "",
            "limitations": [],
        }
        if normalized_state in {"binary_only", "extraction_failed"} or normalized_strength == "weak_reference":
            profile.update(
                {
                    "handling_mode": "reference_only_document",
                    "support_level": "reference_only",
                    "lossiness": "high",
                    "manual_review_required": True,
                    "degrade_reason": normalized_state or "docx_text_not_available",
                    "limitations": [
                        "The DOCX exists, but reliable extracted text is not currently available.",
                    ],
                }
            )
        return profile

    if ext in {".doc", ".odt", ".rtf"} or any(
        marker in normalized_mime
        for marker in (
            "application/msword",
            "application/rtf",
            "application/vnd.oasis.opendocument.text",
            "text/rtf",
        )
    ):
        profile = {
            "format_id": "portable_word_processing_document",
            "format_family": "word_processing",
            "format_label": "Portable word-processing document",
            "handling_mode": "document_text_extraction_or_plain_text_fallback",
            "support_level": "degraded_supported",
            "lossiness": "medium",
            "manual_review_required": False,
            "degrade_reason": "legacy_or_portable_word_processor_structure_flattened",
            "limitations": [
                "Richer layout and tracked-change context may be flattened during extraction.",
            ],
        }
        if normalized_state in {"binary_only", "extraction_failed"} or normalized_strength == "weak_reference":
            profile.update(
                {
                    "handling_mode": "reference_only_document",
                    "support_level": "reference_only",
                    "lossiness": "high",
                    "manual_review_required": True,
                    "degrade_reason": normalized_state or "portable_document_text_not_available",
                    "limitations": [
                        "The document exists, but reliable extracted text is not currently available.",
                    ],
                }
            )
        return profile

    if ext in _SPREADSHEET_EXTENSIONS or "spreadsheetml.sheet" in normalized_mime:
        profile = {
            "format_id": "spreadsheet_export",
            "format_family": "spreadsheet",
            "format_label": "Spreadsheet or time export",
            "handling_mode": "flattened_tabular_text",
            "support_level": "degraded_supported",
            "lossiness": "medium",
            "manual_review_required": False,
            "degrade_reason": "sheet_structure_flattened_to_text",
            "limitations": [
                "Cell formulas, formatting, and workbook structure are flattened into plain text.",
            ],
        }
        if normalized_state in {"binary_only", "extraction_failed"} or normalized_strength == "weak_reference":
            profile.update(
                {
                    "handling_mode": "reference_only_spreadsheet",
                    "support_level": "reference_only",
                    "lossiness": "high",
                    "manual_review_required": True,
                    "degrade_reason": normalized_state or "spreadsheet_text_not_available",
                    "limitations": [
                        "Structured spreadsheet content could not be rendered into usable text.",
                    ],
                }
            )
        return profile

    if ext in _CALENDAR_EXTENSIONS or "text/calendar" in normalized_mime:
        profile = {
            "format_id": "calendar_file",
            "format_family": "calendar",
            "format_label": "Calendar file",
            "handling_mode": "calendar_text_flattened",
            "support_level": "degraded_supported",
            "lossiness": "medium",
            "manual_review_required": False,
            "degrade_reason": "calendar_structure_flattened_to_text",
            "limitations": [
                "Calendar fields remain readable, but recurrence and richer calendar semantics are flattened.",
            ],
        }
        if normalized_state in {"binary_only", "extraction_failed"} or normalized_strength == "weak_reference":
            profile.update(
                {
                    "handling_mode": "reference_only_calendar",
                    "support_level": "reference_only",
                    "lossiness": "high",
                    "manual_review_required": True,
                    "degrade_reason": normalized_state or "calendar_text_not_available",
                    "limitations": [
                        "Calendar metadata is not currently recoverable as reliable text.",
                    ],
                }
            )
        return profile

    if ext in _IMAGE_EXTENSIONS:
        if normalized_state == "sidecar_text_extracted" and text_available:
            return {
                "format_id": "image_sidecar_transcript",
                "format_family": "image",
                "format_label": "Image exhibit with sidecar transcript",
                "handling_mode": "sidecar_transcript_text",
                "support_level": "degraded_supported",
                "lossiness": "medium",
                "manual_review_required": True,
                "degrade_reason": "image_text_recovered_from_sidecar_transcript",
                "limitations": [
                    "Text came from a sidecar transcript rather than direct OCR over the image.",
                    "Visual layout and emphasis still need to be checked against the original image.",
                ],
            }
        return {
            "format_id": "image_only_exhibit",
            "format_family": "image",
            "format_label": "Screenshot or image-only exhibit",
            "handling_mode": "image_embedding_or_reference_only",
            "support_level": "reference_only",
            "lossiness": "high",
            "manual_review_required": True,
            "degrade_reason": normalized_state or "image_only_source",
            "limitations": [
                "The current pipeline does not recover full authored text from images by default.",
                "Image-only exhibits need manual visual review before exact wording is relied on.",
            ],
        }

    if ext in _TRANSCRIPT_TEXT_EXTENSIONS:
        return {
            "format_id": "transcript_text_bundle",
            "format_family": "text_bundle",
            "format_label": "Transcript-like text bundle",
            "handling_mode": "plain_text_ingestion",
            "support_level": "supported",
            "lossiness": "low",
            "manual_review_required": False,
            "degrade_reason": "",
            "limitations": [],
        }

    if ext in _ARCHIVE_EXTENSIONS:
        if normalized_state == "archive_contents_extracted" and text_available:
            return {
                "format_id": "archive_bundle_text_recovered",
                "format_family": "archive",
                "format_label": "Archive bundle with extracted member text",
                "handling_mode": "archive_member_text_recovered",
                "support_level": "degraded_supported",
                "lossiness": "medium",
                "manual_review_required": True,
                "degrade_reason": "archive_member_text_recovered",
                "limitations": [
                    "Only safe and text-like archive members were extracted.",
                    "Nested or binary archive contents may still require manual review.",
                ],
            }
        if normalized_state == "archive_inventory_extracted" and text_available:
            return {
                "format_id": "archive_inventory_bundle",
                "format_family": "archive",
                "format_label": "Archive bundle with member inventory",
                "handling_mode": "archive_member_inventory_only",
                "support_level": "degraded_supported",
                "lossiness": "high",
                "manual_review_required": True,
                "degrade_reason": "archive_contents_not_extracted_only_inventory_available",
                "limitations": [
                    "Only the archive member inventory is available; archive contents were not unpacked into evidence text.",
                    "The original archive contents still need manual extraction or review before serious reliance.",
                ],
            }
        return {
            "format_id": "archive_bundle",
            "format_family": "archive",
            "format_label": "Archive bundle",
            "handling_mode": "unsupported_archive_container",
            "support_level": "unsupported",
            "lossiness": "high",
            "manual_review_required": True,
            "degrade_reason": "archive_contents_not_extracted",
            "limitations": [
                "Archive contents are not unpacked by the current attachment extraction path.",
            ],
        }

    if ext == ".eml" or "message/rfc822" in normalized_mime:
        return {
            "format_id": "attached_email",
            "format_family": "email",
            "format_label": "Attached email message",
            "handling_mode": "embedded_email_text_extraction",
            "support_level": "degraded_supported" if text_available else "reference_only",
            "lossiness": "medium" if text_available else "high",
            "manual_review_required": not text_available,
            "degrade_reason": "" if text_available else "attached_email_text_not_available",
            "limitations": (
                [] if text_available else ["The attached email exists, but its readable content could not be extracted."]
            ),
        }

    if ext == ".pptx":
        return {
            "format_id": "presentation_document",
            "format_family": "presentation",
            "format_label": "Presentation deck",
            "handling_mode": "slide_text_extraction",
            "support_level": "degraded_supported",
            "lossiness": "medium",
            "manual_review_required": False,
            "degrade_reason": "slide_layout_and_visual_context_flattened",
            "limitations": [
                "Slide layout and visual emphasis are flattened to text.",
            ],
        }

    return {
        "format_id": "other_attachment",
        "format_family": "other",
        "format_label": "Other attachment",
        "handling_mode": "unsupported_or_unclassified",
        "support_level": "unsupported",
        "lossiness": "high",
        "manual_review_required": True,
        "degrade_reason": "unsupported_or_unclassified_format",
        "limitations": [
            "This file type is not explicitly supported by the current extraction matrix.",
        ],
    }


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

    profile = {
        "quality_label": "reference_only",
        "quality_rank": "low",
        "lossiness": str(format_profile.get("lossiness") or "high"),
        "visible_limitations": limitations,
        "manual_review_required": bool(format_profile.get("manual_review_required")),
    }

    if normalized_strength == "strong_text" and normalized_state == "text_extracted" and not ocr_used:
        profile.update(
            {
                "quality_label": "native_text_extracted",
                "quality_rank": "high",
                "manual_review_required": bool(format_profile.get("manual_review_required")),
            }
        )
        return profile

    if normalized_strength == "strong_text" and (normalized_state == "ocr_text_extracted" or ocr_used):
        profile.update(
            {
                "quality_label": "ocr_text_recovered",
                "quality_rank": "medium",
                "manual_review_required": True,
            }
        )
        return profile

    if normalized_state == "sidecar_text_extracted":
        profile.update(
            {
                "quality_label": "sidecar_text_recovered",
                "quality_rank": "medium",
                "manual_review_required": True,
            }
        )
        return profile

    if normalized_state == "archive_inventory_extracted":
        profile.update(
            {
                "quality_label": "archive_inventory_extracted",
                "quality_rank": "low",
                "manual_review_required": True,
            }
        )
        return profile

    if normalized_state == "archive_contents_extracted":
        profile.update(
            {
                "quality_label": "archive_contents_extracted",
                "quality_rank": "medium",
                "manual_review_required": True,
            }
        )
        return profile

    if normalized_state in {"binary_only", "image_embedding_only"}:
        profile.update(
            {
                "quality_label": "binary_reference_only",
                "quality_rank": "low",
                "manual_review_required": True,
            }
        )
        return profile

    if normalized_state in {"ocr_failed", "ocr_failure"}:
        profile.update(
            {
                "quality_label": "ocr_failed",
                "quality_rank": "low",
                "manual_review_required": True,
            }
        )
        return profile

    if normalized_state == "extraction_failed":
        profile.update(
            {
                "quality_label": "extraction_failed",
                "quality_rank": "low",
                "manual_review_required": True,
            }
        )
        return profile

    if format_profile.get("support_level") == "unsupported":
        profile.update(
            {
                "quality_label": "unsupported_format",
                "quality_rank": "low",
                "manual_review_required": True,
            }
        )

    return profile
