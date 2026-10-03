"""Attachment classification, extraction profiles, and attachment provenance."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import _CandidateData


_ATTACHMENT_HEADER_RE = re.compile(r'^\[Attachment:\s*(.+?)\s+from email\s+"', re.IGNORECASE)


def _is_attachment_result(metadata: dict[str, Any], *, chunk_id: str = "") -> bool:
    """Classify search results whose support originates from an attachment payload."""
    raw_flag = metadata.get("is_attachment")
    if isinstance(raw_flag, str):
        if raw_flag.lower() == "true":
            return True
    elif raw_flag:
        return True
    if metadata.get("attachment_filename"):
        return True
    if str(metadata.get("chunk_type") or "").lower() == "image":
        return True
    return "__att_" in chunk_id or "__img_" in chunk_id


def _attachment_extraction_state(metadata: dict[str, Any], *, chunk_id: str = "") -> str | None:
    """Return best-effort attachment extraction state from existing chunk metadata."""
    explicit = metadata.get("extraction_state")
    if explicit:
        return str(explicit).strip().lower()
    if str(metadata.get("chunk_type") or "").lower() == "image":
        return "image_embedding_only"
    if _is_attachment_result(metadata, chunk_id=chunk_id):
        return "text_extracted"
    return None


def _known_attachment_profile(normalized: str, weak_reference_only: bool) -> dict[str, Any] | None:
    """Map normalized attachment extraction states to answer-evidence profiles."""
    if normalized in {"ocr_text_extracted", "ocr_extracted_text", "ocr_success"}:
        return {
            "extraction_state": "ocr_text_extracted",
            "text_available": True,
            "ocr_used": True,
            "failure_reason": None,
            "evidence_strength": "strong_text",
        }
    if normalized in {"text_extracted", "text"}:
        available = not weak_reference_only
        return {
            "extraction_state": "text_extracted" if available else "binary_only",
            "text_available": available,
            "ocr_used": False,
            "failure_reason": None if available else "no_text_extracted",
            "evidence_strength": "strong_text" if available else "weak_reference",
        }
    if normalized in {"ocr_failed", "ocr_failure"}:
        return {
            "extraction_state": "ocr_failed",
            "text_available": False,
            "ocr_used": True,
            "failure_reason": "ocr_failed",
            "evidence_strength": "weak_reference",
        }
    if normalized in {"extraction_failed", "text_extraction_failed"}:
        return {
            "extraction_state": "extraction_failed",
            "text_available": False,
            "ocr_used": False,
            "failure_reason": "extraction_failed",
            "evidence_strength": "weak_reference",
        }
    if normalized in {"binary_only", "image_embedding_only", "image_only_no_text"}:
        return {
            "extraction_state": "binary_only",
            "text_available": False,
            "ocr_used": normalized.startswith("ocr_"),
            "failure_reason": "no_text_extracted",
            "evidence_strength": "weak_reference",
        }
    return None


def _attachment_evidence_profile(
    metadata: dict[str, Any],
    *,
    chunk_id: str = "",
    snippet: str = "",
) -> dict[str, Any]:
    """Return normalized attachment evidence semantics for answer-facing output."""
    extraction_state = _attachment_extraction_state(metadata, chunk_id=chunk_id) or ""
    normalized = extraction_state.strip().lower()
    normalized_snippet = " ".join((snippet or "").split())
    weak_reference_only = bool(_ATTACHMENT_HEADER_RE.match((snippet or "").strip())) and "\n" not in (snippet or "")

    known = _known_attachment_profile(normalized, weak_reference_only)
    if known is not None:
        return known
    state = normalized or "unknown"
    available = bool(normalized_snippet)
    return {
        "extraction_state": state,
        "text_available": available,
        "ocr_used": "ocr" in state,
        "failure_reason": None if available else "unknown",
        "evidence_strength": "strong_text" if available else "weak_reference",
    }


def _attachment_record_for_candidate(data: _CandidateData, uid: str, filename: str) -> dict[str, Any] | None:
    """Return the matching attachment record for one candidate, if the DB exposes it."""
    if not uid or not filename:
        return None
    for attachment in data.attachments_by_uid.get(uid, []):
        if str(attachment.get("name") or "") == filename:
            return attachment
    return None


def _attachment_filename(metadata: dict[str, Any], text: str) -> str:
    """Prefer attachment metadata and fall back to a parsed text header or a stable generic label."""
    filename = str(metadata.get("attachment_filename") or metadata.get("filename") or "")
    if filename:
        return filename
    match = _ATTACHMENT_HEADER_RE.match(text.strip())
    return match.group(1).strip() if match else "attachment"


def _attachment_info(
    metadata: dict[str, Any], record: dict[str, Any] | None, filename: str, profile: dict[str, Any]
) -> dict[str, Any]:
    """Merge record and retrieval metadata into the public attachment identity and extraction profile."""
    rec = record or {}
    support = rec.get("documentary_support", {})
    return {
        "filename": filename,
        "attachment_id": str(metadata.get("attachment_id") or rec.get("attachment_id") or ""),
        "mime_type": rec.get("mime_type"),
        "size": rec.get("size"),
        "content_sha256": str(metadata.get("content_sha256") or rec.get("content_sha256") or ""),
        "content_id": rec.get("content_id"),
        "is_inline": bool(rec.get("is_inline", False)) if record is not None else None,
        "locator_version": int(metadata.get("locator_version") or rec.get("locator_version") or 1),
        "text_locator": dict(rec.get("text_locator") or {}),
        "source_type_hint": rec.get("source_type_hint"),
        "format_profile": dict(support.get("format_profile", {})),
        "extraction_quality": dict(support.get("extraction_quality", {})),
        "review_recommendation": str(support.get("review_recommendation", "")),
        "text_preview": str(support.get("text_preview", "")),
        "spreadsheet_semantics": dict(rec.get("spreadsheet_semantics", {})),
        "calendar_semantics": dict(rec.get("calendar_semantics", {})),
        "weak_format_semantics": dict(rec.get("weak_format_semantics", {})),
        **profile,
    }


def _attachment_provenance(
    metadata: dict[str, Any], record: dict[str, Any] | None, result: Any, uid: str, filename: str, start: int, end: int
) -> dict[str, Any]:
    """Construct a stable attachment evidence handle with byte-range, hash, and locator provenance."""
    rec = record or {}
    return {
        "evidence_handle": f"attachment:{uid}:{filename}:{result.chunk_id}:{start}:{end}",
        "uid": uid,
        "chunk_id": result.chunk_id,
        "snippet_start": start,
        "snippet_end": end,
        "source_scope": str(metadata.get("source_scope") or "attachment_text"),
        "char_start": start,
        "char_end": end,
        "surface_hash": str(metadata.get("surface_hash") or ""),
        "attachment_id": str(metadata.get("attachment_id") or rec.get("attachment_id") or ""),
        "content_sha256": str(metadata.get("content_sha256") or rec.get("content_sha256") or ""),
        "locator_version": int(metadata.get("locator_version") or rec.get("locator_version") or 1),
        "attachment_filename": filename,
    }
