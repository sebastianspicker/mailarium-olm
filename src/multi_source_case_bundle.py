"""Multi-source case-evidence fusion for behavioural-analysis cases."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

MULTI_SOURCE_CASE_BUNDLE_VERSION = "1"
_DECLARED_SOURCE_TYPES = ("email", "attachment", "meeting_note", "chat_log", "formal_document")
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


def _is_formal_document(attachment: dict[str, Any]) -> bool:
    """Return whether an attachment should be surfaced as a formal document source."""
    filename = str(attachment.get("filename") or "").strip()
    mime_type = str(attachment.get("mime_type") or "").strip().lower()
    if Path(filename).suffix.lower() in _FORMAL_DOCUMENT_EXTENSIONS:
        return True
    return any(marker in mime_type for marker in _FORMAL_DOCUMENT_MIME_MARKERS)


def _source_reliability_for_email(candidate: dict[str, Any]) -> dict[str, Any]:
    """Return source reliability metadata for one email-body source."""
    weak_message = candidate.get("weak_message")
    verification_status = str(candidate.get("verification_status") or "")
    if weak_message:
        return {
            "level": "medium",
            "basis": "weak_message_semantics",
            "caveats": ["Email body is available, but the message was already classified as weak evidence."],
        }
    if "forensic" in verification_status:
        return {
            "level": "high",
            "basis": "forensic_body_verification",
            "caveats": [],
        }
    return {
        "level": "high",
        "basis": "authored_email_body",
        "caveats": [],
    }


def _source_reliability_for_attachment(candidate: dict[str, Any], *, source_type: str) -> dict[str, Any]:
    """Return source reliability metadata for one attachment-backed source."""
    raw_attachment = candidate.get("attachment")
    attachment: dict[str, Any] = raw_attachment if isinstance(raw_attachment, dict) else {}
    evidence_strength = str(attachment.get("evidence_strength") or "")
    extraction_state = str(attachment.get("extraction_state") or "")
    if evidence_strength == "strong_text":
        basis = "attachment_text_extracted"
        if source_type == "formal_document":
            basis = "formal_document_text_extracted"
        return {
            "level": "high",
            "basis": basis,
            "caveats": [],
        }
    return {
        "level": "low",
        "basis": extraction_state or "attachment_reference_only",
        "caveats": ["Attachment is represented as a reference hit without extracted strong-text evidence."],
    }


def _source_reliability_for_meeting(note: dict[str, Any]) -> dict[str, Any]:
    """Return source reliability metadata for one meeting-note source."""
    extracted_from = str(note.get("_extracted_from") or "")
    if extracted_from == "meeting_data":
        return {
            "level": "high",
            "basis": "calendar_meeting_metadata",
            "caveats": [],
        }
    return {
        "level": "medium",
        "basis": "exchange_extracted_meeting_reference",
        "caveats": ["Meeting context was extracted from Exchange metadata rather than authored narrative text."],
    }


def _weighting_metadata(*, source_type: str, reliability_level: str, text_available: bool) -> dict[str, Any]:
    """Return simple weighting metadata for downstream evidence consumers."""
    base_weight = 0.4
    if reliability_level == "medium":
        base_weight = 0.7
    elif reliability_level == "high":
        base_weight = 1.0
    return {
        "weight_label": reliability_level,
        "base_weight": base_weight,
        "text_available": text_available,
        "can_corroborate_or_contradict": text_available and source_type in {"email", "attachment", "formal_document"},
    }


def _meeting_note_sources(uid: str, full_email: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return meeting-note sources derivable from the current full email row."""
    email = full_email or {}
    sources: list[dict[str, Any]] = []
    meeting_data = email.get("meeting_data")
    if isinstance(meeting_data, dict) and meeting_data:
        note = {
            "source_id": f"meeting:{uid}:meeting_data",
            "source_type": "meeting_note",
            "document_kind": "calendar_metadata",
            "uid": uid,
            "parent_source_id": f"email:{uid}",
            "title": str(email.get("subject") or meeting_data.get("subject") or ""),
            "snippet": "; ".join(f"{key}={value}" for key, value in sorted(meeting_data.items())[:3]),
            "date": str(email.get("date") or ""),
            "provenance": {
                "uid": uid,
                "meeting_source": "meeting_data",
            },
            "_extracted_from": "meeting_data",
        }
        reliability = _source_reliability_for_meeting(note)
        note["source_reliability"] = reliability
        note["source_weighting"] = _weighting_metadata(
            source_type="meeting_note",
            reliability_level=str(reliability["level"]),
            text_available=True,
        )
        sources.append(note)
    exchange_meetings = email.get("exchange_extracted_meetings")
    if isinstance(exchange_meetings, list):
        for index, meeting in enumerate(exchange_meetings, start=1):
            if not isinstance(meeting, dict) or not meeting:
                continue
            note = {
                "source_id": f"meeting:{uid}:exchange:{index}",
                "source_type": "meeting_note",
                "document_kind": "exchange_meeting_reference",
                "uid": uid,
                "parent_source_id": f"email:{uid}",
                "title": str(meeting.get("subject") or email.get("subject") or ""),
                "snippet": "; ".join(f"{key}={value}" for key, value in sorted(meeting.items())[:3]),
                "date": str(email.get("date") or ""),
                "provenance": {
                    "uid": uid,
                    "meeting_source": "exchange_extracted_meetings",
                    "index": index,
                },
                "_extracted_from": "exchange_extracted_meetings",
            }
            reliability = _source_reliability_for_meeting(note)
            note["source_reliability"] = reliability
            note["source_weighting"] = _weighting_metadata(
                source_type="meeting_note",
                reliability_level=str(reliability["level"]),
                text_available=True,
            )
            sources.append(note)
    return sources


def build_multi_source_case_bundle(
    *,
    case_bundle: dict[str, Any] | None,
    candidates: list[dict[str, Any]],
    attachment_candidates: list[dict[str, Any]],
    full_map: dict[str, Any],
) -> dict[str, Any] | None:
    """Return a conservative multi-source evidence bundle for case-scoped analysis."""
    scope = (case_bundle or {}).get("scope") if isinstance(case_bundle, dict) else None
    if not isinstance(scope, dict):
        return None

    sources: list[dict[str, Any]] = []
    source_links: list[dict[str, Any]] = []
    source_type_counts: Counter[str] = Counter()
    email_source_ids_by_uid: dict[str, str] = {}

    for candidate in candidates:
        uid = str(candidate.get("uid") or "")
        if not uid:
            continue
        source_id = f"email:{uid}"
        email_source_ids_by_uid[uid] = source_id
        reliability = _source_reliability_for_email(candidate)
        source = {
            "source_id": source_id,
            "source_type": "email",
            "document_kind": "email_body",
            "uid": uid,
            "actor_id": str(candidate.get("sender_actor_id") or ""),
            "title": str(candidate.get("subject") or ""),
            "date": str(candidate.get("date") or ""),
            "snippet": str(candidate.get("snippet") or ""),
            "provenance": dict(candidate.get("provenance") or {}),
            "follow_up": dict(candidate.get("follow_up") or {}),
            "source_reliability": reliability,
            "source_weighting": _weighting_metadata(
                source_type="email",
                reliability_level=str(reliability["level"]),
                text_available=bool(str(candidate.get("snippet") or "").strip()),
            ),
        }
        sources.append(source)
        source_type_counts["email"] += 1

        for note in _meeting_note_sources(uid, full_map.get(uid) if isinstance(full_map, dict) else None):
            note.pop("_extracted_from", None)
            sources.append(note)
            source_type_counts["meeting_note"] += 1
            source_links.append(
                {
                    "from_source_id": note["source_id"],
                    "to_source_id": source_id,
                    "link_type": "extracted_from_email",
                    "relationship": "contextual_metadata",
                }
            )

    for candidate in attachment_candidates:
        uid = str(candidate.get("uid") or "")
        raw_attachment = candidate.get("attachment")
        attachment: dict[str, Any] = raw_attachment if isinstance(raw_attachment, dict) else {}
        source_type = "formal_document" if _is_formal_document(attachment) else "attachment"
        filename = str(attachment.get("filename") or "attachment")
        source_id = f"{source_type}:{uid}:{filename}"
        reliability = _source_reliability_for_attachment(candidate, source_type=source_type)
        source = {
            "source_id": source_id,
            "source_type": source_type,
            "document_kind": "attachment" if source_type == "attachment" else "attached_document",
            "uid": uid,
            "actor_id": str(candidate.get("sender_actor_id") or ""),
            "title": filename,
            "date": str(candidate.get("date") or ""),
            "snippet": str(candidate.get("snippet") or ""),
            "provenance": dict(candidate.get("provenance") or {}),
            "attachment": dict(attachment),
            "follow_up": dict(candidate.get("follow_up") or {}),
            "source_reliability": reliability,
            "source_weighting": _weighting_metadata(
                source_type=source_type,
                reliability_level=str(reliability["level"]),
                text_available=bool(attachment.get("text_available")),
            ),
        }
        sources.append(source)
        source_type_counts[source_type] += 1
        parent_source_id = email_source_ids_by_uid.get(uid) or f"email:{uid}"
        weighting = source["source_weighting"]
        can_corroborate_or_contradict = isinstance(weighting, dict) and bool(
            weighting.get("can_corroborate_or_contradict")
        )
        source_links.append(
            {
                "from_source_id": source_id,
                "to_source_id": parent_source_id,
                "link_type": "attached_to_email",
                "relationship": (
                    "can_corroborate_or_contradict_message"
                    if can_corroborate_or_contradict
                    else "reference_only_attachment"
                ),
            }
        )

    available_source_types = sorted(source_type_counts)
    missing_source_types = [source_type for source_type in _DECLARED_SOURCE_TYPES if source_type not in source_type_counts]
    direct_text_source_count = sum(1 for source in sources if source["source_weighting"]["text_available"])
    contradiction_ready_source_count = sum(
        1 for source in sources if source["source_weighting"]["can_corroborate_or_contradict"]
    )

    source_type_profiles = [
        {
            "source_type": source_type,
            "available": source_type in source_type_counts,
            "count": int(source_type_counts.get(source_type, 0)),
            "availability_reason": (
                "present_in_current_case_evidence"
                if source_type in source_type_counts
                else "not_available_in_current_case_evidence"
            ),
        }
        for source_type in _DECLARED_SOURCE_TYPES
    ]

    return {
        "version": MULTI_SOURCE_CASE_BUNDLE_VERSION,
        "summary": {
            "source_count": len(sources),
            "source_type_counts": dict(source_type_counts),
            "available_source_types": available_source_types,
            "missing_source_types": missing_source_types,
            "link_count": len(source_links),
            "direct_text_source_count": direct_text_source_count,
            "contradiction_ready_source_count": contradiction_ready_source_count,
        },
        "sources": sources,
        "source_links": source_links,
        "source_type_profiles": source_type_profiles,
    }
