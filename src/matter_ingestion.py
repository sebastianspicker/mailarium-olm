"""Matter-manifest normalization and completeness-ledger helpers."""
# pylint: disable=too-many-locals,too-many-return-statements

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from ._utils import _as_dict, _as_list, _compact
from .attachment_extractor import attachment_format_profile, extraction_quality_profile

MATTER_INGESTION_REPORT_VERSION = "1"
_MANIFEST_SUBJECT_RE = re.compile(r"(?im)^(?:subject|betreff):\s*(.+)$")
_MANIFEST_FROM_RE = re.compile(r"(?im)^(?:from|von):\s*(.+)$")
_MANIFEST_TO_RE = re.compile(r"(?im)^(?:to|an):\s*(.+)$")
_MANIFEST_CC_RE = re.compile(r"(?im)^(?:cc|kopie):\s*(.+)$")
_MANIFEST_BCC_RE = re.compile(r"(?im)^(?:bcc|blindkopie):\s*(.+)$")
_MANIFEST_DATE_RE = re.compile(r"(?im)^(?:date|datum|gesendet):\s*([^\n\r]+)$")
_MANIFEST_MESSAGE_ID_RE = re.compile(r"(?im)^(?:message-id|message-id:|nachrichten-id):\s*(.+)$")
_MANIFEST_IN_REPLY_TO_RE = re.compile(r"(?im)^(?:in-reply-to|antwort-auf):\s*(.+)$")
_MANIFEST_REFERENCES_RE = re.compile(r"(?im)^references:\s*(.+)$")
_MANIFEST_HEADING_RE = re.compile(r"(?m)^#\s+(.+)$")
_PARTY_WITH_EMAIL_RE = re.compile(r"[^<>\n]+<[^>]+>")

_SOURCE_CLASS_TO_TYPE: dict[str, tuple[str, str]] = {
    "email": ("email", "email_body"),
    "attachment": ("attachment", "attachment"),
    "formal_document": ("formal_document", "attached_document"),
    "personnel_file_record": ("formal_document", "personnel_file_record"),
    "job_evaluation_record": ("formal_document", "job_evaluation_record"),
    "prevention_record": ("formal_document", "prevention_record"),
    "medical_record": ("formal_document", "medical_record"),
    "meeting_note": ("meeting_note", "meeting_note"),
    "calendar_export": ("meeting_note", "calendar_export"),
    "note_record": ("note_record", "attached_note_record"),
    "time_record": ("time_record", "attached_time_record"),
    "attendance_export": ("time_record", "attendance_export"),
    "participation_record": ("participation_record", "attached_participation_record"),
    "chat_log": ("chat_log", "operator_supplied_chat_log"),
    "chat_export": ("chat_log", "chat_export"),
    "archive_bundle": ("attachment", "archive_bundle"),
    "screenshot": ("attachment", "image_attachment"),
    "other": ("attachment", "attachment"),
}


def _preview(text: str, *, max_chars: int = 280) -> str:
    """Create a preview of text truncated to max_chars.

    Args:
        text: The text to preview.
        max_chars: Maximum number of characters in the preview (default 280).

    Returns:
        The compacted text, truncated to max_chars with '...' appended if needed.
    """
    compact = _compact(text)
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def _bounded_searchable_text(value: Any, *, max_chars: int = 4000) -> str:
    """Create searchable text bounded to max_chars.

    Args:
        value: The value to convert to searchable text.
        max_chars: Maximum number of characters (default 4000).

    Returns:
        The compacted value as a string, truncated to max_chars with '...' appended if needed.
    """
    compact = _compact(value)
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def _split_party_list(value: str) -> list[str]:
    """Split a party list string into individual party entries.

    Handles email addresses with display names (e.g., 'Name <email@example.com>')
    and comma-separated lists.

    Args:
        value: The party list string to split.

    Returns:
        List of individual party strings, with whitespace compacted.
    """
    compact_value = _compact(value)
    if not compact_value:
        return []
    matches = [_compact(match.group(0).lstrip(", ")) for match in _PARTY_WITH_EMAIL_RE.finditer(compact_value)]
    if matches:
        return [match for match in matches if match]
    parts = re.split(r",\s*(?=[^,]+@)", compact_value)
    return [item for item in (_compact(part) for part in parts) if item]


def _manifest_text_metadata(artifact: dict[str, Any], *, title: str, text: str) -> dict[str, Any]:
    """Extract metadata from manifest artifact text for formal documents.

    Parses email-like headers (Subject, From, To, Cc, Bcc, Date, Message-ID,
    In-Reply-To, References) and markdown headings from the text.

    Args:
        artifact: The manifest artifact dict.
        title: Default title to use if none is found in the text.
        text: The text content to parse for metadata.

    Returns:
        Dict containing extracted metadata fields (title, author, recipients,
        cc_recipients, bcc_recipients, date, message_id, in_reply_to, references).
        Returns empty dict if artifact is not a formal_document or text is empty.
    """
    if _compact(artifact.get("source_class")) != "formal_document" or not text:
        return {}
    inferred_title = _manifest_title(artifact, title, text)
    return {
        "title": inferred_title,
        "author": _manifest_match(_MANIFEST_FROM_RE, text),
        "recipients": _split_party_list(_manifest_match(_MANIFEST_TO_RE, text)),
        "cc_recipients": _split_party_list(_manifest_match(_MANIFEST_CC_RE, text)),
        "bcc_recipients": _split_party_list(_manifest_match(_MANIFEST_BCC_RE, text)),
        "date": _manifest_match(_MANIFEST_DATE_RE, text),
        "message_id": _manifest_match(_MANIFEST_MESSAGE_ID_RE, text),
        "in_reply_to": _manifest_match(_MANIFEST_IN_REPLY_TO_RE, text),
        "references": _manifest_match(_MANIFEST_REFERENCES_RE, text),
    }


def _manifest_match(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text)
    return _compact(match.group(1)) if match else ""


def _manifest_title(artifact: dict[str, Any], fallback: str, text: str) -> str:
    subject = _manifest_match(_MANIFEST_SUBJECT_RE, text)
    if subject:
        return subject
    heading = _manifest_match(_MANIFEST_HEADING_RE, text)
    return heading if heading and heading != _compact(artifact.get("filename")) else fallback


def _looks_like_email_export(*, artifact: dict[str, Any], text_metadata: dict[str, Any]) -> bool:
    """Determine if a formal_document artifact appears to be an email export.

    Checks filename patterns and extracted metadata to identify email exports.

    Args:
        artifact: The manifest artifact dict.
        text_metadata: Extracted text metadata from the artifact.

    Returns:
        True if the artifact appears to be an email export, False otherwise.
    """
    if _compact(artifact.get("source_class")) != "formal_document":
        return False
    filename = _compact(artifact.get("filename") or artifact.get("title")).casefold()
    if filename.startswith("gmail -") or filename.endswith((".eml", ".msg")):
        return True
    has_header_metadata = bool(
        _compact(text_metadata.get("author"))
        and _as_list(text_metadata.get("recipients"))
        and _compact(text_metadata.get("date"))
    )
    return has_header_metadata


def _line_number_for_offset(text: str, offset: int) -> int:
    """Calculate the 1-based line number for a character offset in text.

    Args:
        text: The text string.
        offset: The character offset (0-based).

    Returns:
        The 1-based line number corresponding to the offset.
    """
    return text[: max(offset, 0)].count("\n") + 1


def _snippet_bounds(raw_text: str, snippet: str) -> tuple[int, int] | None:
    """Find the character bounds of a snippet within raw text.

    Performs both exact matching and normalized (whitespace-compacted) matching.

    Args:
        raw_text: The full text to search within.
        snippet: The snippet text to find.

    Returns:
        A tuple of (start, end) character offsets if found, None otherwise.
        For normalized matching, returns bounds in the original raw_text.
    """
    if not raw_text or not snippet:
        return None
    exact_start = raw_text.find(snippet)
    if exact_start >= 0:
        return exact_start, exact_start + len(snippet)
    body_chars: list[str] = []
    body_map: list[int] = []
    prev_space = False
    for idx, char in enumerate(raw_text):
        if char.isspace():
            if prev_space:
                continue
            body_chars.append(" ")
            body_map.append(idx)
            prev_space = True
        else:
            body_chars.append(char)
            body_map.append(idx)
            prev_space = False
    normalized_body = "".join(body_chars)
    normalized_snippet = _compact(snippet)
    collapsed_start = normalized_body.find(normalized_snippet)
    if collapsed_start < 0:
        return None
    start = body_map[collapsed_start]
    end = body_map[collapsed_start + len(normalized_snippet) - 1] + 1
    return start, end


def _snippet_locator(*, text: str, snippet: str, text_locator: dict[str, Any]) -> dict[str, Any]:
    """Create a snippet locator dict for a snippet within text.

    Args:
        text: The full text containing the snippet.
        snippet: The snippet text to locate.
        text_locator: The base text locator dict with char_start and optional
            source_path and content_sha256.

    Returns:
        A locator dict with kind, char_start, char_end, line_start, line_end,
        and optionally source_path and content_sha256. Returns empty dict if
        snippet is empty or text_locator is not a dict.
    """
    compact_snippet = _compact(snippet)
    if not compact_snippet or not isinstance(text_locator, dict):
        return {}
    raw_text = str(text or "")
    if not raw_text:
        return {}
    bounds = _snippet_bounds(raw_text, compact_snippet)
    if bounds is None:
        return {}
    start, end = bounds
    locator = {
        "kind": "quoted_snippet",
        "char_start": int(text_locator.get("char_start") or 0) + start,
        "char_end": int(text_locator.get("char_start") or 0) + end,
        "line_start": _line_number_for_offset(raw_text, start),
        "line_end": _line_number_for_offset(raw_text, end),
    }
    if text_locator.get("source_path"):
        locator["source_path"] = text_locator.get("source_path")
    if text_locator.get("content_sha256"):
        locator["content_sha256"] = text_locator.get("content_sha256")
    return locator


def normalized_source_mapping(source_class: str) -> tuple[str, str]:
    """Return normalized downstream source typing for one manifest source class."""
    return _SOURCE_CLASS_TO_TYPE.get(str(source_class or "").strip(), ("attachment", "attachment"))


def source_review_status(artifact: dict[str, Any]) -> str:
    """Return the effective review status for one manifest artifact."""
    review_status = _compact(artifact.get("review_status"))
    if review_status:
        return review_status
    extraction_state = _compact(artifact.get("extraction_state")).lower()
    evidence_strength = _compact(artifact.get("evidence_strength")).lower()
    if extraction_state in {"excluded"}:
        return "excluded"
    if extraction_state in {"not_reviewed", "not_yet_reviewed"}:
        return "not_yet_reviewed"
    if extraction_state in {"unsupported"}:
        return "unsupported"
    if extraction_state in {
        "binary_only",
        "image_embedding_only",
        "ocr_failed",
        "extraction_failed",
        "archive_inventory_extracted",
        "sidecar_text_extracted",
    }:
        return "degraded"
    if evidence_strength == "weak_reference":
        return "degraded"
    return "parsed"


def documentary_support_for_manifest_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    """Return documentary support metadata for one manifest artifact."""
    filename = _compact(artifact.get("filename"))
    mime_type = _compact(artifact.get("mime_type")).lower()
    extraction_state = _compact(artifact.get("extraction_state")) or (
        "text_extracted" if _compact(artifact.get("text")) else "not_reviewed"
    )
    evidence_strength = _compact(artifact.get("evidence_strength")) or (
        "strong_text" if _compact(artifact.get("text")) else "weak_reference"
    )
    ocr_used = bool(artifact.get("ocr_used"))
    format_profile = attachment_format_profile(
        filename=filename,
        mime_type=mime_type,
        extraction_state=extraction_state,
        evidence_strength=evidence_strength,
        ocr_used=ocr_used,
        text_available=bool(_compact(artifact.get("text"))),
    )
    extraction_quality = extraction_quality_profile(
        extraction_state=extraction_state,
        evidence_strength=evidence_strength,
        ocr_used=ocr_used,
        format_profile=format_profile,
    )
    return {
        "filename": filename,
        "mime_type": mime_type,
        "text_available": bool(_compact(artifact.get("text"))),
        "evidence_strength": evidence_strength,
        "extraction_state": extraction_state,
        "ocr_used": ocr_used,
        "failure_reason": _compact(artifact.get("failure_reason") or artifact.get("excluded_reason")),
        "text_preview": _preview(str(artifact.get("text") or "")),
        "format_profile": format_profile,
        "extraction_quality": extraction_quality,
    }


def manifest_promotability_profile(
    artifact: dict[str, Any],
    *,
    documentary_support: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return promotability and lead semantics for one manifest artifact."""
    documentary = (
        documentary_support if isinstance(documentary_support, dict) else documentary_support_for_manifest_artifact(artifact)
    )
    format_profile = _as_dict(documentary.get("format_profile"))
    extraction_quality = _as_dict(documentary.get("extraction_quality"))
    weak_format_semantics = _as_dict(artifact.get("weak_format_semantics"))
    review_status = source_review_status(artifact)
    text_available = bool(documentary.get("text_available"))
    evidence_strength = str(documentary.get("evidence_strength") or "")
    support_level = str(format_profile.get("support_level") or "")
    lossiness = str(extraction_quality.get("lossiness") or "")
    manual_review_required = bool(
        format_profile.get("manual_review_required") or extraction_quality.get("manual_review_required")
    )
    recovery_mode = str(weak_format_semantics.get("recovery_mode") or "")

    promotability_status = _promotability_status(
        review_status=review_status,
        support_level=support_level,
        text_available=text_available,
        recovery_mode=recovery_mode,
        evidence_strength=evidence_strength,
        manual_review_required=manual_review_required,
        lossiness=lossiness,
        ocr_used=bool(documentary.get("ocr_used")),
    )

    chronology_ready = bool(_compact(artifact.get("date")) or text_available)
    contradiction_ready = promotability_status in {"promotable_direct", "promotable_with_original_check"}
    lead_summary = (
        _compact(artifact.get("summary"))
        or _compact(artifact.get("title"))
        or _compact(artifact.get("filename"))
        or _compact(artifact.get("source_id"))
    )
    return {
        "promotability_status": promotability_status,
        "chronology_ready": chronology_ready,
        "contradiction_ready": contradiction_ready,
        "low_confidence_lead": _low_confidence_lead(promotability_status, recovery_mode, lead_summary),
    }


def _promotability_status(
    *,
    review_status: str,
    support_level: str,
    text_available: bool,
    recovery_mode: str,
    evidence_strength: str,
    manual_review_required: bool,
    lossiness: str,
    ocr_used: bool,
) -> str:
    if _reference_only(review_status, support_level, text_available, recovery_mode):
        return "reference_only_not_promotable"
    if recovery_mode == "sidecar_transcript":
        return "lead_only_manual_review"
    original_check = _requires_original_check(manual_review_required, lossiness, ocr_used)
    if _strong_parsed(text_available, review_status, evidence_strength):
        return "promotable_with_original_check" if original_check else "promotable_direct"
    if _weak_or_textless(text_available, evidence_strength):
        return "lead_only_manual_review" if recovery_mode else "reference_only_not_promotable"
    if _degraded_lead(review_status, manual_review_required, lossiness):
        return "lead_only_manual_review"
    if original_check:
        return "promotable_with_original_check"
    return (
        "promotable_direct"
        if review_status == "parsed" and evidence_strength == "strong_text"
        else "reference_only_not_promotable"
    )


def _requires_original_check(manual_review_required: bool, lossiness: str, ocr_used: bool) -> bool:
    return manual_review_required or lossiness in {"medium", "high"} or ocr_used


def _strong_parsed(text_available: bool, review_status: str, evidence_strength: str) -> bool:
    return text_available and review_status == "parsed" and evidence_strength == "strong_text"


def _weak_or_textless(text_available: bool, evidence_strength: str) -> bool:
    return not text_available or evidence_strength == "weak_reference"


def _degraded_lead(review_status: str, manual_review_required: bool, lossiness: str) -> bool:
    return review_status == "degraded" and (manual_review_required or lossiness == "high")


def _reference_only(review_status: str, support_level: str, text_available: bool, recovery_mode: str) -> bool:
    return (
        review_status in {"unsupported", "excluded", "not_yet_reviewed"}
        or (support_level == "unsupported" and not text_available)
        or recovery_mode == "archive_member_inventory"
    )


def _low_confidence_lead(status: str, recovery_mode: str, summary: str) -> dict[str, str]:
    if status not in {"lead_only_manual_review", "reference_only_not_promotable"}:
        return {}
    action = "Check the original source before using this as evidence."
    if status == "lead_only_manual_review":
        action = "Use only as a lead until the original source is reviewed."
    return {"lead_type": recovery_mode or "manual_review_follow_up", "summary": summary, "recommended_action": action}


def _first_compact(*values: Any) -> str:
    for value in values:
        text = _compact(value)
        if text:
            return text
    return ""


def _string_list(value: Any) -> list[str]:
    return [text for item in _as_list(value) if (text := _compact(item))]


def _party_values(artifact: dict[str, Any], metadata: dict[str, Any], key: str) -> list[str]:
    values = _string_list(artifact.get(key))
    return values if values else _string_list(metadata.get(key))


def _artifact_reliability_level(review_status: str, documentary_support: dict[str, Any]) -> str:
    weak_status = review_status in {"unsupported", "excluded", "not_yet_reviewed"}
    if weak_status or str(documentary_support.get("evidence_strength") or "") == "weak_reference":
        return "low"
    if review_status == "degraded" or bool(documentary_support.get("ocr_used")):
        return "medium"
    return "high"


def _artifact_source_context(artifact: dict[str, Any], index: int) -> dict[str, Any]:
    source_class = _first_compact(artifact.get("source_class"), "other")
    source_type, document_kind = normalized_source_mapping(source_class)
    documentary_support = documentary_support_for_manifest_artifact(artifact)
    review_status = source_review_status(artifact)
    source_id = _first_compact(artifact.get("source_id"), f"manifest:{index}:{source_class}")
    initial_title = _first_compact(artifact.get("title"), artifact.get("filename"), source_id)
    raw_text = str(artifact.get("text") or "")
    text_metadata = _manifest_text_metadata(artifact, title=initial_title, text=raw_text)
    if _looks_like_email_export(artifact=artifact, text_metadata=text_metadata):
        source_type, document_kind = "email", "email_export_document"
    text = _compact(raw_text)
    text_locator = _as_dict(artifact.get("text_locator"))
    return {
        "source_class": source_class,
        "source_type": source_type,
        "document_kind": document_kind,
        "documentary_support": documentary_support,
        "promotability_profile": manifest_promotability_profile(artifact, documentary_support=documentary_support),
        "review_status": review_status,
        "reliability_level": _artifact_reliability_level(review_status, documentary_support),
        "source_id": source_id,
        "title": _first_compact(text_metadata.get("title"), initial_title),
        "raw_text": raw_text,
        "text": text,
        "summary": _compact(artifact.get("summary")),
        "text_metadata": text_metadata,
        "author": _first_compact(artifact.get("author"), text_metadata.get("author")),
        "recipients": _party_values(artifact, text_metadata, "recipients"),
        "cc_recipients": _party_values(artifact, text_metadata, "cc_recipients"),
        "bcc_recipients": _party_values(artifact, text_metadata, "bcc_recipients"),
        "participants": _string_list(artifact.get("participants")),
        "date": _first_compact(artifact.get("date"), text_metadata.get("date")),
        "text_source_path": _compact(artifact.get("text_source_path")),
        "text_locator": text_locator,
        "snippet_locator": _snippet_locator(text=raw_text, snippet=text or raw_text, text_locator=text_locator)
        if raw_text
        else {},
    }


def _source_roles(
    author: str, recipients: list[str], cc_recipients: list[str], bcc_recipients: list[str], participants: list[str]
) -> dict[str, Any]:
    return {
        "author": author,
        "recipients": recipients,
        "cc_recipients": cc_recipients,
        "bcc_recipients": bcc_recipients,
        "participants": participants,
    }


def _source_date_context(artifact: dict[str, Any], date_value: str) -> dict[str, Any]:
    date_start = _compact(artifact.get("date_start"))
    date_end = _compact(artifact.get("date_end"))
    return {
        "display_date": date_value,
        "date_start": date_start,
        "date_end": date_end,
        "is_approximate": bool(artifact.get("date_is_approximate")),
        "has_range": bool(date_start and date_end),
    }


def _source_provenance(artifact: dict[str, Any], text_metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_kind": "matter_manifest",
        "custodian": _compact(artifact.get("custodian")),
        "acquisition_date": _compact(artifact.get("acquisition_date")),
        "filename": _compact(artifact.get("filename")),
        "source_path": _compact(artifact.get("source_path")),
        "content_sha256": _compact(artifact.get("content_sha256")),
        "file_size_bytes": int(artifact.get("file_size_bytes") or 0),
        "related_email_uid": _compact(artifact.get("related_email_uid")),
        "message_id": _compact(text_metadata.get("message_id")),
        "in_reply_to": _compact(text_metadata.get("in_reply_to")),
        "references": _compact(text_metadata.get("references")),
    }


def _source_document_locator(
    artifact: dict[str, Any], source_id: str, text_source_path: str, text_locator: dict[str, Any], snippet_locator: dict[str, Any]
) -> dict[str, Any]:
    return {
        "evidence_handle": source_id,
        "source_path": _compact(artifact.get("source_path")),
        "filename": _compact(artifact.get("filename")),
        "content_sha256": _compact(artifact.get("content_sha256")),
        "text_source_path": text_source_path,
        "text_locator": text_locator,
        "snippet_locator": snippet_locator,
    }


def _source_weighting(level: str, text: str, source_type: str) -> dict[str, Any]:
    base_weight = {"high": 1.0, "medium": 0.7}.get(level, 0.4)
    corroborating_type = source_type in {
        "email",
        "attachment",
        "formal_document",
        "note_record",
        "time_record",
        "participation_record",
    }
    return {
        "weight_label": level,
        "base_weight": base_weight,
        "text_available": bool(text),
        "can_corroborate_or_contradict": bool(text) and corroborating_type,
    }


def source_from_manifest_artifact(artifact: dict[str, Any], *, index: int) -> dict[str, Any]:
    """Return one normalized mixed-source entry for a manifest artifact."""
    context = _artifact_source_context(artifact, index)
    source_class = str(context["source_class"])
    source_type = str(context["source_type"])
    document_kind = str(context["document_kind"])
    documentary_support = _as_dict(context["documentary_support"])
    promotability_profile = _as_dict(context["promotability_profile"])
    review_status = str(context["review_status"])
    reliability_level = str(context["reliability_level"])
    source_id = str(context["source_id"])
    title = str(context["title"])
    raw_text = str(context["raw_text"])
    text = str(context["text"])
    summary = str(context["summary"])
    text_metadata = _as_dict(context["text_metadata"])
    author = str(context["author"])
    recipients = _string_list(context["recipients"])
    cc_recipients = _string_list(context["cc_recipients"])
    bcc_recipients = _string_list(context["bcc_recipients"])
    participants = _string_list(context["participants"])
    date_value = str(context["date"])
    text_source_path = str(context["text_source_path"])
    text_locator = _as_dict(context["text_locator"])
    snippet_locator = _as_dict(context["snippet_locator"])
    source: dict[str, Any] = {
        "source_id": source_id,
        "source_type": source_type,
        "source_class": source_class,
        "document_kind": document_kind,
        "uid": _compact(artifact.get("related_email_uid")),
        "title": title,
        "date": date_value,
        "snippet": text,
        "searchable_text": _bounded_searchable_text(raw_text or text),
        "operator_summary": summary,
        "author": author,
        "recipients": recipients,
        "cc_recipients": cc_recipients,
        "bcc_recipients": bcc_recipients,
        "participants": participants,
        "source_roles": _source_roles(author, recipients, cc_recipients, bcc_recipients, participants),
        "date_context": _source_date_context(artifact, date_value),
        "provenance": _source_provenance(artifact, text_metadata),
        "document_locator": _source_document_locator(artifact, source_id, text_source_path, text_locator, snippet_locator),
        "documentary_support": documentary_support,
        "promotability_status": str(promotability_profile.get("promotability_status") or "reference_only_not_promotable"),
        "source_reliability": {
            "level": reliability_level,
            "basis": f"matter_manifest_{review_status or 'parsed'}",
            "caveats": ["This source entered through the operator-supplied matter manifest."]
            if source_class in {"chat_log", "chat_export"}
            else [],
        },
        "source_weighting": _source_weighting(reliability_level, text, source_type),
        "source_manifest_entry": {
            "artifact_id": source_id,
            "review_status": review_status,
            "custodian": _compact(artifact.get("custodian")),
            "expected_collection": _compact(artifact.get("expected_collection")),
        },
    }
    weak_format_semantics = _as_dict(artifact.get("weak_format_semantics"))
    if weak_format_semantics:
        source["weak_format_semantics"] = weak_format_semantics
    low_confidence_lead = _as_dict(promotability_profile.get("low_confidence_lead"))
    if low_confidence_lead:
        source["low_confidence_lead"] = low_confidence_lead
    return source


def build_matter_ingestion_report(
    *,
    review_mode: str,
    matter_manifest: dict[str, Any] | None,
    multi_source_case_bundle: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a completeness ledger for the supplied matter manifest."""
    manifest = _as_dict(matter_manifest)
    artifacts = [item for item in _as_list(manifest.get("artifacts")) if isinstance(item, dict)]
    sources = {
        str(source.get("source_id") or "")
        for source in _as_list(_as_dict(multi_source_case_bundle).get("sources"))
        if isinstance(source, dict) and str(source.get("source_id") or "")
    }
    review_status_counts: Counter[str] = Counter()
    source_class_counts: Counter[str] = Counter()
    custodian_counts: Counter[str] = Counter()
    artifact_rows: list[dict[str, Any]] = []
    for index, artifact in enumerate(artifacts, start=1):
        row = _ingestion_artifact_row(artifact, index=index, source_ids=sources)
        artifact_rows.append(row)
        _update_ingestion_counts(row, review_status_counts, source_class_counts, custodian_counts)
    summary = _ingestion_summary(artifacts, artifact_rows, review_status_counts, source_class_counts, custodian_counts)
    completeness_status = _completeness_status(review_mode, artifacts, summary)
    return _ingestion_report_payload(review_mode, manifest, artifacts, artifact_rows, summary, completeness_status)


def _ingestion_artifact_row(artifact: dict[str, Any], *, index: int, source_ids: set[str]) -> dict[str, Any]:
    source_class = _compact(artifact.get("source_class")) or "other"
    source_id = _compact(artifact.get("source_id")) or f"manifest:{index}:{source_class}"
    documentary = documentary_support_for_manifest_artifact(artifact)
    profile = manifest_promotability_profile(artifact, documentary_support=documentary)
    return {
        "artifact_id": source_id,
        "source_id": source_id,
        "title": _compact(artifact.get("title")) or _compact(artifact.get("filename")) or source_id,
        "source_class": source_class,
        "normalized_source_type": normalized_source_mapping(source_class)[0],
        "date": _compact(artifact.get("date")),
        "custodian": _compact(artifact.get("custodian")),
        "review_status": source_review_status(artifact),
        "accounting_status": "included_in_case_bundle" if source_id in source_ids else "not_in_case_bundle",
        "promotability_status": str(profile.get("promotability_status") or "reference_only_not_promotable"),
        "chronology_ready": bool(profile.get("chronology_ready")),
        "contradiction_ready": bool(profile.get("contradiction_ready")),
        "extraction_state": str(documentary.get("extraction_state") or ""),
        "evidence_strength": str(documentary.get("evidence_strength") or ""),
        "format_support_level": str(_as_dict(documentary.get("format_profile")).get("support_level") or ""),
        "related_email_uid": _compact(artifact.get("related_email_uid")),
        "source_path": _compact(artifact.get("source_path")),
        "file_size_bytes": int(artifact.get("file_size_bytes") or 0),
        "content_sha256": _compact(artifact.get("content_sha256")),
        "excluded_reason": _compact(artifact.get("excluded_reason")),
        "weak_format_semantics": _as_dict(artifact.get("weak_format_semantics")),
        "low_confidence_lead": _as_dict(profile.get("low_confidence_lead")),
    }


def _update_ingestion_counts(
    row: dict[str, Any], review_counts: Counter[str], class_counts: Counter[str], custodian_counts: Counter[str]
) -> None:
    review_counts[str(row["review_status"])] += 1
    class_counts[str(row["source_class"])] += 1
    custodian = str(row["custodian"])
    if custodian:
        custodian_counts[custodian] += 1


def _status_count(rows: list[dict[str, Any]], key: str, expected: str) -> int:
    return sum(row.get(key) == expected for row in rows)


def _ingestion_summary(
    artifacts: list[dict[str, Any]],
    artifact_rows: list[dict[str, Any]],
    review_status_counts: Counter[str],
    source_class_counts: Counter[str],
    custodian_counts: Counter[str],
) -> dict[str, Any]:
    promotable = sum(
        row.get("promotability_status") in {"promotable_direct", "promotable_with_original_check"} for row in artifact_rows
    )
    total = len(artifacts)
    accounted = _status_count(artifact_rows, "accounting_status", "included_in_case_bundle")
    return {
        "total_supplied_artifacts": len(artifacts),
        "parsed_artifacts": int(review_status_counts.get("parsed", 0)),
        "degraded_artifacts": int(review_status_counts.get("degraded", 0)),
        "unsupported_artifacts": int(review_status_counts.get("unsupported", 0)),
        "excluded_artifacts": int(review_status_counts.get("excluded", 0)),
        "not_yet_reviewed_artifacts": int(review_status_counts.get("not_yet_reviewed", 0)),
        "accounted_artifacts": accounted,
        "unaccounted_artifacts": total - accounted,
        "source_class_counts": dict(source_class_counts),
        "custodian_counts": dict(custodian_counts),
        "review_status_counts": dict(review_status_counts),
        "promotable_direct_artifacts": _status_count(artifact_rows, "promotability_status", "promotable_direct"),
        "promotable_with_original_check_artifacts": _status_count(
            artifact_rows, "promotability_status", "promotable_with_original_check"
        ),
        "lead_only_manual_review_artifacts": _status_count(artifact_rows, "promotability_status", "lead_only_manual_review"),
        "reference_only_not_promotable_artifacts": _status_count(
            artifact_rows, "promotability_status", "reference_only_not_promotable"
        ),
        "promotable_artifacts": promotable,
        "promotable_coverage": _coverage(promotable, total),
        "accounted_coverage": _coverage(accounted, total),
        "chronology_ready_artifacts": sum(bool(row.get("chronology_ready")) for row in artifact_rows),
        "contradiction_ready_artifacts": sum(bool(row.get("contradiction_ready")) for row in artifact_rows),
        "low_confidence_lead_count": sum(bool(_as_dict(row.get("low_confidence_lead"))) for row in artifact_rows),
    }


def _coverage(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def _completeness_status(review_mode: str, artifacts: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    if review_mode == "retrieval_only" and not artifacts:
        return "retrieval_only_no_manifest"
    return "complete" if summary["unaccounted_artifacts"] == 0 else "incomplete"


def _ingestion_report_payload(
    review_mode: str,
    manifest: dict[str, Any],
    artifacts: list[dict[str, Any]],
    artifact_rows: list[dict[str, Any]],
    summary: dict[str, Any],
    completeness_status: str,
) -> dict[str, Any]:
    return {
        "version": MATTER_INGESTION_REPORT_VERSION,
        "review_mode": review_mode,
        "manifest_id": _compact(manifest.get("manifest_id")),
        "summary": summary,
        "completeness_status": completeness_status,
        "accounted_completeness_status": "complete" if summary["unaccounted_artifacts"] == 0 else "incomplete",
        "promotable_completeness_status": (
            "complete"
            if len(artifacts) > 0
            and int(summary["promotable_artifacts"]) + int(summary["lead_only_manual_review_artifacts"]) == len(artifacts)
            else "incomplete"
        ),
        "is_exhaustive_review": review_mode == "exhaustive_matter_review",
        "artifacts": artifact_rows,
    }
