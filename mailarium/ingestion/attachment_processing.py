"""Attachment extraction, evidence projection, and chunk emission for ingestion."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from mailarium.model.attachment_identity import (
    ATTACHMENT_TEXT_NORMALIZATION_VERSION,
    DEFAULT_ATTACHMENT_OCR_LANG,
    ensure_attachment_identity,
    normalize_attachment_search_text,
)
from mailarium.model.attachment_surfaces import build_attachment_surfaces, primary_surface_payload

from .attachment_extractor import attachment_format_profile, attachment_ocr_available_for, attachment_supports_ocr
from .runtime import IngestRuntime

_IngestRuntime = IngestRuntime


def _normalize_unprocessed_attachments(
    email,
    *,
    extraction_requested: bool,
) -> None:
    """Mark unprocessed attachment metadata rows as explicit payload failures."""
    if not extraction_requested:
        return
    attachments = getattr(email, "attachments", None) or []
    if not attachments or not bool(getattr(email, "has_attachments", False)):
        return
    payload_extraction_failed = bool(getattr(email, "_attachment_payload_extraction_failed", False))
    default_reason = "attachment_payload_extraction_failed" if payload_extraction_failed else "attachment_payload_unavailable"
    for att_i, attachment in enumerate(attachments):
        if not isinstance(attachment, dict):
            continue
        if str(attachment.get("extraction_state") or "").strip():
            continue
        filename = str(attachment.get("name") or f"attachment-{att_i}")
        attachment_id, content_sha256 = ensure_attachment_identity(attachment)
        _set_attachment_evidence(
            email,
            att_index=att_i,
            extraction_state="extraction_failed",
            evidence_strength="weak_reference",
            ocr_used=False,
            ocr_engine="",
            ocr_lang="",
            ocr_confidence=0.0,
            failure_reason=default_reason,
            text_preview="",
            extracted_text="",
            normalized_text="",
            text_normalization_version=0,
            text_source_path="",
            text_locator=_mailbox_attachment_locator(
                email_uid=str(getattr(email, "uid", "") or ""),
                att_index=att_i,
                filename=filename,
                extraction_state="extraction_failed",
                attachment_id=attachment_id,
                content_sha256=content_sha256,
            ),
            attachment_id=attachment_id,
            content_sha256=content_sha256,
            locator_version=2,
        )


def _attachments_safe_for_stale_cleanup(email: Any) -> bool:
    """Return whether attachment payload extraction completed well enough for broad stale cleanup."""
    if bool(getattr(email, "_attachment_payload_extraction_failed", False)):
        return False
    attachments = getattr(email, "attachments", None) or []
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        state = str(attachment.get("extraction_state") or "").strip().lower()
        reason = str(attachment.get("failure_reason") or "").strip().lower()
        if state == "extraction_failed" and reason in {
            "attachment_payload_unavailable",
            "attachment_payload_extraction_failed",
        }:
            return False
    return True


def _set_attachment_evidence(
    email,
    *,
    att_index: int,
    **evidence: Any,
) -> None:
    """Persist attachment evidence semantics on the parsed email object."""
    attachments = getattr(email, "attachments", None) or []
    if 0 <= att_index < len(attachments):
        attachment = attachments[att_index]
        values = _attachment_evidence_values(evidence)
        attachment.update(values)
        attachment["surfaces"] = build_attachment_surfaces(
            attachment_id=attachment["attachment_id"],
            extracted_text=attachment["extracted_text"],
            normalized_text=attachment["normalized_text"],
            text_locator=attachment.get("text_locator") or {},
            extraction_state=attachment["extraction_state"],
            evidence_strength=attachment["evidence_strength"],
            ocr_used=bool(attachment["ocr_used"]),
            ocr_confidence=float(attachment["ocr_confidence"] or 0.0),
            surfaces=attachment.get("surfaces"),
        )


def _attachment_evidence_values(evidence: dict[str, Any]) -> dict[str, Any]:
    """Derive evidence strength, OCR use, and extraction state for an attachment."""
    defaults: dict[str, Any] = {
        "extraction_state": "",
        "evidence_strength": "",
        "ocr_used": False,
        "ocr_engine": "",
        "ocr_lang": "",
        "ocr_confidence": 0.0,
        "failure_reason": None,
        "text_preview": "",
        "extracted_text": "",
        "normalized_text": "",
        "text_normalization_version": 0,
        "text_source_path": "",
        "text_locator": {},
        "attachment_id": "",
        "content_sha256": "",
        "locator_version": 1,
    }
    values = defaults | evidence
    values["ocr_used"] = bool(values["ocr_used"])
    values["ocr_confidence"] = float(values["ocr_confidence"] or 0.0)
    values["text_normalization_version"] = int(values["text_normalization_version"] or 0)
    values["text_locator"] = dict(values["text_locator"] or {})
    values["attachment_id"] = str(values["attachment_id"] or "")
    values["content_sha256"] = str(values["content_sha256"] or "")
    values["locator_version"] = int(values["locator_version"] or 1)
    return values


def _attachment_text_preview(text: str, *, max_chars: int = 280) -> str:
    """Return a compact persisted preview for extracted attachment text."""
    collapsed = " ".join((text or "").split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 3].rstrip() + "..."


def _mailbox_attachment_locator(
    *,
    email_uid: str,
    att_index: int,
    filename: str,
    extraction_state: str,
    attachment_id: str = "",
    content_sha256: str = "",
    extracted_text: str = "",
) -> dict[str, Any]:
    """Create a locator dictionary for a mailbox attachment.

    Extracts metadata from attachment text such as page numbers, sheet names,
    cell ranges, and archive member paths.

    Args:
        email_uid: The unique identifier of the parent email.
        att_index: The attachment index within the email.
        filename: The attachment filename.
        extraction_state: The state of text extraction (e.g., 'text_extracted', 'ocr_text_extracted').
        attachment_id: Optional attachment identifier.
        content_sha256: Optional SHA256 hash of attachment content.
        extracted_text: The extracted text from the attachment.

    Returns:
        A dictionary containing locator metadata for the attachment.
    """
    return {
        "kind": "mailbox_attachment",
        "locator_version": 2,
        "email_uid": email_uid,
        "attachment_index": att_index,
        "filename": filename,
        "attachment_id": str(attachment_id or ""),
        "content_sha256": str(content_sha256 or ""),
        "extraction_state": extraction_state,
        **_attachment_locator_details(extracted_text),
    }


def _attachment_locator_details(extracted_text: str) -> dict[str, Any]:
    """Build stable attachment locator fields from IDs, hashes, and indexes."""
    text = str(extracted_text or "")
    pages = [int(match) for match in re.findall(r"\[Page\s+(\d+)\]", text, flags=re.IGNORECASE) if match.isdigit()]
    return {
        "page_number": min(pages) if pages else None,
        "page_count": max(pages) if pages else None,
        "sheet_name": _locator_match(r"\[Sheet:\s*([^\]]+)\]", text),
        "cell_range": _locator_match(r"\b([A-Z]{1,4}\d{1,7}\s*:\s*[A-Z]{1,4}\d{1,7})\b", text).replace(" ", ""),
        "archive_member_path": _locator_match(r"\[Member:\s*([^\]]+)\]", text),
    }


def _locator_match(pattern: str, text: str) -> str:
    """Compare two locator mappings using their shared stable fields."""
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return str(match.group(1) if match else "").strip()


def _is_locator_rich(locator: dict[str, Any]) -> bool:
    """Check if a locator dictionary contains meaningful metadata.

    Args:
        locator: A dictionary containing locator metadata.

    Returns:
        True if any of page_number, sheet_name, cell_range, or archive_member_path
        contain non-empty/non-zero values.
    """
    for key in ("page_number", "sheet_name", "cell_range", "archive_member_path"):
        value = locator.get(key)
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, int) and value > 0:
            return True
    return False


def _looks_like_weak_language_signal(text: str) -> bool:
    """Determine if extracted text appears to be a weak language signal.

    Text is considered weak if it has fewer than 4 tokens total, or fewer than
    3 alphabetic tokens.

    Args:
        text: The text to evaluate.

    Returns:
        True if the text appears to be a weak language signal.
    """
    tokens = [token for token in re.split(r"\s+", str(text or "").strip()) if token]
    if len(tokens) < 4:
        return True
    alpha_tokens = [token for token in tokens if re.search(r"[A-Za-zÄÖÜäöüß]", token)]
    return len(alpha_tokens) < 3


def _textless_attachment_state(*, filename: str, mime_type: str) -> tuple[str, str]:
    """Determine attachment state for textless attachments without OCR.

    Args:
        filename: The attachment filename.
        mime_type: The MIME type of the attachment.

    Returns:
        A tuple of (extraction_state, failure_reason) for the attachment.
    """
    return _textless_attachment_state_with_ocr(
        filename=filename,
        mime_type=mime_type,
        ocr_attempted=False,
        ocr_available=False,
    )


def _textless_attachment_state_with_ocr(
    *,
    filename: str,
    mime_type: str,
    ocr_attempted: bool,
    ocr_available: bool,
) -> tuple[str, str]:
    """Determine attachment state for textless attachments considering OCR availability.

    Args:
        filename: The attachment filename.
        mime_type: The MIME type of the attachment.
        ocr_attempted: Whether OCR was attempted on the attachment.
        ocr_available: Whether OCR is available for this attachment type.

    Returns:
        A tuple of (extraction_state, failure_reason) for the attachment.
    """
    profile = attachment_format_profile(
        filename=filename,
        mime_type=mime_type,
        extraction_state="binary_only",
        evidence_strength="weak_reference",
        ocr_used=False,
        text_available=False,
    )
    if attachment_supports_ocr(filename, mime_type=mime_type):
        if ocr_attempted and ocr_available:
            return "ocr_failed", "ocr_failed"
        return "binary_only", "no_text_extracted_ocr_not_available"
    support_level = str(profile.get("support_level") or "")
    if support_level == "unsupported":
        return "unsupported", str(profile.get("degrade_reason") or "unsupported_format")
    return "binary_only", str(profile.get("degrade_reason") or "no_text_extracted")


def _attachment_surface(runtime: _IngestRuntime, email: Any, att_index: int) -> dict[str, Any]:
    """Create a normalized attachment surface from extraction output."""
    attachments = getattr(email, "attachments", None) or []
    record = attachments[att_index] if 0 <= att_index < len(attachments) else {}
    surfaces = record.get("surfaces") if isinstance(record, dict) else []
    for surface in surfaces if isinstance(surfaces, list) else []:
        if isinstance(surface, dict):
            kind = str(surface.get("surface_kind") or "reference_only")
            runtime.surface_mix[kind] = runtime.surface_mix.get(kind, 0) + 1
    primary = primary_surface_payload(surfaces)
    locator = primary.get("locator") if isinstance(primary, dict) else {}
    runtime.counters.locator_rich += int(isinstance(locator, dict) and _is_locator_rich(locator))
    return primary


def _record_attachment_identity(runtime: _IngestRuntime, content_sha256: str) -> None:
    """Store stable attachment identity fields on the email and surface metadata."""
    runtime.counters.attachments_seen += 1
    if not content_sha256:
        return
    if content_sha256 in runtime.content_hashes:
        runtime.counters.duplicate_content += 1
    else:
        runtime.content_hashes.add(content_sha256)


def _image_chunk_metadata(
    email: Any,
    email_dict: dict[str, Any],
    filename: str,
    att_index: int,
    identity: tuple[str, str],
    surface: dict[str, Any],
) -> dict[str, Any]:
    """Build locator and extraction metadata for an image embedding chunk."""
    locator = surface.get("locator") if isinstance(surface.get("locator"), dict) else {}
    return _attachment_parent_metadata(email, email_dict) | {
        "chunk_type": "image",
        "candidate_kind": "attachment",
        "is_attachment": "True",
        "filename": filename,
        "attachment_name": filename,
        "attachment_filename": filename,
        "attachment_type": filename.rsplit(".", 1)[-1].lower() if "." in filename else "",
        "attachment_id": identity[0],
        "content_sha256": identity[1],
        "extraction_state": "image_embedding_only",
        "evidence_strength": "weak_reference",
        "ocr_used": "False",
        "failure_reason": "no_text_extracted",
        "source_scope": "attachment_text",
        "segment_ordinal": str(att_index),
        "surface_id": str(surface.get("surface_id") or ""),
        "surface_kind": str(surface.get("surface_kind") or "reference_only"),
        "origin_kind": str(surface.get("origin_kind") or "reference"),
        "surface_locator_json": json.dumps(locator, ensure_ascii=False),
    }


def _process_image_attachment(
    runtime: _IngestRuntime,
    email: Any,
    email_dict: dict[str, Any],
    att_index: int,
    filename: str,
    content: bytes,
    identity: tuple[str, str],
) -> int | None:
    """Embed supported images and record weak-reference evidence when text is unavailable."""
    if not (runtime.image_embedder and runtime.image_matcher and runtime.image_matcher(filename)):
        return None
    from mailarium.model.chunks import EmailChunk

    embedding = runtime.image_embedder(filename, content)
    _set_attachment_evidence(
        email,
        att_index=att_index,
        extraction_state="image_embedding_only",
        evidence_strength="weak_reference",
        ocr_used=False,
        failure_reason="no_text_extracted_ocr_not_available",
        text_locator=_mailbox_attachment_locator(
            email_uid=email.uid,
            att_index=att_index,
            filename=filename,
            extraction_state="image_embedding_only",
            attachment_id=identity[0],
            content_sha256=identity[1],
        ),
        attachment_id=identity[0],
        content_sha256=identity[1],
        locator_version=2,
    )
    surface = _attachment_surface(runtime, email, att_index)
    if not embedding or not runtime.embedder:
        return 0
    runtime.pending_chunks.append(
        EmailChunk(
            uid=email.uid,
            chunk_id=f"{email.uid}__img_{att_index}",
            text=f"[Image attachment: {filename}]",
            metadata=_image_chunk_metadata(email, email_dict, filename, att_index, identity, surface),
            embedding=embedding,
        )
    )
    runtime.counters.chunks += 1
    runtime.counters.image_embeddings += 1
    return 1


def _extract_attachment_text(
    runtime: _IngestRuntime,
    filename: str,
    content: bytes,
    mime_type: str,
) -> tuple[str | None, str | None, bool]:
    """Run text extraction and return normalized text plus extraction metadata."""
    text, failure_reason = runtime.attachment_extractor(filename, content, mime_type=mime_type)
    ocr_used = False
    if not text and runtime.attachment_ocr_extractor:
        ocr_text = runtime.attachment_ocr_extractor(filename, content)
        if ocr_text:
            text, ocr_used = ocr_text, True
    return text, failure_reason, ocr_used


def _persist_attachment_text(
    runtime: _IngestRuntime,
    email: Any,
    att_index: int,
    filename: str,
    identity: tuple[str, str],
    text: str,
    ocr_used: bool,
) -> tuple[str, str, dict[str, Any]]:
    """Persist attachment text while preserving the invariants of email ingestion."""
    state = runtime.classify_text_state(filename, text, ocr_used=ocr_used)
    normalized = _set_extracted_attachment_text_evidence(
        email,
        att_index=att_index,
        filename=filename,
        attachment_id=identity[0],
        content_sha256=identity[1],
        text=text,
        state=state,
        ocr_used=ocr_used,
    )
    runtime.counters.weak_language += int(_looks_like_weak_language_signal(text))
    runtime.counters.ocr_only += int(ocr_used and state == "ocr_text_extracted")
    return normalized, state, _attachment_surface(runtime, email, att_index)


def _set_extracted_attachment_text_evidence(
    email: Any,
    *,
    att_index: int,
    filename: str,
    attachment_id: str,
    content_sha256: str,
    text: str,
    state: str,
    ocr_used: bool,
) -> str:
    """Persist extracted text and its provenance on an attachment, then return normalized text."""
    normalized = normalize_attachment_search_text(text)
    ocr_lang = str(os.environ.get("ATTACHMENT_OCR_LANG", DEFAULT_ATTACHMENT_OCR_LANG) or "").strip()
    ocr_lang = ocr_lang or DEFAULT_ATTACHMENT_OCR_LANG
    _set_attachment_evidence(
        email,
        att_index=att_index,
        extraction_state=state,
        evidence_strength="strong_text",
        ocr_used=ocr_used,
        ocr_engine="tesseract" if ocr_used else "",
        ocr_lang=ocr_lang if ocr_used else "",
        failure_reason=None,
        text_preview=_attachment_text_preview(text),
        extracted_text=text,
        normalized_text=normalized,
        text_normalization_version=ATTACHMENT_TEXT_NORMALIZATION_VERSION if normalized else 0,
        text_source_path=f"attachment://{email.uid}/{att_index}/{filename}",
        text_locator=_mailbox_attachment_locator(
            email_uid=email.uid,
            att_index=att_index,
            filename=filename,
            extraction_state=state,
            attachment_id=attachment_id,
            content_sha256=content_sha256,
            extracted_text=text,
        ),
        attachment_id=attachment_id,
        content_sha256=content_sha256,
        locator_version=2,
    )
    return normalized


def _attachment_parent_metadata(email: Any, email_dict: dict[str, Any]) -> dict[str, Any]:
    """Collect email and attachment identity fields shared by attachment chunks."""
    return {
        "uid": email.uid,
        "subject": email_dict.get("subject", ""),
        "sender_name": email_dict.get("sender_name", ""),
        "sender_email": email_dict.get("sender_email", ""),
        "date": email_dict.get("date", ""),
        "folder": email_dict.get("folder", ""),
    }


def _chunk_attachment_text(
    runtime: _IngestRuntime,
    email: Any,
    email_dict: dict[str, Any],
    att_index: int,
    filename: str,
    identity: tuple[str, str],
    text: str,
    normalized: str,
    state: str,
    ocr_used: bool,
    surface: dict[str, Any],
) -> list[Any]:
    """Split extracted attachment text and attach parent provenance metadata."""
    locator = surface.get("locator") if isinstance(surface.get("locator"), dict) else {}
    return runtime.dependencies.chunk_attachment(
        email_uid=email.uid,
        filename=filename,
        text=text,
        normalized_text=normalized,
        parent_metadata=_attachment_parent_metadata(email, email_dict),
        att_index=att_index,
        attachment_id=identity[0],
        content_sha256=identity[1],
        extraction_state=state,
        evidence_strength="strong_text",
        ocr_used=ocr_used,
        failure_reason=None,
        surface_id=str(surface.get("surface_id") or ""),
        surface_kind=str(surface.get("surface_kind") or "verbatim"),
        surface_origin_kind=str(surface.get("origin_kind") or "native"),
        surface_locator=locator,
        surface_ocr_confidence=float(surface.get("ocr_confidence") or 0.0),
    )


def _persist_attachment_failure(
    runtime: _IngestRuntime,
    email: Any,
    att_index: int,
    filename: str,
    mime_type: str,
    identity: tuple[str, str],
    extraction_reason: str | None,
) -> None:
    """Persist attachment failure while preserving the invariants of email ingestion."""
    if extraction_reason:
        state, reason = "extraction_failed", extraction_reason
    else:
        state, reason = _textless_attachment_state_with_ocr(
            filename=filename,
            mime_type=mime_type,
            ocr_attempted=bool(runtime.attachment_ocr_extractor),
            ocr_available=attachment_ocr_available_for(filename, mime_type=mime_type),
        )
    _set_attachment_evidence(
        email,
        att_index=att_index,
        extraction_state=state,
        evidence_strength="weak_reference",
        ocr_used=False,
        failure_reason=reason,
        text_locator=_mailbox_attachment_locator(
            email_uid=email.uid,
            att_index=att_index,
            filename=filename,
            extraction_state=state,
            attachment_id=identity[0],
            content_sha256=identity[1],
        ),
        attachment_id=identity[0],
        content_sha256=identity[1],
        locator_version=2,
    )
    _attachment_surface(runtime, email, att_index)
    profile = attachment_format_profile(
        filename=filename,
        mime_type=mime_type,
        extraction_state=state,
        evidence_strength="weak_reference",
        ocr_used=False,
        text_available=False,
    )
    key = str(profile.get("format_id") or filename.rsplit(".", 1)[-1].lower() or "unknown")
    runtime.format_failures[key] = runtime.format_failures.get(key, 0) + 1


def _process_attachment(
    runtime: _IngestRuntime,
    email: Any,
    email_dict: dict[str, Any],
    att_index: int,
    filename: str,
    content: bytes,
) -> tuple[int, int]:
    """Route image or text extraction and queue the resulting attachment chunks."""
    attachments = getattr(email, "attachments", None) or []
    metadata = attachments[att_index] if 0 <= att_index < len(attachments) else {}
    mime_type = str((metadata or {}).get("mime_type") or "")
    identity = ensure_attachment_identity(metadata, content_bytes=content)
    _record_attachment_identity(runtime, identity[1])
    image_count = _process_image_attachment(
        runtime,
        email,
        email_dict,
        att_index,
        filename,
        content,
        identity,
    )
    if image_count is not None:
        return 0, image_count
    text, extraction_reason, ocr_used = _extract_attachment_text(runtime, filename, content, mime_type)
    if not text:
        _persist_attachment_failure(
            runtime,
            email,
            att_index,
            filename,
            mime_type,
            identity,
            extraction_reason,
        )
        return 0, 0
    normalized, state, surface = _persist_attachment_text(
        runtime,
        email,
        att_index,
        filename,
        identity,
        text,
        ocr_used,
    )
    chunks = _chunk_attachment_text(
        runtime,
        email,
        email_dict,
        att_index,
        filename,
        identity,
        text,
        normalized,
        state,
        ocr_used,
        surface,
    )
    runtime.counters.chunks += len(chunks)
    runtime.counters.attachment_chunks += len(chunks)
    if runtime.embedder:
        runtime.pending_chunks.extend(chunks)
    return len(chunks), 0
