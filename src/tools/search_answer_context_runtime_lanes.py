# mypy: disable-error-code=name-defined
"""Split helpers for search answer-context runtime (search_answer_context_runtime_lanes)."""

from __future__ import annotations

import re
from typing import Any

from ..actor_resolution import resolve_actor_graph
from ..behavioral_evidence_chains import build_behavioral_evidence_chains
from ..behavioral_strength import apply_behavioral_strength
from ..case_intake import build_case_bundle
from ..communication_graph import build_communication_graph
from ..comparative_treatment import build_comparative_treatment
from ..cross_message_patterns import build_case_patterns
from ..formatting import weak_message_semantics
from ..investigation_report import build_investigation_report
from ..mcp_models import EmailAnswerContextInput
from ..multi_source_case_bundle import build_multi_source_case_bundle
from ..power_context import apply_power_context_to_actor_graph, build_power_context
from ..trigger_retaliation import build_retaliation_analysis
from . import search_answer_context_impl as impl
from .search_answer_context_budget import (
    _compact_snippets_for_budget,
    _compact_timeline_events,
    _dedupe_evidence_items,
    _estimated_json_chars,
    _reindex_evidence,
    _strip_optional_evidence_fields,
    _summarize_conversation_groups_for_budget,
    _summarize_timeline_for_budget,
    _weakest_evidence_target,
)
from .search_answer_context_case_payloads import _apply_actor_ids_to_candidates, _apply_actor_ids_to_case_bundle
from .search_answer_context_rendering import (
    _answer_policy,
    _answer_quality,
    _final_answer_contract,
    _render_final_answer,
    _resolve_exact_wording_requested,
)
from .search_answer_context_runtime_payload import _compact_optional_case_surfaces, build_payload, rebuild_sections
from .utils import ToolDepsProto, json_response

# ruff: noqa: F401


def _segment_search_results(
    *,
    retriever: Any,
    lane_query: str,
    lane_id: str,
    limit: int,
    scan_id: str | None = None,
) -> tuple[list[Any], dict[str, Any]]:
    db = getattr(retriever, "email_db", None)
    if db is None or not hasattr(db, "search_message_segments"):
        return [], {"segment_result_count": 0, "segment_excluded_count": 0}

    from ..retriever_models import SearchResult

    try:
        rows = db.search_message_segments(lane_query, limit=limit)
    except Exception:
        return [], {"segment_result_count": 0, "segment_excluded_count": 0}

    segment_results = [
        SearchResult(
            chunk_id=f"{row['uid']}__segment_{int(row['ordinal'])}",
            text=str(row.get("segment_text") or ""),
            metadata={
                "uid": str(row.get("uid") or ""),
                "subject": str(row.get("subject") or ""),
                "sender_email": str(row.get("sender_email") or ""),
                "sender_name": str(row.get("sender_name") or ""),
                "date": str(row.get("date") or ""),
                "conversation_id": str(row.get("conversation_id") or ""),
                "folder": str(row.get("folder") or ""),
                "has_attachments": bool(row.get("has_attachments") or row.get("attachment_count")),
                "detected_language": str(row.get("detected_language") or ""),
                "detected_language_confidence": str(row.get("detected_language_confidence") or ""),
                "segment_type": str(row.get("segment_type") or ""),
                "segment_ordinal": int(row.get("ordinal") or 0),
                "source_surface": str(row.get("source_surface") or ""),
                "body_render_source": f"message_segments:{(row.get('segment_type') or '')!s}",
                "score_kind": "segment_sql",
                "score_calibration": "synthetic",
                "result_key": f"segment:{row['uid']}:{int(row.get('ordinal') or 0)}",
                "matched_query_lanes": [lane_id],
                "matched_query_queries": [lane_query],
            },
            distance=max(0.0, 1.0 - float(row.get("score") or 0.0)),
        )
        for row in rows
    ]

    if scan_id and segment_results:
        from ..scan_session import filter_seen

        segment_results, scan_meta = filter_seen(scan_id, segment_results)
    else:
        scan_meta = None

    return segment_results, {
        "segment_result_count": len(segment_results),
        "segment_excluded_count": int((scan_meta or {}).get("excluded_count") or 0),
    }


def _derive_query_lanes(
    *,
    retriever: Any,
    params: EmailAnswerContextInput,
    search_kwargs: dict[str, Any],
) -> list[str]:
    exact_wording_requested = _resolve_exact_wording_requested(
        question=params.question,
        explicit=(
            bool(search_kwargs.get("_exact_wording_requested"))
            if search_kwargs.get("_exact_wording_requested") is not None
            else getattr(params, "exact_wording_requested", None)
        ),
    )

    def _append_lane(lanes: list[str], lane: str) -> None:
        compact = " ".join(str(lane or "").split()).strip()
        if not compact:
            return
        lowered = compact.casefold()
        if any(existing.casefold() == lowered for existing in lanes):
            return
        lanes.append(compact[:500])

    def _case_scope_query_lanes() -> list[str]:
        case_scope = params.case_scope
        if case_scope is None:
            return []
        lanes: list[str] = []
        base_query = " ".join(str(search_kwargs.get("query") or "").split()).strip()
        target_bits = [
            value
            for value in (
                str(getattr(case_scope.target_person, "name", "") or "").strip(),
                str(getattr(case_scope.target_person, "email", "") or "").strip(),
            )
            if value
        ]
        actor_bits = [
            value
            for actor in [
                *case_scope.suspected_actors[:6],
                *case_scope.comparator_actors[:4],
                *getattr(case_scope, "context_people", [])[:4],
            ]
            for value in (
                str(getattr(actor, "name", "") or "").strip(),
                str(getattr(actor, "email", "") or "").strip(),
                str(getattr(actor, "role_hint", "") or "").strip(),
            )
            if value
        ]
        institutional_bits = [
            value
            for actor in getattr(case_scope, "institutional_actors", [])[:4]
            for value in (
                str(getattr(actor, "label", "") or "").strip(),
                str(getattr(actor, "email", "") or "").strip(),
                str(getattr(actor, "function", "") or "").strip(),
            )
            if value
        ]
        issue_track_terms = [
            value
            for track in case_scope.employment_issue_tracks[:8]
            if str(track).strip()
            for value in [str(track).replace("_", " ").strip(), str(track).strip()]
            if value
        ]
        issue_tag_terms = [str(item).strip() for item in case_scope.employment_issue_tags[:8] if str(item).strip()]
        allegation_terms = [str(item).replace("_", " ").strip() for item in case_scope.allegation_focus[:6] if str(item).strip()]
        trigger_terms = [
            " ".join(
                bit
                for bit in (
                    str(getattr(event, "date", "") or "").strip(),
                    str(getattr(event, "trigger_type", "") or "").replace("_", " ").strip(),
                )
                if bit
            ).strip()
            for event in case_scope.trigger_events[:4]
        ]
        attachment_terms = ["attachment", "record", "calendar", "meeting note", "document", "protocol"]
        _append_lane(lanes, base_query)
        if exact_wording_requested:
            _append_lane(lanes, " ".join([base_query, *target_bits[:1], *actor_bits[:4], *institutional_bits[:2]]))
            if trigger_terms:
                _append_lane(
                    lanes,
                    " ".join(
                        [*target_bits[:1], *trigger_terms[:3], *actor_bits[:2], *institutional_bits[:1], *issue_track_terms[:1]]
                    ),
                )
            _append_lane(lanes, " ".join([*target_bits[:1], *issue_track_terms[:3], *issue_tag_terms[:2], *allegation_terms[:2]]))
            if case_scope.comparator_actors:
                comparator_bits = [
                    value
                    for actor in case_scope.comparator_actors[:4]
                    for value in (
                        str(getattr(actor, "name", "") or "").strip(),
                        str(getattr(actor, "email", "") or "").strip(),
                    )
                    if value
                ]
                _append_lane(
                    lanes, " ".join([*target_bits[:1], *comparator_bits[:4], *issue_track_terms[:2], *allegation_terms[:1]])
                )
            _append_lane(
                lanes,
                " ".join(
                    [*target_bits[:1], *attachment_terms[:4], *institutional_bits[:2], *trigger_terms[:1], *issue_track_terms[:1]]
                ),
            )
            return lanes[:8]
        _append_lane(
            lanes,
            " ".join(
                [
                    base_query,
                    *target_bits[:1],
                    *actor_bits[:4],
                    *institutional_bits[:2],
                    *issue_track_terms[:2],
                    *issue_tag_terms[:2],
                ]
            ),
        )
        _append_lane(lanes, " ".join([*target_bits[:1], *allegation_terms[:3], *issue_track_terms[:3], *issue_tag_terms[:2]]))
        if trigger_terms:
            _append_lane(lanes, " ".join([*target_bits[:1], *trigger_terms[:3], *issue_track_terms[:2], *allegation_terms[:2]]))
        if case_scope.comparator_actors:
            comparator_bits = [
                value
                for actor in case_scope.comparator_actors[:4]
                for value in (
                    str(getattr(actor, "name", "") or "").strip(),
                    str(getattr(actor, "email", "") or "").strip(),
                )
                if value
            ]
            _append_lane(lanes, " ".join([*target_bits[:1], *comparator_bits[:4], *issue_track_terms[:2], *allegation_terms[:2]]))
        _append_lane(
            lanes,
            " ".join(
                [*target_bits[:1], *attachment_terms[:4], *institutional_bits[:2], *issue_track_terms[:2], *issue_tag_terms[:2]]
            ),
        )
        return lanes[:8]

    explicit = [" ".join(str(item or "").split()).strip() for item in params.query_lanes if str(item or "").strip()]
    if explicit:
        return explicit[:8]
    query = str(search_kwargs.get("query") or "").strip()
    if not query:
        return []
    expand_query_requested = bool(search_kwargs.get("expand_query"))
    expand_query_lanes = getattr(retriever, "_expand_query_lanes", None)
    if expand_query_requested and callable(expand_query_lanes):
        expanded = expand_query_lanes(query, max_lanes=4)
        expanded_lanes: list[Any] = []
        if isinstance(expanded, list):
            expanded_lanes = list(expanded)
        lanes = [" ".join(str(item or "").split()).strip() for item in expanded_lanes if str(item or "").strip()]
        if lanes:
            scope_lanes = _case_scope_query_lanes()
            if scope_lanes:
                combined: list[str] = []
                for lane in [*scope_lanes, *lanes]:
                    _append_lane(combined, lane)
                return combined[:8]
            return lanes
    scope_lanes = _case_scope_query_lanes()
    if scope_lanes:
        return scope_lanes[:8]
    return [query]


__all__ = [
    "_derive_query_lanes",
    "_segment_search_results",
]
