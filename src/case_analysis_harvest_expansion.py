# mypy: disable-error-code=name-defined
"""Split archive-harvest helpers (case_analysis_harvest_expansion)."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any, cast

from .case_analysis_scope import derive_case_analysis_query
from .case_operator_intake import ingest_chat_exports
from .matter_file_ingestion import enrich_matter_manifest, infer_matter_manifest_authorized_roots
from .mcp_models import EmailAnswerContextInput, EmailCaseAnalysisInput
from .multi_source_case_bundle import build_standalone_mixed_source_bundle, promotable_mixed_source_evidence_rows
from .question_execution_waves import derive_wave_query_lane_specs, get_wave_definition

if TYPE_CHECKING:
    from .tools.utils import ToolDepsProto

# ruff: noqa: F401,F821


def _best_body_text(email_row: dict[str, Any]) -> str:
    for key in ("forensic_body_text", "body_text", "raw_body_text", "subject"):
        text = _compact(email_row.get(key))
        if text:
            return text
    return ""


def _email_language_fields(email_row: dict[str, Any]) -> dict[str, str]:
    return {
        "detected_language": _compact(email_row.get("detected_language")),
        "detected_language_confidence": _compact(email_row.get("detected_language_confidence")),
    }


_EXPANSION_ERROR_SAMPLE_LIMIT = 8


def _default_expansion_stage_diagnostics(stage: str) -> dict[str, Any]:
    return {
        "stage": stage,
        "status": "ok",
        "attempted_count": 0,
        "expanded_row_count": 0,
        "error_count": 0,
        "errors": [],
    }


def _coerce_expansion_stage_result(
    result: Any,
    *,
    stage: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]]
    diagnostics = _default_expansion_stage_diagnostics(stage)
    if isinstance(result, tuple) and len(result) == 2:
        result_rows = result[0]
        result_diagnostics = result[1]
        rows = [item for item in result_rows if isinstance(item, dict)] if isinstance(result_rows, list) else []
        if isinstance(result_diagnostics, dict):
            diagnostics = {
                **diagnostics,
                **result_diagnostics,
            }
            diagnostics["errors"] = [
                item for item in list(diagnostics.get("errors") or [])[:_EXPANSION_ERROR_SAMPLE_LIMIT] if isinstance(item, dict)
            ]
            diagnostics["error_count"] = int(diagnostics.get("error_count") or len(diagnostics["errors"]))
            diagnostics["attempted_count"] = int(diagnostics.get("attempted_count") or 0)
            diagnostics["expanded_row_count"] = int(diagnostics.get("expanded_row_count") or len(rows))
            diagnostics["status"] = "partial" if int(diagnostics.get("error_count") or 0) > 0 else "ok"
            return rows, diagnostics
        diagnostics["expanded_row_count"] = len(rows)
        return rows, diagnostics
    rows = [item for item in result if isinstance(item, dict)] if isinstance(result, list) else []
    diagnostics["expanded_row_count"] = len(rows)
    return rows, diagnostics


def _aggregate_expansion_diagnostics(rounds: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_rounds = [round_entry for round_entry in rounds if isinstance(round_entry, dict)]
    thread_error_count = sum(
        int((round_entry.get("thread_expansion") or {}).get("error_count") or 0) for round_entry in normalized_rounds
    )
    attachment_error_count = sum(
        int((round_entry.get("attachment_expansion") or {}).get("error_count") or 0) for round_entry in normalized_rounds
    )
    total_error_count = thread_error_count + attachment_error_count
    return {
        "status": "partial" if total_error_count > 0 else "ok",
        "error_count": total_error_count,
        "thread_expansion_error_count": thread_error_count,
        "attachment_expansion_error_count": attachment_error_count,
        "rounds": normalized_rounds,
    }


def _thread_expansion_rows(
    db: Any,
    *,
    evidence_bank: list[dict[str, Any]],
    exhaustive_review: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    diagnostics = _default_expansion_stage_diagnostics("thread_expansion")
    if db is None or not hasattr(db, "get_thread_emails"):
        return [], diagnostics
    existing_uids = {str(item.get("uid") or "") for item in evidence_bank if _compact(item.get("uid"))}
    expanded: list[dict[str, Any]] = []
    for seed in evidence_bank:
        if str(seed.get("candidate_kind") or "") == "attachment":
            continue
        conversation_id = _compact(seed.get("conversation_id"))
        if not conversation_id:
            continue
        diagnostics["attempted_count"] = int(diagnostics.get("attempted_count") or 0) + 1
        try:
            thread_rows = db.get_thread_emails(conversation_id) or []
        except Exception as exc:
            diagnostics["error_count"] = int(diagnostics.get("error_count") or 0) + 1
            errors = cast(list[dict[str, Any]], diagnostics.setdefault("errors", []))
            if len(errors) < _EXPANSION_ERROR_SAMPLE_LIMIT:
                errors.append(
                    {
                        "conversation_id": conversation_id,
                        "seed_uid": _compact(seed.get("uid")),
                        "error_type": type(exc).__name__,
                        "error": _compact(str(exc))[:240],
                    }
                )
            continue
        relevance_terms = _seed_relevance_terms(seed)
        ranked_thread_rows = sorted(
            [row for row in thread_rows if isinstance(row, dict)],
            key=lambda row: (
                -_text_overlap_score(
                    haystack=" ".join(
                        [
                            str(row.get("subject") or ""),
                            str(row.get("sender_name") or ""),
                            str(row.get("sender_email") or ""),
                            _best_body_text(dict(row)),
                        ]
                    ),
                    terms=relevance_terms,
                ),
                0 if bool(row.get("has_attachments") or row.get("attachment_count")) else 1,
                str(row.get("date") or ""),
            ),
        )
        max_additions = 4 if exhaustive_review else 2
        additions = 0
        for row in ranked_thread_rows:
            uid = _compact(row.get("uid"))
            if not uid or uid in existing_uids:
                continue
            relevance_score = _text_overlap_score(
                haystack=" ".join([str(row.get("subject") or ""), _best_body_text(dict(row))]),
                terms=relevance_terms,
            )
            existing_uids.add(uid)
            expanded.append(
                {
                    "uid": uid,
                    "chunk_id": f"{uid}:thread_expansion",
                    "score": float(seed.get("score") or 0.0) * (0.85 + min(relevance_score, 4) * 0.03),
                    "subject": _compact(row.get("subject")),
                    "sender_email": _compact(row.get("sender_email")),
                    "sender_name": _compact(row.get("sender_name")),
                    "date": _compact(row.get("date")),
                    "conversation_id": conversation_id,
                    "folder": _compact(row.get("folder")),
                    "has_attachments": bool(row.get("has_attachments") or row.get("attachment_count")),
                    "candidate_kind": "body",
                    "attachment_filename": "",
                    "snippet": _best_body_text(dict(row))[:280],
                    "matched_query_lanes": list(seed.get("matched_query_lanes") or []),
                    "matched_query_queries": list(seed.get("matched_query_queries") or []),
                    "result_key": f"{uid}:thread_expansion",
                    "harvest_source": "thread_expansion",
                    "harvest_round": int(seed.get("harvest_round") or 0),
                    "verification_status": "thread_context",
                    "relevance_score": relevance_score,
                    **_email_language_fields(dict(row)),
                    "provenance": {
                        "evidence_handle": f"thread:{uid}:{conversation_id}",
                        "uid": uid,
                        "conversation_id": conversation_id,
                        "body_render_source": "thread_expansion",
                    },
                }
            )
            additions += 1
            if additions >= max_additions:
                break
    diagnostics["expanded_row_count"] = len(expanded)
    diagnostics["status"] = "partial" if int(diagnostics.get("error_count") or 0) > 0 else "ok"
    return expanded, diagnostics


def _attachment_expansion_rows(
    db: Any,
    *,
    evidence_bank: list[dict[str, Any]],
    exhaustive_review: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    diagnostics = _default_expansion_stage_diagnostics("attachment_expansion")
    if db is None or not hasattr(db, "attachments_for_email"):
        return [], diagnostics
    expanded: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in evidence_bank:
        uid = _compact(item.get("uid"))
        if not uid:
            continue
        diagnostics["attempted_count"] = int(diagnostics.get("attempted_count") or 0) + 1
        try:
            attachments = db.attachments_for_email(uid) or []
        except Exception as exc:
            diagnostics["error_count"] = int(diagnostics.get("error_count") or 0) + 1
            errors = cast(list[dict[str, Any]], diagnostics.setdefault("errors", []))
            if len(errors) < _EXPANSION_ERROR_SAMPLE_LIMIT:
                errors.append(
                    {
                        "uid": uid,
                        "seed_result_key": _compact(item.get("result_key")),
                        "error_type": type(exc).__name__,
                        "error": _compact(str(exc))[:240],
                    }
                )
            continue
        relevance_terms = _seed_relevance_terms(item)
        ranked_attachments = sorted(
            [attachment for attachment in attachments if isinstance(attachment, dict)],
            key=lambda attachment: (
                -_text_overlap_score(
                    haystack=" ".join(
                        [
                            str(attachment.get("name") or ""),
                            str(attachment.get("extracted_text") or ""),
                            str(attachment.get("text_preview") or ""),
                            str((attachment.get("documentary_support") or {}).get("source_type_hint") or ""),
                        ]
                    ),
                    terms=relevance_terms,
                ),
                0 if not bool(attachment.get("is_inline")) else 1,
                0 if bool(_compact(attachment.get("extracted_text") or attachment.get("text_preview"))) else 1,
                0
                if _compact((attachment.get("documentary_support") or {}).get("source_type_hint"))
                in {"formal_document", "note_record", "participation_record", "time_record"}
                else 1,
                0 if _compact(attachment.get("name")).lower().endswith((".pdf", ".eml", ".ics", ".docx", ".txt")) else 1,
                _compact(attachment.get("name")).casefold(),
            ),
        )
        selected = []
        for attachment in ranked_attachments:
            if bool(attachment.get("is_inline")) and not _compact(
                attachment.get("extracted_text") or attachment.get("text_preview")
            ):
                continue
            selected.append(attachment)
            if len(selected) >= (5 if exhaustive_review else 3):
                break
        for attachment in selected:
            filename = _compact(attachment.get("name"))
            if not filename or (uid, filename) in seen:
                continue
            seen.add((uid, filename))
            relevance_score = _text_overlap_score(
                haystack=" ".join(
                    [
                        str(attachment.get("name") or ""),
                        str(attachment.get("extracted_text") or ""),
                        str(attachment.get("text_preview") or ""),
                    ]
                ),
                terms=relevance_terms,
            )
            snippet = _compact(attachment.get("extracted_text") or attachment.get("text_preview") or attachment.get("name"))
            expanded.append(
                {
                    "uid": uid,
                    "chunk_id": f"{uid}:attachment:{filename}",
                    "score": float(item.get("score") or 0.0) * (0.8 + min(relevance_score, 4) * 0.04),
                    "subject": _compact(item.get("subject")),
                    "sender_email": _compact(item.get("sender_email")),
                    "sender_name": _compact(item.get("sender_name")),
                    "date": _compact(item.get("date")),
                    "conversation_id": _compact(item.get("conversation_id")),
                    "folder": _compact(item.get("folder")),
                    "has_attachments": True,
                    "candidate_kind": "attachment",
                    "attachment_filename": filename,
                    "snippet": snippet[:280],
                    "matched_query_lanes": list(item.get("matched_query_lanes") or []),
                    "matched_query_queries": list(item.get("matched_query_queries") or []),
                    "result_key": f"{uid}:attachment:{filename}",
                    "harvest_source": "attachment_expansion",
                    "harvest_round": int(item.get("harvest_round") or 0),
                    "verification_status": "attachment_reference",
                    "relevance_score": relevance_score,
                    "attachment": {
                        "filename": filename,
                        "mime_type": _compact(attachment.get("mime_type")),
                        "evidence_strength": _compact(attachment.get("evidence_strength")) or "weak_reference",
                        "text_available": bool(_compact(attachment.get("extracted_text") or attachment.get("text_preview"))),
                    },
                    "detected_language": _compact(item.get("detected_language")),
                    "detected_language_confidence": _compact(item.get("detected_language_confidence")),
                    "provenance": {
                        "evidence_handle": f"attachment:{uid}:{filename}",
                        "uid": uid,
                        "attachment_filename": filename,
                        "body_render_source": "attachment_expansion",
                    },
                }
            )
    diagnostics["expanded_row_count"] = len(expanded)
    diagnostics["status"] = "partial" if int(diagnostics.get("error_count") or 0) > 0 else "ok"
    return expanded, diagnostics


def _enrich_evidence_bank(
    *,
    db: Any,
    answer_params: EmailAnswerContextInput,
    bank_entries: list[dict[str, Any]],
    bank_results: list[Any],
    exhaustive_review: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from .tools import search_answer_context_impl as impl

    enriched: list[dict[str, Any]] = []
    for index, entry in enumerate(bank_entries):
        result = bank_results[index] if index < len(bank_results) else None
        if result is None:
            enriched.append(dict(entry))
            continue
        metadata = dict(result.metadata) if isinstance(result.metadata, dict) else {}
        metadata.setdefault("evidence_mode", answer_params.evidence_mode)
        uid = _compact(metadata.get("uid"))
        if _compact(metadata.get("score_kind")) == "segment_sql":
            segment_full_email: dict[str, Any] = {}
            if db is not None and uid and hasattr(db, "get_emails_full_batch"):
                segment_full_email = dict((db.get_emails_full_batch([uid]) or {}).get(uid) or {})
            thread_locator = impl._thread_locator_for_candidate(
                {"uid": uid, "conversation_id": metadata.get("conversation_id", "")},
                segment_full_email or None,
            )
            recipients_summary = impl._recipients_summary(segment_full_email or None)
            speaker_attribution = impl._speaker_attribution_for_candidate(
                db,
                uid=uid,
                conversation_id=str(metadata.get("conversation_id") or ""),
                sender_email=str(metadata.get("sender_email") or ""),
                sender_name=str(metadata.get("sender_name") or ""),
                conversation_context=None,
                full_email=segment_full_email or None,
            )
            reply_context_from, reply_context_emails = impl._reply_context_identities(
                segment_full_email or None,
                str(metadata.get("sender_email") or ""),
            )
            enriched.append(
                {
                    **dict(entry),
                    "rank": index + 1,
                    "uid": uid,
                    "subject": metadata.get("subject", ""),
                    "sender_email": metadata.get("sender_email", ""),
                    "sender_name": metadata.get("sender_name", ""),
                    "date": metadata.get("date", ""),
                    "conversation_id": metadata.get("conversation_id", ""),
                    "score": float(getattr(result, "score", 0.0) or 0.0),
                    "snippet": impl._snippet(getattr(result, "text", "") or ""),
                    "body_render_mode": "segment",
                    "body_render_source": _compact(metadata.get("body_render_source")) or "message_segments",
                    "verification_status": "segment_exact",
                    "provenance": {
                        "evidence_handle": (
                            f"segment:{uid}:{_compact(metadata.get('segment_type'))}:{int(metadata.get('segment_ordinal') or 0)}"
                        ),
                        "uid": uid,
                        "segment_type": _compact(metadata.get("segment_type")),
                        "segment_ordinal": int(metadata.get("segment_ordinal") or 0),
                        "body_render_source": _compact(metadata.get("body_render_source")) or "message_segments",
                    },
                    "candidate_kind": "body",
                    "harvest_source": "segment_search",
                    "harvest_round": int(entry.get("harvest_round") or 0),
                    "segment_type": _compact(metadata.get("segment_type")),
                    "segment_ordinal": int(metadata.get("segment_ordinal") or 0),
                    **_email_language_fields(segment_full_email or metadata),
                    "recipients_summary": recipients_summary,
                    "speaker_attribution": speaker_attribution,
                    "reply_context_from": reply_context_from,
                    "reply_context_emails": reply_context_emails,
                    **thread_locator,
                }
            )
            continue
        if _compact(entry.get("candidate_kind")) == "attachment":
            attachment_candidate = impl._attachment_candidate(db, result, rank=index + 1, params=answer_params)
            attachment_candidate["harvest_source"] = "search_result"
            attachment_candidate["harvest_round"] = int(entry.get("harvest_round") or 0)
            enriched.append({**dict(entry), **attachment_candidate, "candidate_kind": "attachment"})
            continue
        retrieval_snippet = impl._snippet(getattr(result, "text", "") or "")
        provenance_result = impl._provenance_for_candidate(
            db,
            uid,
            retrieval_snippet,
            metadata=metadata,
        )
        snippet = provenance_result[0]
        body_render_mode = provenance_result[1]
        body_render_source = provenance_result[2]
        verification_status = provenance_result[3]
        provenance_payload = provenance_result[4]
        full_email: dict[str, Any] | None = provenance_result[5]
        thread_locator = impl._thread_locator_for_candidate(
            {"uid": uid, "conversation_id": metadata.get("conversation_id", "")},
            full_email,
        )
        recipients_summary = impl._recipients_summary(full_email)
        speaker_attribution = impl._speaker_attribution_for_candidate(
            db,
            uid=uid,
            conversation_id=str(metadata.get("conversation_id") or ""),
            sender_email=str(metadata.get("sender_email") or ""),
            sender_name=str(metadata.get("sender_name") or ""),
            conversation_context=None,
            full_email=full_email,
        )
        reply_context_from, reply_context_emails = impl._reply_context_identities(
            full_email,
            str(metadata.get("sender_email") or ""),
        )
        enriched.append(
            {
                **dict(entry),
                "rank": index + 1,
                "uid": uid,
                "subject": metadata.get("subject", ""),
                "sender_email": metadata.get("sender_email", ""),
                "sender_name": metadata.get("sender_name", ""),
                "date": metadata.get("date", ""),
                "conversation_id": metadata.get("conversation_id", ""),
                "score": float(getattr(result, "score", 0.0) or 0.0),
                "snippet": snippet,
                "body_render_mode": body_render_mode,
                "body_render_source": body_render_source,
                "verification_status": verification_status,
                "provenance": provenance_payload,
                "candidate_kind": "body",
                "harvest_source": "search_result",
                "harvest_round": int(entry.get("harvest_round") or 0),
                **_email_language_fields(full_email or {}),
                "recipients_summary": recipients_summary,
                "speaker_attribution": speaker_attribution,
                "reply_context_from": reply_context_from,
                "reply_context_emails": reply_context_emails,
                **thread_locator,
            }
        )
    candidate_uids = [str(item.get("uid") or "") for item in enriched if _compact(item.get("uid"))]
    if db is not None and candidate_uids:
        event_map = db.event_records_for_uids(candidate_uids) if hasattr(db, "event_records_for_uids") else {}
        occurrence_map = db.entity_occurrences_for_uids(candidate_uids) if hasattr(db, "entity_occurrences_for_uids") else {}
        for row in enriched:
            uid = _compact(row.get("uid"))
            if not uid:
                continue
            events = event_map.get(uid) if isinstance(event_map, dict) else None
            if isinstance(events, list) and events:
                row["event_records"] = [dict(item) for item in events if isinstance(item, dict)]
            occurrences = occurrence_map.get(uid) if isinstance(occurrence_map, dict) else None
            if isinstance(occurrences, list) and occurrences:
                row["entity_occurrences"] = [dict(item) for item in occurrences if isinstance(item, dict)]

    expanded = [*enriched]
    thread_rows, thread_diagnostics = _coerce_expansion_stage_result(
        _thread_expansion_rows(db, evidence_bank=enriched, exhaustive_review=exhaustive_review),
        stage="thread_expansion",
    )
    attachment_rows, attachment_diagnostics = _coerce_expansion_stage_result(
        _attachment_expansion_rows(db, evidence_bank=enriched, exhaustive_review=exhaustive_review),
        stage="attachment_expansion",
    )
    expanded.extend(thread_rows)
    expanded.extend(attachment_rows)
    expansion_diagnostics = {
        "status": (
            "partial"
            if int(thread_diagnostics.get("error_count") or 0) > 0 or int(attachment_diagnostics.get("error_count") or 0) > 0
            else "ok"
        ),
        "error_count": int(thread_diagnostics.get("error_count") or 0) + int(attachment_diagnostics.get("error_count") or 0),
        "thread_expansion": thread_diagnostics,
        "attachment_expansion": attachment_diagnostics,
    }
    return expanded, expansion_diagnostics


__all__ = [
    "_EXPANSION_ERROR_SAMPLE_LIMIT",
    "_aggregate_expansion_diagnostics",
    "_attachment_expansion_rows",
    "_best_body_text",
    "_coerce_expansion_stage_result",
    "_default_expansion_stage_diagnostics",
    "_email_language_fields",
    "_enrich_evidence_bank",
    "_thread_expansion_rows",
]
