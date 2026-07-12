"""Multi-source case-evidence fusion for behavioural-analysis cases."""
# pylint: disable=too-many-branches,too-many-locals,too-many-statements

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from .multi_source_case_bundle_assembly import (
    append_chat_log_sources_stage,
    append_manifest_sources_stage,
)
from .multi_source_case_bundle_helpers import (
    MULTI_SOURCE_CASE_BUNDLE_VERSION,
    _attachment_document_kind,
    _attachment_source_type,
    _calendar_semantics,
    _chat_log_sources,
    _chronology_anchor_for_source,
    _document_locator,
    _documentary_support_payload,
    _meeting_note_sources,
    _source_reliability_for_attachment,
    _source_reliability_for_email,
    _spreadsheet_semantics,
    _string_list,
    _weighting_metadata,
)
from .multi_source_case_bundle_summary import _rebuild_bundle_summary


def append_chat_log_sources(
    bundle: dict[str, Any] | None,
    *,
    chat_log_entries: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Append chat log sources to an existing multi-source case bundle.

    Args:
        bundle: The existing bundle to append to, or None to create a new one.
        chat_log_entries: List of chat log entries to add as sources.

    Returns:
        The updated bundle with chat log sources added, or None if bundle is None
        and no chat log entries are provided.

    """
    return append_chat_log_sources_stage(bundle, chat_log_entries=chat_log_entries)


def append_manifest_sources(
    bundle: dict[str, Any] | None,
    *,
    matter_manifest: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Append sources from a matter manifest to an existing multi-source case bundle.

    Args:
        bundle: The existing bundle to append to, or None to create a new one.
        matter_manifest: The matter manifest containing artifacts to add as sources.

    Returns:
        The updated bundle with manifest sources added, or the original bundle if
        no valid artifacts are found in the manifest.

    """
    return append_manifest_sources_stage(bundle, matter_manifest=matter_manifest)


def empty_multi_source_case_bundle() -> dict[str, Any]:
    """Return an empty bundle scaffold for standalone manifest/chat assembly."""
    return {
        "version": MULTI_SOURCE_CASE_BUNDLE_VERSION,
        "summary": {},
        "sources": [],
        "source_links": [],
        "source_link_diagnostics": [],
        "source_type_profiles": [],
        "chronology_anchors": [],
    }


def build_standalone_mixed_source_bundle(
    *,
    matter_manifest: dict[str, Any] | None = None,
    chat_log_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Build a mixed-source bundle from manifest/chat records without email candidates."""
    bundle: dict[str, Any] | None = empty_multi_source_case_bundle()
    if chat_log_entries:
        bundle = append_chat_log_sources(bundle, chat_log_entries=chat_log_entries)
    if matter_manifest is not None:
        bundle = append_manifest_sources(bundle, matter_manifest=matter_manifest)
    if not isinstance(bundle, dict):
        return None
    if not any(isinstance(source, dict) for source in bundle.get("sources", []) or []):
        return None
    return bundle


@dataclass(frozen=True)
class _PromotionRequest:
    bundle: dict[str, Any]
    limit: int | None


@dataclass
class _PromotionRuntime:
    request: _PromotionRequest
    diagnostics_by_source_id: dict[str, list[dict[str, Any]]]
    rows: list[dict[str, Any]]


def _diagnostics_by_source_id(bundle: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for item in bundle.get("source_link_diagnostics", []) or []:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("source_id") or "")
        if source_id:
            result.setdefault(source_id, []).append(item)
    return result


def _promotion_score(source: dict[str, Any]) -> tuple[float, str, bool, bool]:
    weighting = dict(source.get("source_weighting") or {})
    support = dict(source.get("documentary_support") or {})
    reliability = dict(source.get("source_reliability") or {})
    status = str(source.get("promotability_status") or "")
    text_available = bool(weighting.get("text_available")) or bool(str(source.get("searchable_text") or "").strip())
    score = 0.48 + min(float(weighting.get("base_weight") or 0.4), 1.0) * 0.22
    competition_class, low_confidence, adjustment = _promotion_status_adjustment(source, status)
    score += adjustment + _promotion_signal_adjustment(source, weighting, support, text_available)
    score += _promotion_reliability_adjustment(reliability)
    if source.get("weak_format_semantics"):
        score -= 0.1
        low_confidence = True
        competition_class = "weak_format" if competition_class == "standard" else competition_class
    return score, competition_class, low_confidence, text_available


def _promotion_status_adjustment(source: dict[str, Any], status: str) -> tuple[str, bool, float]:
    if status == "lead_only_manual_review":
        return "lead_only", True, -0.28
    if status == "promotable_with_original_check":
        return "manual_check", True, -0.12
    return "standard", bool(source.get("low_confidence_lead")), 0.0


def _promotion_signal_adjustment(
    source: dict[str, Any],
    weighting: dict[str, Any],
    support: dict[str, Any],
    text_available: bool,
) -> float:
    adjustments = (
        (text_available, 0.08),
        (bool(weighting.get("can_corroborate_or_contradict")), 0.04),
        (bool(source.get("chronology_anchor")), 0.03),
        (str(support.get("evidence_strength") or "") == "strong_text", 0.05),
    )
    return sum(value for enabled, value in adjustments if enabled)


def _promotion_reliability_adjustment(reliability: dict[str, Any]) -> float:
    level = str(reliability.get("level") or "")
    if level == "high":
        return 0.04
    if level == "low":
        return -0.05
    return 0.0


def _candidate_related_sources(
    source: dict[str, Any],
    diagnostics_by_source_id: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    source_id = str(source.get("source_id") or "")
    raw = cast(
        list[dict[str, Any]],
        source.get("candidate_related_sources")
        if isinstance(source.get("candidate_related_sources"), list)
        else diagnostics_by_source_id.get(source_id, []) or [],
    )
    result: list[dict[str, Any]] = []
    for item in raw:
        normalized = _normalized_related_source(item)
        if normalized is not None:
            result.append(normalized)
    return result


def _normalized_related_source(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    related_id = _first_text(item.get("source_id"), item.get("candidate_email_source_id"))
    confidence = _source_text(item, "confidence")
    if not related_id or confidence not in {"high", "medium"}:
        return None
    return {
        "source_id": related_id,
        "confidence": confidence,
        "match_basis": [str(member) for member in item.get("match_basis", []) if str(member).strip()],
        "status": _first_text(item.get("status"), "candidate_link"),
    }


def _promotion_snippet(source: dict[str, Any], support: dict[str, Any]) -> str:
    return next(
        (
            str(value).strip()
            for value in (
                source.get("snippet"),
                source.get("searchable_text"),
                support.get("text_preview"),
                source.get("title"),
            )
            if str(value or "").strip()
        ),
        "",
    )[:320]


def _source_text(source: dict[str, Any], key: str) -> str:
    return str(source.get(key) or "")


def _first_text(*values: Any) -> str:
    return next((str(value) for value in values if str(value or "")), "")


def _related_source_ids(related: list[dict[str, Any]]) -> list[str]:
    identifiers = (_source_text(item, "source_id") for item in related)
    return list(dict.fromkeys(identifier for identifier in identifiers if identifier))[:4]


def _promotion_row(
    source: dict[str, Any],
    diagnostics_by_source_id: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    source_id = _source_text(source, "source_id")
    source_type = _source_text(source, "source_type")
    support = dict(source.get("documentary_support") or {})
    locator = dict(source.get("document_locator") or {})
    provenance = dict(source.get("provenance") or {})
    reliability = dict(source.get("source_reliability") or {})
    score, competition_class, low_confidence, text_available = _promotion_score(source)
    related = _candidate_related_sources(source, diagnostics_by_source_id)
    candidate_kind = "body" if source_type in {"chat_log", "email"} else "attachment"
    evidence_handle = _first_text(locator.get("evidence_handle"), provenance.get("evidence_handle"), source_id)
    row: dict[str, Any] = {
        "uid": _source_text(source, "uid"),
        "source_id": source_id,
        "source_type": source_type,
        "candidate_kind": candidate_kind,
        "subject": _first_text(source.get("title"), source_id),
        "sender_email": _first_text(source.get("sender_email"), source.get("author")),
        "sender_name": _first_text(source.get("sender_name"), source.get("author")),
        "date": _source_text(source, "date"),
        "conversation_id": _source_text(source, "conversation_id"),
        "score": round(max(0.0, min(score, 0.95)), 4),
        "snippet": _promotion_snippet(source, support),
        "verification_status": "mixed_source_text" if text_available else "mixed_source_reference",
        "score_kind": "mixed_source_competition",
        "score_calibration": "calibrated" if text_available else "synthetic",
        "result_key": f"mixed:{source_id}",
        "matched_query_lanes": [f"mixed_source:{_first_text(source_type, 'record')}"],
        "matched_query_queries": [_first_text(source.get("title"), source_type, "mixed source")],
        "harvest_source": "mixed_source_bundle",
        "harvest_round": 0,
        "body_render_mode": "quoted_snippet",
        "body_render_source": _first_text(source_type, "mixed_source"),
        "source_reliability": reliability,
        "promotability_status": _source_text(source, "promotability_status"),
        "competition_class": competition_class,
        "low_confidence_lead": low_confidence,
        "candidate_related_source_ids": _related_source_ids(related),
        "candidate_related_sources": related[:8],
        "source_link_ambiguity": dict(source.get("source_link_ambiguity") or {}),
        "provenance": {**provenance, "evidence_handle": evidence_handle, "source_id": source_id},
        "document_locator": locator,
        "follow_up": dict(source.get("follow_up") or {"tool": "source_record", "source_id": source_id}),
    }
    _add_promotion_attachment_fields(row, source, support, text_available=text_available)
    return row


def _add_promotion_attachment_fields(
    row: dict[str, Any],
    source: dict[str, Any],
    support: dict[str, Any],
    *,
    text_available: bool,
) -> None:
    weak_semantics = dict(source.get("weak_format_semantics") or {})
    if weak_semantics:
        row["weak_format_semantics"] = weak_semantics
    if row["candidate_kind"] != "attachment":
        return
    attachment: dict[str, Any] = dict(source.get("attachment") or {}) if isinstance(source.get("attachment"), dict) else {}
    filename = str(attachment.get("filename") or source.get("title") or row["source_id"])
    row["attachment_filename"] = filename
    row["attachment"] = {
        "filename": filename,
        "source_type_hint": row["source_type"] or "attachment",
        "text_available": text_available,
        "evidence_strength": str(support.get("evidence_strength") or "weak_reference"),
        "extraction_state": str(support.get("extraction_state") or ""),
    }


def _is_promotable_source(source: Any) -> bool:
    if not isinstance(source, dict):
        return False
    if not _source_text(source, "source_id"):
        return False
    if _source_text(source, "source_type") == "email" and _source_text(source, "uid"):
        return False
    return _source_text(source, "promotability_status") != "reference_only_not_promotable"


def _promotion_sort_key(item: dict[str, Any]) -> tuple[float, int, str]:
    verification_rank = 0 if _source_text(item, "verification_status") == "mixed_source_text" else 1
    return (-float(item.get("score") or 0.0), verification_rank, _source_text(item, "source_id"))


def promotable_mixed_source_evidence_rows(
    bundle: dict[str, Any] | None,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return mixed-source rows shaped for answer-context candidate competition."""
    if not isinstance(bundle, dict):
        return []
    runtime = _PromotionRuntime(
        request=_PromotionRequest(bundle=bundle, limit=limit),
        diagnostics_by_source_id=_diagnostics_by_source_id(bundle),
        rows=[],
    )
    for source in bundle.get("sources", []) or []:
        if not _is_promotable_source(source):
            continue
        assert isinstance(source, dict)
        runtime.rows.append(_promotion_row(source, runtime.diagnostics_by_source_id))
    runtime.rows.sort(key=_promotion_sort_key)
    if runtime.request.limit is not None and runtime.request.limit >= 0:
        return runtime.rows[: runtime.request.limit]
    return runtime.rows


_COMPACT_SCALAR_FIELDS = (
    "uid",
    "actor_id",
    "title",
    "date",
    "snippet",
    "sender_name",
    "sender_email",
    "author",
    "date_context",
    "operator_summary",
    "promotability_status",
)
_COMPACT_SEQUENCE_FIELDS = ("to", "cc", "bcc", "recipients", "participants")


def _copy_compact_scalar_fields(source: dict[str, Any], target: dict[str, Any]) -> None:
    for key in _COMPACT_SCALAR_FIELDS:
        value = source.get(key)
        if value not in (None, "", []):
            target[key] = value
    for key in _COMPACT_SEQUENCE_FIELDS:
        values = [str(item) for item in source.get(key, []) if item]
        if values:
            target[key] = values


def _compact_link_ambiguity(source: dict[str, Any]) -> dict[str, Any] | None:
    raw = source.get("source_link_ambiguity")
    if not raw:
        return None
    ambiguity = dict(raw)
    return {
        "status": _source_text(ambiguity, "status"),
        "candidate_count": int(ambiguity.get("candidate_count") or 0),
        "candidates": [
            {
                "source_id": _source_text(item, "source_id"),
                "confidence": _source_text(item, "confidence"),
                "status": _source_text(item, "status"),
            }
            for item in ambiguity.get("candidates", []) or []
            if isinstance(item, dict)
        ][:6],
    }


def _copy_compact_relationships(source: dict[str, Any], target: dict[str, Any]) -> None:
    ambiguity = _compact_link_ambiguity(source)
    if ambiguity is not None:
        target["source_link_ambiguity"] = ambiguity
    if source.get("chronology_anchor"):
        target["chronology_anchor"] = dict(source.get("chronology_anchor") or {})
    if source.get("candidate_related_source_ids"):
        target["candidate_related_source_ids"] = [str(item) for item in source.get("candidate_related_source_ids", []) if item][
            :4
        ]
    if source.get("candidate_related_sources"):
        target["candidate_related_sources"] = [
            {
                "source_id": _source_text(item, "source_id"),
                "confidence": _source_text(item, "confidence"),
                "status": _source_text(item, "status"),
            }
            for item in source.get("candidate_related_sources", [])
            if isinstance(item, dict)
        ][:4]


def _copy_compact_evidence(source: dict[str, Any], target: dict[str, Any]) -> None:
    if source.get("provenance"):
        provenance = dict(source.get("provenance") or {})
        target["provenance"] = {
            "evidence_handle": _source_text(provenance, "evidence_handle"),
            "chunk_id": _source_text(provenance, "chunk_id"),
            "snippet_start": provenance.get("snippet_start"),
            "snippet_end": provenance.get("snippet_end"),
        }
    if source.get("document_locator"):
        locator = dict(source.get("document_locator") or {})
        target["document_locator"] = {
            "evidence_handle": _source_text(locator, "evidence_handle"),
            "chunk_id": _source_text(locator, "chunk_id"),
        }
    _copy_compact_documentary_support(source, target)


def _copy_compact_documentary_support(source: dict[str, Any], target: dict[str, Any]) -> None:
    if not source.get("documentary_support"):
        return
    support = dict(source.get("documentary_support") or {})
    target["documentary_support"] = {
        "extraction_state": _source_text(support, "extraction_state"),
        "evidence_strength": _source_text(support, "evidence_strength"),
        "ocr_used": bool(support.get("ocr_used")),
        "failure_reason": _source_text(support, "failure_reason"),
        "text_preview": _source_text(support, "text_preview"),
        "format_profile": dict(support.get("format_profile") or {}),
        "extraction_quality": dict(support.get("extraction_quality") or {}),
    }


def _compact_source(source: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "source_id": _source_text(source, "source_id"),
        "source_type": _source_text(source, "source_type"),
        "document_kind": _source_text(source, "document_kind"),
        "source_reliability": dict(source.get("source_reliability") or {}),
    }
    _copy_compact_scalar_fields(source, result)
    if source.get("weak_format_semantics"):
        result["weak_format_semantics"] = dict(source.get("weak_format_semantics") or {})
    _copy_compact_relationships(source, result)
    _copy_compact_evidence(source, result)
    return result


def _compact_source_link(link: dict[str, Any]) -> dict[str, Any]:
    match_basis = link.get("match_basis")
    return {
        "from_source_id": _source_text(link, "from_source_id"),
        "to_source_id": _source_text(link, "to_source_id"),
        "link_type": _source_text(link, "link_type"),
        "relationship": _source_text(link, "relationship"),
        "confidence": _source_text(link, "confidence"),
        "match_basis": [str(item) for item in match_basis if item] if isinstance(match_basis, list) else [],
    }


def _compact_chronology_anchor(anchor: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _source_text(anchor, key)
        for key in (
            "source_id",
            "source_type",
            "date",
            "date_origin",
            "anchor_confidence",
            "date_choice_reason",
        )
    }


def _compact_link_diagnostic(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": _source_text(item, "source_id"),
        "candidate_email_source_id": _source_text(item, "candidate_email_source_id"),
        "confidence": _source_text(item, "confidence"),
        "status": _source_text(item, "status"),
        "candidate_rank": int(item.get("candidate_rank") or 0),
    }


def _compact_sources(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [_compact_source(source) for source in bundle.get("sources", []) if isinstance(source, dict)]


def _compact_profiles(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(profile)
        for profile in bundle.get("source_type_profiles", [])
        if isinstance(profile, dict) and bool(profile.get("available"))
    ]


def _compact_diagnostics(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _compact_link_diagnostic(item)
        for item in bundle.get("source_link_diagnostics", [])
        if isinstance(item, dict) and _source_text(item, "status") == "ambiguous_candidate_link"
    ][:10]


def _compact_links(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [_compact_source_link(link) for link in bundle.get("source_links", []) if isinstance(link, dict)]


def _compact_anchors(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [_compact_chronology_anchor(anchor) for anchor in bundle.get("chronology_anchors", []) if isinstance(anchor, dict)][
        :10
    ]


def compact_multi_source_case_bundle(bundle: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the compact, stable JSON projection of a multi-source bundle."""
    if not isinstance(bundle, dict):
        return bundle
    return {
        "version": _source_text(bundle, "version"),
        "summary": dict(bundle.get("summary") or {}),
        "sources": _compact_sources(bundle),
        "source_links": _compact_links(bundle),
        "source_type_profiles": _compact_profiles(bundle),
        "chronology_anchors": _compact_anchors(bundle),
        "source_link_diagnostics": _compact_diagnostics(bundle),
    }


@dataclass(frozen=True)
class _BundleBuildRequest:
    case_bundle: dict[str, Any] | None
    candidates: list[dict[str, Any]]
    attachment_candidates: list[dict[str, Any]]
    full_map: dict[str, Any]
    chat_log_entries: list[dict[str, Any]] | None


@dataclass
class _BundleBuildRuntime:
    request: _BundleBuildRequest
    sources: list[dict[str, Any]]
    source_links: list[dict[str, Any]]
    email_source_ids_by_uid: dict[str, str]


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in (value or []) if isinstance(item, dict)]


def _first_stripped_text(*values: Any, limit: int | None = None) -> str:
    text = next((str(value).strip() for value in values if str(value or "").strip()), "")
    return text[:limit] if limit is not None else text


def _apply_derived_source_semantics(source: dict[str, Any]) -> None:
    derived = (
        ("chronology_anchor", _chronology_anchor_for_source(source)),
        ("spreadsheet_semantics", _spreadsheet_semantics(source)),
        ("calendar_semantics", _calendar_semantics(source)),
    )
    for key, value in derived:
        if value is not None:
            source[key] = value


def _email_provenance(candidate: dict[str, Any], full_email: dict[str, Any]) -> dict[str, Any]:
    return {
        **dict(candidate.get("provenance") or {}),
        "message_id": _source_text(full_email, "message_id"),
        "in_reply_to": _source_text(full_email, "in_reply_to"),
        "references": " ".join(str(item) for item in (full_email.get("references") or []) if item),
    }


def _build_email_source(candidate: dict[str, Any], full_email: dict[str, Any]) -> dict[str, Any] | None:
    uid = _source_text(candidate, "uid")
    if not uid:
        return None
    reliability = _source_reliability_for_email(candidate)
    source = {
        "source_id": f"email:{uid}",
        "source_type": "email",
        "document_kind": "email_body",
        "uid": uid,
        "actor_id": _source_text(candidate, "sender_actor_id"),
        "title": _source_text(candidate, "subject"),
        "date": _source_text(candidate, "date"),
        "snippet": _source_text(candidate, "snippet"),
        "searchable_text": _first_stripped_text(
            full_email.get("forensic_body_text"),
            full_email.get("body_text"),
            full_email.get("normalized_body_text"),
            candidate.get("snippet"),
            limit=4000,
        ),
        "sender_name": _first_text(full_email.get("sender_name"), candidate.get("sender_name")),
        "sender_email": _first_text(full_email.get("sender_email"), candidate.get("sender_email")),
        "to": _string_list(full_email.get("to")),
        "cc": _string_list(full_email.get("cc")),
        "bcc": _string_list(full_email.get("bcc")),
        "language_hint_text": _first_stripped_text(
            full_email.get("forensic_body_text"),
            full_email.get("body_text"),
            full_email.get("raw_body_text"),
        ),
        "provenance": _email_provenance(candidate, full_email),
        "follow_up": dict(candidate.get("follow_up") or {}),
        "conversation_id": _first_text(full_email.get("conversation_id"), candidate.get("conversation_id")),
        "source_reliability": reliability,
        "source_weighting": _weighting_metadata(
            source_type="email",
            reliability_level=str(reliability["level"]),
            text_available=bool(_source_text(candidate, "snippet").strip()),
        ),
        "event_records": _dict_rows(candidate.get("event_records")),
        "entity_occurrences": _dict_rows(candidate.get("entity_occurrences")),
    }
    _apply_derived_source_semantics(source)
    return source


def _append_meeting_notes(runtime: _BundleBuildRuntime, uid: str, email_source_id: str) -> None:
    for note in _meeting_note_sources(uid, runtime.request.full_map.get(uid)):
        note.pop("_extracted_from", None)
        runtime.sources.append(note)
        runtime.source_links.append(
            {
                "from_source_id": note["source_id"],
                "to_source_id": email_source_id,
                "link_type": "extracted_from_email",
                "relationship": "contextual_metadata",
            }
        )


def _append_email_sources(runtime: _BundleBuildRuntime) -> None:
    for candidate in runtime.request.candidates:
        uid = _source_text(candidate, "uid")
        full_email = runtime.request.full_map.get(uid)
        source = _build_email_source(candidate, full_email if isinstance(full_email, dict) else {})
        if source is None:
            continue
        source_id = _source_text(source, "source_id")
        runtime.email_source_ids_by_uid[uid] = source_id
        runtime.sources.append(source)
        _append_meeting_notes(runtime, uid, source_id)


def _copy_declared_attachment_semantics(attachment: dict[str, Any], source: dict[str, Any]) -> None:
    for key in ("spreadsheet_semantics", "calendar_semantics", "weak_format_semantics"):
        value = attachment.get(key)
        if isinstance(value, dict) and value:
            source[key] = dict(value)


def _build_attachment_source(candidate: dict[str, Any]) -> dict[str, Any]:
    attachment = cast(dict[str, Any], candidate.get("attachment")) if isinstance(candidate.get("attachment"), dict) else {}
    uid = _source_text(candidate, "uid")
    source_type = _attachment_source_type(candidate, attachment)
    filename = _first_text(attachment.get("filename"), "attachment")
    reliability = _source_reliability_for_attachment(candidate, source_type=source_type)
    source = {
        "source_id": f"{source_type}:{uid}:{filename}",
        "source_type": source_type,
        "document_kind": _attachment_document_kind(source_type),
        "uid": uid,
        "actor_id": _source_text(candidate, "sender_actor_id"),
        "title": filename,
        "date": _source_text(candidate, "date"),
        "snippet": _source_text(candidate, "snippet"),
        "searchable_text": _first_text(attachment.get("text"), attachment.get("extracted_text"), attachment.get("text_preview"))[
            :4000
        ],
        "language_hint_text": _first_text(attachment.get("text"), attachment.get("text_preview")),
        "provenance": dict(candidate.get("provenance") or {}),
        "attachment": dict(attachment),
        "document_locator": _document_locator(candidate),
        "documentary_support": _documentary_support_payload(candidate, source_type=source_type) or {},
        "follow_up": dict(candidate.get("follow_up") or {}),
        "source_reliability": reliability,
        "source_weighting": _weighting_metadata(
            source_type=source_type,
            reliability_level=str(reliability["level"]),
            text_available=bool(attachment.get("text_available")),
        ),
        "event_records": _dict_rows(candidate.get("event_records")),
        "entity_occurrences": _dict_rows(candidate.get("entity_occurrences")),
    }
    _copy_declared_attachment_semantics(attachment, source)
    _apply_derived_source_semantics(source)
    return source


def _append_attachment_link(runtime: _BundleBuildRuntime, source: dict[str, Any]) -> None:
    parent_source_id = runtime.email_source_ids_by_uid.get(_source_text(source, "uid"))
    if not parent_source_id:
        return
    weighting = source["source_weighting"]
    can_corroborate = isinstance(weighting, dict) and bool(weighting.get("can_corroborate_or_contradict"))
    runtime.source_links.append(
        {
            "from_source_id": source["source_id"],
            "to_source_id": parent_source_id,
            "link_type": "attached_to_email",
            "relationship": ("can_corroborate_or_contradict_message" if can_corroborate else "reference_only_attachment"),
        }
    )


def _append_attachment_sources(runtime: _BundleBuildRuntime) -> None:
    for candidate in runtime.request.attachment_candidates:
        source = _build_attachment_source(candidate)
        runtime.sources.append(source)
        _append_attachment_link(runtime, source)


def _append_chat_sources(runtime: _BundleBuildRuntime) -> list[dict[str, Any]]:
    email_sources = [source for source in runtime.sources if _source_text(source, "source_type") == "email"]
    chat_sources, chat_links, diagnostics, _counts = _chat_log_sources(
        runtime.request.chat_log_entries,
        email_source_ids_by_uid=runtime.email_source_ids_by_uid,
        email_sources=email_sources,
    )
    runtime.sources.extend(chat_sources)
    runtime.source_links.extend(chat_links)
    return diagnostics


def build_multi_source_case_bundle(
    *,
    case_bundle: dict[str, Any] | None,
    candidates: list[dict[str, Any]],
    attachment_candidates: list[dict[str, Any]],
    full_map: dict[str, Any],
    chat_log_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Build the ordered email, note, attachment, and chat source bundle."""
    scope = (case_bundle or {}).get("scope") if isinstance(case_bundle, dict) else None
    if not isinstance(scope, dict):
        return None
    runtime = _BundleBuildRuntime(
        request=_BundleBuildRequest(case_bundle, candidates, attachment_candidates, full_map, chat_log_entries),
        sources=[],
        source_links=[],
        email_source_ids_by_uid={},
    )
    _append_email_sources(runtime)
    _append_attachment_sources(runtime)
    diagnostics = _append_chat_sources(runtime)
    return _rebuild_bundle_summary(
        {
            "version": MULTI_SOURCE_CASE_BUNDLE_VERSION,
            "summary": {},
            "sources": runtime.sources,
            "source_links": runtime.source_links,
            "source_link_diagnostics": diagnostics,
            "source_type_profiles": [],
            "chronology_anchors": [],
        }
    )
