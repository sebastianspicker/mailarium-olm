# mypy: disable-error-code=name-defined
"""Candidate-row builders for answer-context runtime payloads."""

from __future__ import annotations

from typing import Any

from . import search_answer_context_impl as impl
from .search_answer_context_runtime_ranking import _support_type_for_result, _support_type_for_row


def build_initial_candidate_rows(
    *,
    preloaded_rows: list[dict[str, Any]],
    results: list[Any],
    db: Any,
    params: Any,
    exact_wording: bool,
    later_round_only_handles: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert preloaded evidence rows or search results into payload candidates."""
    candidates: list[dict[str, Any]] = []
    attachment_candidates: list[dict[str, Any]] = []
    if preloaded_rows:

        def _row_rank_key(row: dict[str, Any]) -> tuple[float, float, str]:
            score = float(row.get("score") or 0.0)
            if str(row.get("score_calibration") or "").strip() == "calibrated":
                score += 0.03
            if str(row.get("score_kind") or "").strip() == "segment_sql":
                score += 0.015
            if row.get("attachment") or row.get("attachment_filename"):
                score += 0.01
                attachment = row.get("attachment") if isinstance(row.get("attachment"), dict) else {}
                if str((attachment or {}).get("evidence_strength") or row.get("evidence_strength") or "") == "strong_text":
                    score += 0.015
                extraction_state = str((attachment or {}).get("extraction_state") or row.get("extraction_state") or "")
                if extraction_state.strip().lower() in {"ocr_text_extracted", "archive_contents_extracted"}:
                    score += 0.005
            locator_fields_present = sum(
                1
                for key in (
                    "attachment_id",
                    "content_sha256",
                    "segment_ordinal",
                    "snippet_start",
                    "snippet_end",
                    "char_start",
                    "char_end",
                )
                if row.get(key) not in (None, "", 0)
            )
            if locator_fields_present >= 2:
                score += 0.012
            elif locator_fields_present == 1:
                score += 0.006
            if str(row.get("verification_status") or "").strip() in {
                "retrieval_exact",
                "forensic_exact",
                "hybrid_verified_forensic",
                "segment_exact",
            }:
                score += 0.015
            elif str(row.get("verification_status") or "").strip() == "near_exact_verified":
                score += 0.008
            if exact_wording:
                verification_status = str(row.get("verification_status") or "").strip()
                if verification_status in {"forensic_exact", "segment_exact"}:
                    score += 0.07
                elif verification_status in {"retrieval_exact", "hybrid_verified_forensic"}:
                    score += 0.04
                if str(row.get("body_render_source") or "").strip() in {
                    "forensic_body_text",
                    "message_segments",
                    "quoted_reply",
                }:
                    score += 0.02
                if verification_status in {"thread_context", "attachment_reference", "mixed_source_reference"}:
                    score -= 0.025
            return (score, float(row.get("score") or 0.0), str(row.get("result_key") or row.get("uid") or ""))

        ordered_rows = sorted(preloaded_rows, key=_row_rank_key, reverse=True)
        for rank, row in enumerate(ordered_rows, start=1):
            uid = str(row.get("uid") or "")
            provenance = dict(row.get("provenance") or {})
            document_locator = dict(row.get("document_locator") or {})
            matched_query_lanes = [str(item) for item in row.get("matched_query_lanes", []) if item]
            matched_query_queries = [str(item) for item in row.get("matched_query_queries", []) if item]
            source_id = str(row.get("source_id") or (f"email:{uid}" if uid else row.get("result_key") or ""))
            source_type = str(row.get("source_type") or "")
            candidate_related_source_ids = [
                str(item) for item in row.get("candidate_related_source_ids", []) if str(item).strip()
            ]
            candidate_related_sources = [
                dict(item) for item in row.get("candidate_related_sources", []) if isinstance(item, dict)
            ]
            if str(row.get("candidate_kind") or "") == "attachment" or isinstance(row.get("attachment"), dict):
                attachment = dict(row.get("attachment") or {})
                filename = str(attachment.get("filename") or row.get("attachment_filename") or "attachment")
                attachment.setdefault("filename", filename)
                source_type_hint = str(attachment.get("source_type_hint") or row.get("source_type") or "attachment")
                provenance.setdefault(
                    "evidence_handle",
                    str(document_locator.get("evidence_handle") or source_id or f"{source_type_hint}:{uid}:{filename}"),
                )
                evidence_handle = str(provenance.get("evidence_handle") or "")
                attachment_candidates.append(
                    {
                        "rank": rank,
                        "uid": uid,
                        "source_id": source_id or f"{source_type_hint}:{uid}:{filename}",
                        "source_type": source_type or source_type_hint,
                        "subject": row.get("subject", ""),
                        "sender_email": row.get("sender_email", ""),
                        "sender_name": row.get("sender_name", ""),
                        "date": row.get("date", ""),
                        "conversation_id": row.get("conversation_id", ""),
                        "score": float(row.get("score") or 0.0),
                        "snippet": row.get("snippet", ""),
                        "match_reason": row.get("match_reason") or impl._match_reason(rank, params),
                        "attachment": attachment,
                        "provenance": provenance,
                        "verification_status": row.get("verification_status", "attachment_reference"),
                        "exact_wording_requested": exact_wording,
                        "score_kind": row.get("score_kind", "semantic"),
                        "score_calibration": row.get("score_calibration", "calibrated"),
                        "result_key": row.get("result_key", ""),
                        "matched_query_lanes": matched_query_lanes,
                        "matched_query_queries": matched_query_queries,
                        "support_type": _support_type_for_row(row),
                        "document_locator": document_locator,
                        "source_reliability": dict(row.get("source_reliability") or {}),
                        "candidate_related_source_ids": candidate_related_source_ids,
                        "candidate_related_sources": candidate_related_sources,
                        "harvest_round": int(row.get("harvest_round") or 0),
                        "later_round_recovery": int(row.get("harvest_round") or 0) > 0,
                        "later_round_only_recovery": evidence_handle in later_round_only_handles,
                        "follow_up": row.get("follow_up") or ({"tool": "email_deep_context", "uid": uid} if uid else {}),
                    }
                )
                continue
            provenance.setdefault("evidence_handle", str(document_locator.get("evidence_handle") or source_id or f"email:{uid}"))
            evidence_handle = str(provenance.get("evidence_handle") or "")
            candidates.append(
                {
                    "rank": rank,
                    "uid": uid,
                    "source_id": source_id or f"email:{uid}",
                    "source_type": source_type or ("email" if uid else "mixed_source"),
                    "subject": row.get("subject", ""),
                    "sender_email": row.get("sender_email", ""),
                    "sender_name": row.get("sender_name", ""),
                    "date": row.get("date", ""),
                    "conversation_id": row.get("conversation_id", ""),
                    "score": float(row.get("score") or 0.0),
                    "snippet": row.get("snippet", ""),
                    "match_reason": row.get("match_reason") or impl._match_reason(rank, params),
                    "body_render_mode": row.get("body_render_mode", "quoted_snippet"),
                    "body_render_source": row.get("body_render_source", row.get("harvest_source", "retrieval")),
                    "verification_status": row.get("verification_status", "retrieval_exact"),
                    "exact_wording_requested": exact_wording,
                    "provenance": provenance,
                    "score_kind": row.get("score_kind", "semantic"),
                    "score_calibration": row.get("score_calibration", "calibrated"),
                    "result_key": row.get("result_key", ""),
                    "matched_query_lanes": matched_query_lanes,
                    "matched_query_queries": matched_query_queries,
                    "support_type": _support_type_for_row(row),
                    "document_locator": document_locator,
                    "source_reliability": dict(row.get("source_reliability") or {}),
                    "candidate_related_source_ids": candidate_related_source_ids,
                    "candidate_related_sources": candidate_related_sources,
                    "harvest_round": int(row.get("harvest_round") or 0),
                    "later_round_recovery": int(row.get("harvest_round") or 0) > 0,
                    "later_round_only_recovery": evidence_handle in later_round_only_handles,
                    "follow_up": row.get("follow_up") or ({"tool": "email_deep_context", "uid": uid} if uid else {}),
                }
            )
    else:
        for rank, result in enumerate(results, start=1):
            metadata = result.metadata
            uid = str(metadata.get("uid", ""))
            if impl._is_attachment_result(metadata, chunk_id=result.chunk_id):
                attachment_candidate = impl._attachment_candidate(
                    db,
                    result,
                    rank=rank,
                    params=params,
                )
                attachment = attachment_candidate.get("attachment") or {}
                source_type_hint = str(
                    (attachment if isinstance(attachment, dict) else {}).get("source_type_hint") or "attachment"
                )
                filename = str((attachment if isinstance(attachment, dict) else {}).get("filename") or "attachment")
                attachment_candidate["source_id"] = f"{source_type_hint}:{uid}:{filename}"
                attachment_candidate["verification_status"] = str(metadata.get("verification_status") or "attachment_reference")
                attachment_candidate["exact_wording_requested"] = exact_wording
                attachment_candidate["score_kind"] = str(metadata.get("score_kind") or "semantic")
                attachment_candidate["score_calibration"] = str(metadata.get("score_calibration") or "calibrated")
                attachment_candidate["result_key"] = str(metadata.get("result_key") or "")
                attachment_candidate["matched_query_lanes"] = [
                    str(item) for item in metadata.get("matched_query_lanes", []) if item
                ]
                attachment_candidate["matched_query_queries"] = [
                    str(item) for item in metadata.get("matched_query_queries", []) if item
                ]
                attachment_candidate["support_type"] = _support_type_for_result(
                    result,
                    matched_queries=attachment_candidate["matched_query_queries"],
                )
                attachment_candidates.append(attachment_candidate)
                continue
            retrieval_snippet = impl._snippet(result.text)
            metadata = {**metadata, "evidence_mode": params.evidence_mode}
            snippet, body_render_mode, body_render_source, verification_status, provenance, _full_email = (
                impl._provenance_for_candidate(
                    db,
                    uid,
                    retrieval_snippet,
                    metadata=metadata,
                )
            )
            candidates.append(
                {
                    "rank": rank,
                    "uid": uid,
                    "source_id": f"email:{uid}",
                    "subject": metadata.get("subject", ""),
                    "sender_email": metadata.get("sender_email", ""),
                    "sender_name": metadata.get("sender_name", ""),
                    "date": metadata.get("date", ""),
                    "conversation_id": metadata.get("conversation_id", ""),
                    "score": result.score,
                    "snippet": snippet,
                    "match_reason": impl._match_reason(rank, params),
                    "body_render_mode": body_render_mode,
                    "body_render_source": body_render_source,
                    "verification_status": verification_status,
                    "exact_wording_requested": exact_wording,
                    "provenance": provenance,
                    "score_kind": metadata.get("score_kind", "semantic"),
                    "score_calibration": metadata.get("score_calibration", "calibrated"),
                    "result_key": metadata.get("result_key", ""),
                    "matched_query_lanes": [str(item) for item in metadata.get("matched_query_lanes", []) if item],
                    "matched_query_queries": [str(item) for item in metadata.get("matched_query_queries", []) if item],
                    "support_type": _support_type_for_result(
                        result,
                        matched_queries=[str(item) for item in metadata.get("matched_query_queries", []) if item],
                    ),
                    "follow_up": {
                        "tool": "email_deep_context",
                        "uid": uid,
                    },
                }
            )
    return candidates, attachment_candidates


__all__ = ["build_initial_candidate_rows"]
