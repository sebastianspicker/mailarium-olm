"""Multi-source case-evidence fusion for behavioural-analysis cases."""

from __future__ import annotations

from typing import Any, cast

from .matter_ingestion import source_from_manifest_artifact
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
    resolve_manifest_email_links,
)
from .multi_source_case_bundle_summary import _rebuild_bundle_summary


def append_chat_log_sources(
    bundle: dict[str, Any] | None,
    *,
    chat_log_entries: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    if not isinstance(bundle, dict):
        return bundle
    bundle_copy = {
        **bundle,
        "summary": dict(bundle.get("summary") or {}),
        "sources": [source for source in bundle.get("sources", []) if isinstance(source, dict)],
        "source_links": [link for link in bundle.get("source_links", []) if isinstance(link, dict)],
        "source_type_profiles": [profile for profile in bundle.get("source_type_profiles", []) if isinstance(profile, dict)],
        "source_link_diagnostics": [item for item in bundle.get("source_link_diagnostics", []) if isinstance(item, dict)],
    }
    existing_source_ids = {str(source.get("source_id") or "") for source in bundle_copy["sources"]}
    email_source_ids_by_uid = {
        str(source.get("uid") or ""): str(source.get("source_id") or "")
        for source in bundle_copy["sources"]
        if str(source.get("source_type") or "") == "email" and str(source.get("uid") or "")
    }
    email_sources = [
        source
        for source in bundle_copy["sources"]
        if str(source.get("source_type") or "") == "email" and str(source.get("source_id") or "")
    ]
    new_sources, new_links, new_diagnostics, _new_counts = _chat_log_sources(
        chat_log_entries,
        email_source_ids_by_uid=email_source_ids_by_uid,
        email_sources=email_sources,
    )
    for source in new_sources:
        if str(source.get("source_id") or "") in existing_source_ids:
            continue
        bundle_copy["sources"].append(source)
        existing_source_ids.add(str(source.get("source_id") or ""))
    bundle_copy["source_links"].extend(new_links)
    bundle_copy["source_link_diagnostics"].extend(new_diagnostics)
    return _rebuild_bundle_summary(bundle_copy)


def append_manifest_sources(
    bundle: dict[str, Any] | None,
    *,
    matter_manifest: dict[str, Any] | None,
) -> dict[str, Any] | None:
    manifest = matter_manifest if isinstance(matter_manifest, dict) else {}
    artifacts = [item for item in manifest.get("artifacts", []) if isinstance(item, dict)]
    if not artifacts:
        return bundle
    bundle_copy = {
        **(bundle or {}),
        "summary": dict((bundle or {}).get("summary") or {}),
        "sources": [source for source in (bundle or {}).get("sources", []) if isinstance(source, dict)],
        "source_links": [link for link in (bundle or {}).get("source_links", []) if isinstance(link, dict)],
        "source_type_profiles": [
            profile for profile in (bundle or {}).get("source_type_profiles", []) if isinstance(profile, dict)
        ],
        "chronology_anchors": [anchor for anchor in (bundle or {}).get("chronology_anchors", []) if isinstance(anchor, dict)],
        "source_link_diagnostics": [item for item in (bundle or {}).get("source_link_diagnostics", []) if isinstance(item, dict)],
    }
    existing_source_ids = {str(source.get("source_id") or "") for source in bundle_copy["sources"]}
    email_sources = [
        source
        for source in bundle_copy["sources"]
        if str(source.get("source_type") or "") == "email" and str(source.get("source_id") or "")
    ]
    new_sources: list[dict[str, Any]] = []
    for index, artifact in enumerate(artifacts, start=1):
        source = source_from_manifest_artifact(artifact, index=index)
        chronology_anchor = _chronology_anchor_for_source(source)
        if chronology_anchor is not None:
            source["chronology_anchor"] = chronology_anchor
        source_id = str(source.get("source_id") or "")
        if source_id in existing_source_ids:
            continue
        bundle_copy["sources"].append(source)
        new_sources.append(source)
        existing_source_ids.add(source_id)
        uid = str(source.get("uid") or "")
        if uid and str(source.get("source_type") or "") == "email":
            email_sources.append(source)
    for source in new_sources:
        links, diagnostics = resolve_manifest_email_links(source, email_sources=email_sources)
        candidate_related_sources = [
            {
                "source_id": str(item.get("candidate_email_source_id") or ""),
                "confidence": str(item.get("confidence") or ""),
                "match_basis": [str(member) for member in item.get("match_basis", []) if str(member).strip()],
                "status": str(item.get("status") or "candidate_link"),
                "score": int(item.get("score") or 0),
                "candidate_rank": int(item.get("candidate_rank") or 0),
            }
            for item in diagnostics
            if isinstance(item, dict)
            and str(item.get("candidate_email_source_id") or "")
            and str(item.get("confidence") or "") in {"high", "medium"}
        ]
        if candidate_related_sources:
            source["candidate_related_sources"] = candidate_related_sources[:8]
            source["candidate_related_source_ids"] = list(
                dict.fromkeys(
                    str(item.get("source_id") or "") for item in candidate_related_sources if str(item.get("source_id") or "")
                )
            )[:8]
        ambiguous_candidates = [
            {
                "source_id": str(item.get("candidate_email_source_id") or ""),
                "confidence": str(item.get("confidence") or ""),
                "status": str(item.get("status") or ""),
                "match_basis": [str(member) for member in item.get("match_basis", []) if str(member).strip()],
                "score": int(item.get("score") or 0),
                "candidate_rank": int(item.get("candidate_rank") or 0),
            }
            for item in diagnostics
            if isinstance(item, dict)
            and str(item.get("status") or "") == "ambiguous_candidate_link"
            and str(item.get("candidate_email_source_id") or "")
        ]
        if ambiguous_candidates:
            source["source_link_ambiguity"] = {
                "status": "ambiguous_candidate_set",
                "candidate_count": len(ambiguous_candidates),
                "candidates": ambiguous_candidates[:8],
            }
        bundle_copy["source_links"].extend(links)
        bundle_copy["source_link_diagnostics"].extend(diagnostics)
    return _rebuild_bundle_summary(bundle_copy)


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


def promotable_mixed_source_evidence_rows(
    bundle: dict[str, Any] | None,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return mixed-source rows shaped for answer-context candidate competition."""
    if not isinstance(bundle, dict):
        return []

    diagnostics_by_source_id: dict[str, list[dict[str, Any]]] = {}
    for item in bundle.get("source_link_diagnostics", []) or []:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("source_id") or "")
        if not source_id:
            continue
        diagnostics_by_source_id.setdefault(source_id, []).append(item)

    rows: list[dict[str, Any]] = []
    for source in bundle.get("sources", []) or []:
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("source_id") or "")
        source_type = str(source.get("source_type") or "")
        uid = str(source.get("uid") or "")
        if not source_id:
            continue
        if source_type == "email" and uid:
            continue

        documentary_support = dict(source.get("documentary_support") or {})
        document_locator = dict(source.get("document_locator") or {})
        provenance = dict(source.get("provenance") or {})
        source_reliability = dict(source.get("source_reliability") or {})
        source_weighting = dict(source.get("source_weighting") or {})
        promotability_status = str(source.get("promotability_status") or "")
        text_available = bool(source_weighting.get("text_available")) or bool(str(source.get("searchable_text") or "").strip())
        candidate_kind = "body" if source_type in {"chat_log", "email"} else "attachment"
        attachment_filename = str(
            ((source.get("attachment") or {}) if isinstance(source.get("attachment"), dict) else {}).get("filename")
            or source.get("title")
            or source_id
        )
        snippet = next(
            (
                str(value).strip()
                for value in (
                    source.get("snippet"),
                    source.get("searchable_text"),
                    documentary_support.get("text_preview"),
                    source.get("title"),
                )
                if str(value or "").strip()
            ),
            "",
        )[:320]
        base_weight = float(source_weighting.get("base_weight") or 0.4)
        score = 0.48 + min(base_weight, 1.0) * 0.22
        competition_class = "standard"
        low_confidence_lead = bool(source.get("low_confidence_lead"))
        if promotability_status == "reference_only_not_promotable":
            continue
        if promotability_status == "lead_only_manual_review":
            competition_class = "lead_only"
            low_confidence_lead = True
            score -= 0.28
        elif promotability_status == "promotable_with_original_check":
            competition_class = "manual_check"
            low_confidence_lead = True
            score -= 0.12
        if text_available:
            score += 0.08
        if bool(source_weighting.get("can_corroborate_or_contradict")):
            score += 0.04
        if source.get("chronology_anchor"):
            score += 0.03
        if str(documentary_support.get("evidence_strength") or "") == "strong_text":
            score += 0.05
        if str(source_reliability.get("level") or "") == "high":
            score += 0.04
        elif str(source_reliability.get("level") or "") == "low":
            score -= 0.05
        weak_format_semantics = dict(source.get("weak_format_semantics") or {})
        if weak_format_semantics:
            score -= 0.1
            low_confidence_lead = True
            if competition_class == "standard":
                competition_class = "weak_format"
        raw_candidate_related_sources: list[dict[str, Any]] = cast(
            list[dict[str, Any]],
            source.get("candidate_related_sources")
            if isinstance(source.get("candidate_related_sources"), list)
            else diagnostics_by_source_id.get(source_id, []) or [],
        )
        candidate_related_sources: list[dict[str, Any]] = []
        for item in raw_candidate_related_sources:
            if not isinstance(item, dict):
                continue
            related_source_id = str(item.get("source_id") or item.get("candidate_email_source_id") or "")
            confidence = str(item.get("confidence") or "")
            if not related_source_id or confidence not in {"high", "medium"}:
                continue
            candidate_related_sources.append(
                {
                    "source_id": related_source_id,
                    "confidence": confidence,
                    "match_basis": [str(member) for member in item.get("match_basis", []) if str(member).strip()],
                    "status": str(item.get("status") or "candidate_link"),
                }
            )
        candidate_related_source_ids = list(
            dict.fromkeys(
                str(item.get("source_id") or item.get("candidate_email_source_id") or "")
                for item in candidate_related_sources
                if str(item.get("source_id") or item.get("candidate_email_source_id") or "")
            )
        )[:4]
        evidence_handle = str(document_locator.get("evidence_handle") or provenance.get("evidence_handle") or source_id)
        row: dict[str, Any] = {
            "uid": uid,
            "source_id": source_id,
            "source_type": source_type,
            "candidate_kind": candidate_kind,
            "subject": str(source.get("title") or source_id),
            "sender_email": str(source.get("sender_email") or source.get("author") or ""),
            "sender_name": str(source.get("sender_name") or source.get("author") or ""),
            "date": str(source.get("date") or ""),
            "conversation_id": str(source.get("conversation_id") or ""),
            "score": round(max(0.0, min(score, 0.95)), 4),
            "snippet": snippet,
            "verification_status": "mixed_source_text" if text_available else "mixed_source_reference",
            "score_kind": "mixed_source_competition",
            "score_calibration": "calibrated" if text_available else "synthetic",
            "result_key": f"mixed:{source_id}",
            "matched_query_lanes": [f"mixed_source:{source_type or 'record'}"],
            "matched_query_queries": [str(source.get("title") or source_type or "mixed source")],
            "harvest_source": "mixed_source_bundle",
            "harvest_round": 0,
            "body_render_mode": "quoted_snippet",
            "body_render_source": source_type or "mixed_source",
            "source_reliability": source_reliability,
            "promotability_status": promotability_status,
            "competition_class": competition_class,
            "low_confidence_lead": low_confidence_lead,
            "candidate_related_source_ids": candidate_related_source_ids,
            "candidate_related_sources": candidate_related_sources[:8],
            "source_link_ambiguity": dict(source.get("source_link_ambiguity") or {}),
            "provenance": {
                **provenance,
                "evidence_handle": evidence_handle,
                "source_id": source_id,
            },
            "document_locator": document_locator,
            "follow_up": dict(source.get("follow_up") or ({"tool": "source_record", "source_id": source_id})),
        }
        if weak_format_semantics:
            row["weak_format_semantics"] = weak_format_semantics
        if candidate_kind == "attachment":
            row["attachment_filename"] = attachment_filename
            row["attachment"] = {
                "filename": attachment_filename,
                "source_type_hint": source_type or "attachment",
                "text_available": text_available,
                "evidence_strength": str(documentary_support.get("evidence_strength") or "weak_reference"),
                "extraction_state": str(documentary_support.get("extraction_state") or ""),
            }
        rows.append(row)

    rows.sort(
        key=lambda item: (
            -float(item.get("score") or 0.0),
            0 if str(item.get("verification_status") or "") == "mixed_source_text" else 1,
            str(item.get("source_id") or ""),
        )
    )
    if limit is not None and limit >= 0:
        return rows[:limit]
    return rows


def compact_multi_source_case_bundle(bundle: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(bundle, dict):
        return bundle
    compact_sources: list[dict[str, Any]] = []
    for source in bundle.get("sources", []):
        if not isinstance(source, dict):
            continue
        compact_source: dict[str, Any] = {
            "source_id": str(source.get("source_id") or ""),
            "source_type": str(source.get("source_type") or ""),
            "document_kind": str(source.get("document_kind") or ""),
            "source_reliability": dict(source.get("source_reliability") or {}),
        }
        for key in (
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
        ):
            value = source.get(key)
            if value not in (None, "", []):
                compact_source[key] = value
        if source.get("weak_format_semantics"):
            compact_source["weak_format_semantics"] = dict(source.get("weak_format_semantics") or {})
        if source.get("source_link_ambiguity"):
            compact_source["source_link_ambiguity"] = {
                "status": str((source.get("source_link_ambiguity") or {}).get("status") or ""),
                "candidate_count": int((source.get("source_link_ambiguity") or {}).get("candidate_count") or 0),
                "candidates": [
                    {
                        "source_id": str(item.get("source_id") or ""),
                        "confidence": str(item.get("confidence") or ""),
                        "status": str(item.get("status") or ""),
                    }
                    for item in ((source.get("source_link_ambiguity") or {}).get("candidates") or [])
                    if isinstance(item, dict)
                ][:6],
            }
        for key in ("to", "cc", "bcc", "recipients", "participants"):
            values = [str(item) for item in source.get(key, []) if item]
            if values:
                compact_source[key] = values
        if source.get("chronology_anchor"):
            compact_source["chronology_anchor"] = dict(source.get("chronology_anchor") or {})
        if source.get("candidate_related_source_ids"):
            compact_source["candidate_related_source_ids"] = [
                str(item) for item in source.get("candidate_related_source_ids", []) if item
            ][:4]
        if source.get("candidate_related_sources"):
            compact_source["candidate_related_sources"] = [
                {
                    "source_id": str(item.get("source_id") or ""),
                    "confidence": str(item.get("confidence") or ""),
                    "status": str(item.get("status") or ""),
                }
                for item in source.get("candidate_related_sources", [])
                if isinstance(item, dict)
            ][:4]
        if source.get("provenance"):
            provenance = dict(source.get("provenance") or {})
            compact_source["provenance"] = {
                "evidence_handle": str(provenance.get("evidence_handle") or ""),
                "chunk_id": str(provenance.get("chunk_id") or ""),
                "snippet_start": provenance.get("snippet_start"),
                "snippet_end": provenance.get("snippet_end"),
            }
        if source.get("documentary_support"):
            documentary_support = dict(source.get("documentary_support") or {})
            compact_source["documentary_support"] = {
                "extraction_state": str(documentary_support.get("extraction_state") or ""),
                "evidence_strength": str(documentary_support.get("evidence_strength") or ""),
                "ocr_used": bool(documentary_support.get("ocr_used")),
                "failure_reason": str(documentary_support.get("failure_reason") or ""),
                "text_preview": str(documentary_support.get("text_preview") or ""),
                "format_profile": dict(documentary_support.get("format_profile") or {}),
                "extraction_quality": dict(documentary_support.get("extraction_quality") or {}),
            }
        if source.get("document_locator"):
            locator = dict(source.get("document_locator") or {})
            compact_source["document_locator"] = {
                "evidence_handle": str(locator.get("evidence_handle") or ""),
                "chunk_id": str(locator.get("chunk_id") or ""),
            }
        compact_sources.append(compact_source)
    compact_profiles = [
        dict(profile)
        for profile in bundle.get("source_type_profiles", [])
        if isinstance(profile, dict) and bool(profile.get("available"))
    ]
    return {
        "version": str(bundle.get("version") or ""),
        "summary": dict(bundle.get("summary") or {}),
        "sources": compact_sources,
        "source_links": [
            {
                "from_source_id": str(link.get("from_source_id") or ""),
                "to_source_id": str(link.get("to_source_id") or ""),
                "link_type": str(link.get("link_type") or ""),
                "relationship": str(link.get("relationship") or ""),
                "confidence": str(link.get("confidence") or ""),
                "match_basis": [str(item) for item in link.get("match_basis", []) if item]
                if isinstance(link.get("match_basis"), list)
                else [],
            }
            for link in bundle.get("source_links", [])
            if isinstance(link, dict)
        ],
        "source_type_profiles": compact_profiles,
        "chronology_anchors": [
            {
                "source_id": str(anchor.get("source_id") or ""),
                "source_type": str(anchor.get("source_type") or ""),
                "date": str(anchor.get("date") or ""),
                "date_origin": str(anchor.get("date_origin") or ""),
                "anchor_confidence": str(anchor.get("anchor_confidence") or ""),
                "date_choice_reason": str(anchor.get("date_choice_reason") or ""),
            }
            for anchor in bundle.get("chronology_anchors", [])
            if isinstance(anchor, dict)
        ][:10],
        "source_link_diagnostics": [
            {
                "source_id": str(item.get("source_id") or ""),
                "candidate_email_source_id": str(item.get("candidate_email_source_id") or ""),
                "confidence": str(item.get("confidence") or ""),
                "status": str(item.get("status") or ""),
                "candidate_rank": int(item.get("candidate_rank") or 0),
            }
            for item in bundle.get("source_link_diagnostics", [])
            if isinstance(item, dict) and str(item.get("status") or "") == "ambiguous_candidate_link"
        ][:10],
    }


def build_multi_source_case_bundle(
    *,
    case_bundle: dict[str, Any] | None,
    candidates: list[dict[str, Any]],
    attachment_candidates: list[dict[str, Any]],
    full_map: dict[str, Any],
    chat_log_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    scope = (case_bundle or {}).get("scope") if isinstance(case_bundle, dict) else None
    if not isinstance(scope, dict):
        return None
    sources: list[dict[str, Any]] = []
    source_links: list[dict[str, Any]] = []
    email_source_ids_by_uid: dict[str, str] = {}
    for candidate in candidates:
        uid = str(candidate.get("uid") or "")
        if not uid:
            continue
        source_id = f"email:{uid}"
        email_source_ids_by_uid[uid] = source_id
        reliability = _source_reliability_for_email(candidate)
        full_email = full_map.get(uid) if isinstance(full_map, dict) else None
        source = {
            "source_id": source_id,
            "source_type": "email",
            "document_kind": "email_body",
            "uid": uid,
            "actor_id": str(candidate.get("sender_actor_id") or ""),
            "title": str(candidate.get("subject") or ""),
            "date": str(candidate.get("date") or ""),
            "snippet": str(candidate.get("snippet") or ""),
            "searchable_text": next(
                (
                    text[:4000]
                    for text in (
                        str((full_email or {}).get("forensic_body_text") or "").strip(),
                        str((full_email or {}).get("body_text") or "").strip(),
                        str((full_email or {}).get("normalized_body_text") or "").strip(),
                        str(candidate.get("snippet") or "").strip(),
                    )
                    if text
                ),
                "",
            ),
            "sender_name": str((full_email or {}).get("sender_name") or candidate.get("sender_name") or ""),
            "sender_email": str((full_email or {}).get("sender_email") or candidate.get("sender_email") or ""),
            "to": _string_list((full_email or {}).get("to")),
            "cc": _string_list((full_email or {}).get("cc")),
            "bcc": _string_list((full_email or {}).get("bcc")),
            "language_hint_text": next(
                (
                    text
                    for text in (
                        str((full_email or {}).get("forensic_body_text") or "").strip(),
                        str((full_email or {}).get("body_text") or "").strip(),
                        str((full_email or {}).get("raw_body_text") or "").strip(),
                    )
                    if text
                ),
                "",
            ),
            "provenance": {
                **dict(candidate.get("provenance") or {}),
                "message_id": str((full_email or {}).get("message_id") or ""),
                "in_reply_to": str((full_email or {}).get("in_reply_to") or ""),
                "references": " ".join(str(item) for item in ((full_email or {}).get("references") or []) if item),
            },
            "follow_up": dict(candidate.get("follow_up") or {}),
            "conversation_id": str((full_email or {}).get("conversation_id") or candidate.get("conversation_id") or ""),
            "source_reliability": reliability,
            "source_weighting": _weighting_metadata(
                source_type="email",
                reliability_level=str(reliability["level"]),
                text_available=bool(str(candidate.get("snippet") or "").strip()),
            ),
            "event_records": [dict(item) for item in (candidate.get("event_records") or []) if isinstance(item, dict)],
            "entity_occurrences": [dict(item) for item in (candidate.get("entity_occurrences") or []) if isinstance(item, dict)],
        }
        chronology_anchor = _chronology_anchor_for_source(source)
        if chronology_anchor is not None:
            source["chronology_anchor"] = chronology_anchor
        spreadsheet_semantics = _spreadsheet_semantics(source)
        if spreadsheet_semantics is not None:
            source["spreadsheet_semantics"] = spreadsheet_semantics
        calendar_semantics = _calendar_semantics(source)
        if calendar_semantics is not None:
            source["calendar_semantics"] = calendar_semantics
        sources.append(source)
        for note in _meeting_note_sources(uid, full_map.get(uid) if isinstance(full_map, dict) else None):
            note.pop("_extracted_from", None)
            sources.append(note)
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
        attachment = cast(dict[str, Any], candidate.get("attachment")) if isinstance(candidate.get("attachment"), dict) else {}
        source_type = _attachment_source_type(candidate, attachment)
        filename = str(attachment.get("filename") or "attachment")
        source_id = f"{source_type}:{uid}:{filename}"
        reliability = _source_reliability_for_attachment(candidate, source_type=source_type)
        source = {
            "source_id": source_id,
            "source_type": source_type,
            "document_kind": _attachment_document_kind(source_type),
            "uid": uid,
            "actor_id": str(candidate.get("sender_actor_id") or ""),
            "title": filename,
            "date": str(candidate.get("date") or ""),
            "snippet": str(candidate.get("snippet") or ""),
            "searchable_text": str(
                attachment.get("text") or attachment.get("extracted_text") or attachment.get("text_preview") or ""
            )[:4000],
            "language_hint_text": str(attachment.get("text") or attachment.get("text_preview") or ""),
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
            "event_records": [dict(item) for item in (candidate.get("event_records") or []) if isinstance(item, dict)],
            "entity_occurrences": [dict(item) for item in (candidate.get("entity_occurrences") or []) if isinstance(item, dict)],
        }
        if isinstance(attachment.get("spreadsheet_semantics"), dict) and attachment.get("spreadsheet_semantics"):
            source["spreadsheet_semantics"] = dict(attachment.get("spreadsheet_semantics") or {})
        if isinstance(attachment.get("calendar_semantics"), dict) and attachment.get("calendar_semantics"):
            source["calendar_semantics"] = dict(attachment.get("calendar_semantics") or {})
        if isinstance(attachment.get("weak_format_semantics"), dict) and attachment.get("weak_format_semantics"):
            source["weak_format_semantics"] = dict(attachment.get("weak_format_semantics") or {})
        chronology_anchor = _chronology_anchor_for_source(source)
        if chronology_anchor is not None:
            source["chronology_anchor"] = chronology_anchor
        spreadsheet_semantics = _spreadsheet_semantics(source)
        if spreadsheet_semantics is not None:
            source["spreadsheet_semantics"] = spreadsheet_semantics
        calendar_semantics = _calendar_semantics(source)
        if calendar_semantics is not None:
            source["calendar_semantics"] = calendar_semantics
        sources.append(source)
        parent_source_id = email_source_ids_by_uid.get(uid)
        weighting = source["source_weighting"]
        can_corroborate_or_contradict = isinstance(weighting, dict) and bool(weighting.get("can_corroborate_or_contradict"))
        if parent_source_id:
            source_links.append(
                {
                    "from_source_id": source_id,
                    "to_source_id": parent_source_id,
                    "link_type": "attached_to_email",
                    "relationship": "can_corroborate_or_contradict_message"
                    if can_corroborate_or_contradict
                    else "reference_only_attachment",
                }
            )
    chat_sources, chat_links, chat_diagnostics, _chat_counts = _chat_log_sources(
        chat_log_entries,
        email_source_ids_by_uid=email_source_ids_by_uid,
        email_sources=[source for source in sources if str(source.get("source_type") or "") == "email"],
    )
    sources.extend(chat_sources)
    source_links.extend(chat_links)
    return _rebuild_bundle_summary(
        {
            "version": MULTI_SOURCE_CASE_BUNDLE_VERSION,
            "summary": {},
            "sources": sources,
            "source_links": source_links,
            "source_link_diagnostics": chat_diagnostics,
            "source_type_profiles": [],
            "chronology_anchors": [],
        }
    )
