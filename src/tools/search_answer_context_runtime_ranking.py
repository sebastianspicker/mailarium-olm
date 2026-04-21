# mypy: disable-error-code=name-defined
"""Split helpers for search answer-context runtime (search_answer_context_runtime_ranking)."""

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


def _bank_entry(
    *,
    result: Any,
    key: str,
    matched_query_lanes: list[str],
    matched_query_queries: list[str],
) -> dict[str, Any]:
    metadata = result.metadata if isinstance(result.metadata, dict) else {}
    text_preview = impl._snippet(getattr(result, "text", "") or "")
    attachment_filename = str(metadata.get("attachment_filename") or metadata.get("filename") or "")
    support_type = _support_type_for_result(result, matched_queries=matched_query_queries)
    return {
        "uid": str(metadata.get("uid") or ""),
        "chunk_id": str(getattr(result, "chunk_id", "") or ""),
        "score": float(getattr(result, "score", 0.0) or 0.0),
        "subject": str(metadata.get("subject") or ""),
        "sender_email": str(metadata.get("sender_email") or ""),
        "sender_name": str(metadata.get("sender_name") or ""),
        "date": str(metadata.get("date") or ""),
        "conversation_id": str(metadata.get("conversation_id") or ""),
        "folder": str(metadata.get("folder") or ""),
        "has_attachments": bool(metadata.get("has_attachments") or metadata.get("attachment_count")),
        "candidate_kind": "attachment" if attachment_filename else "body",
        "support_type": support_type,
        "attachment_filename": attachment_filename,
        "snippet": text_preview,
        "matched_query_lanes": list(matched_query_lanes),
        "matched_query_queries": list(matched_query_queries),
        "result_key": key,
        "score_kind": str(metadata.get("score_kind") or "semantic"),
        "score_calibration": str(metadata.get("score_calibration") or "calibrated"),
        "segment_type": str(metadata.get("segment_type") or ""),
        "segment_ordinal": int(metadata.get("segment_ordinal") or 0),
    }


def _support_type_for_result(result: Any, *, matched_queries: list[str]) -> str:
    metadata = result.metadata if isinstance(result.metadata, dict) else {}
    explicit_support_type = str(metadata.get("support_type") or "").strip().lower()
    if explicit_support_type in {"body", "segment", "attachment", "calendar", "comparator", "counterevidence"}:
        return explicit_support_type

    text = " ".join(
        part
        for part in (
            str(getattr(result, "text", "") or ""),
            str(metadata.get("subject") or ""),
            str(metadata.get("body_render_source") or ""),
            str(metadata.get("segment_type") or ""),
            str(metadata.get("issue_type") or ""),
            str(metadata.get("issue_category") or ""),
            str(metadata.get("source_type") or ""),
        )
        if part
    ).lower()

    def _metadata_terms(key: str) -> set[str]:
        value = metadata.get(key)
        if isinstance(value, str):
            tokens = re.findall(r"[\w-]+", value.lower())
            return {token for token in tokens if token}
        if isinstance(value, list):
            terms: set[str] = set()
            for item in value:
                tokens = re.findall(r"[\w-]+", str(item or "").lower())
                terms.update(token for token in tokens if token)
            return terms
        return set()

    metadata_tokens = set()
    for token_key in (
        "issue_tags",
        "main_issue_tags",
        "all_issue_tags",
        "role_hints",
        "support_tags",
        "source_tags",
    ):
        metadata_tokens.update(_metadata_terms(token_key))

    del matched_queries
    if str(metadata.get("attachment_filename") or metadata.get("filename") or "").strip():
        return "attachment"
    if str(metadata.get("score_kind") or "") == "segment_sql" or str(metadata.get("segment_type") or "").strip():
        return "segment"
    if bool(metadata.get("is_calendar_message")) or any(
        token in text for token in ("calendar", "meeting", "invite", "termin", "besprechung")
    ):
        return "calendar"

    comparator_signals = {
        "vergleich",
        "comparator",
        "peer",
        "gleichbehandlung",
        "ungleichbehandlung",
        "vergleichsgruppe",
        "vergleichsperson",
    }
    if any(token in text for token in comparator_signals) or (comparator_signals & metadata_tokens):
        return "comparator"

    counterevidence_signals = {
        "widerspruch",
        "contradiction",
        "counterevidence",
        "gegenbeleg",
        "omission",
        "unterlassen",
        "nichtantwort",
        "silence",
    }
    if any(token in text for token in counterevidence_signals) or (counterevidence_signals & metadata_tokens):
        return "counterevidence"
    return "body"


def _support_type_for_row(row: dict[str, Any]) -> str:
    declared = str(row.get("support_type") or "").strip().lower()
    if declared:
        return declared
    attachment_filename = ""
    attachment_value: Any = row.get("attachment")
    if isinstance(attachment_value, dict):
        attachment_filename = str(attachment_value.get("filename") or "")
    metadata = {
        "attachment_filename": str(row.get("attachment_filename") or ""),
        "filename": attachment_filename,
        "score_kind": str(row.get("score_kind") or ""),
        "segment_type": str(row.get("segment_type") or ""),
        "is_calendar_message": row.get("is_calendar_message"),
        "subject": str(row.get("subject") or ""),
        "body_render_source": str(row.get("body_render_source") or ""),
    }
    proxy = type("_RowProxy", (), {"metadata": metadata, "text": str(row.get("snippet") or "")})()
    return _support_type_for_result(
        proxy,
        matched_queries=[str(item) for item in row.get("matched_query_queries", []) if str(item).strip()],
    )


def _term_tokens(text: str) -> list[str]:
    return [token for token in re.findall(r"[\w-]+", str(text or "").casefold()) if token]


def _lane_expansion_terms(
    *,
    base_query: str,
    lane_query: str,
    executed_query: str,
    query_expansion_suffix: str,
) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    def _add(tokens: list[str]) -> None:
        for token in tokens:
            compact = token.strip()
            if not compact or compact in seen:
                continue
            seen.add(compact)
            terms.append(compact)

    base_tokens = set(_term_tokens(base_query))
    lane_extra_tokens = [token for token in _term_tokens(lane_query) if token not in base_tokens]
    executed_extra_tokens = [token for token in _term_tokens(executed_query) if token not in base_tokens]

    _add(_term_tokens(query_expansion_suffix))
    _add(lane_extra_tokens)
    _add(executed_extra_tokens)
    return terms


def _result_search_surface(result: Any) -> str:
    metadata = result.metadata if isinstance(result.metadata, dict) else {}
    return " ".join(
        part
        for part in (
            str(getattr(result, "text", "") or ""),
            str(metadata.get("subject") or ""),
            str(metadata.get("segment_type") or ""),
            str(metadata.get("attachment_filename") or metadata.get("filename") or ""),
            str(metadata.get("sender_name") or ""),
            str(metadata.get("sender_email") or ""),
        )
        if part
    ).casefold()


def _lane_recovered_expansion_terms(
    *,
    expansion_terms: list[str],
    new_keys: list[str],
    result_lookup: dict[str, Any],
) -> tuple[list[str], int]:
    if not expansion_terms or not new_keys:
        return [], 0
    recovered: list[str] = []
    seen: set[str] = set()
    recovered_key_count = 0
    for key in new_keys:
        result = result_lookup.get(key)
        if result is None:
            continue
        haystack = _result_search_surface(result)
        matched_any = False
        for term in expansion_terms:
            if term and term in haystack:
                matched_any = True
                if term not in seen:
                    seen.add(term)
                    recovered.append(term)
        if matched_any:
            recovered_key_count += 1
    return recovered, recovered_key_count


def _record_lane_match(
    *,
    key: str,
    lane_id: str,
    lane_query: str,
    lane_hits: dict[str, list[str]],
    lane_queries_by_key: dict[str, list[str]],
) -> None:
    lane_hits.setdefault(key, [])
    lane_queries_by_key.setdefault(key, [])
    if lane_id not in lane_hits[key]:
        lane_hits[key].append(lane_id)
    if lane_query not in lane_queries_by_key[key]:
        lane_queries_by_key[key].append(lane_query)


def _result_identity_key(result: Any, *, fallback: str) -> str:
    metadata = result.metadata if isinstance(result.metadata, dict) else {}
    explicit_key = str(metadata.get("result_key") or "").strip()
    if explicit_key:
        return explicit_key

    chunk_id = str(getattr(result, "chunk_id", "") or "").strip()
    uid = str(metadata.get("uid") or "").strip()
    attachment_filename = str(metadata.get("attachment_filename") or metadata.get("filename") or "").strip()
    if attachment_filename:
        attachment_marker = str(metadata.get("attachment_id") or chunk_id or metadata.get("source_surface") or "attachment")
        return f"attachment:{uid or fallback}:{attachment_filename}:{attachment_marker}"

    segment_ordinal = int(metadata.get("segment_ordinal") or 0)
    score_kind = str(metadata.get("score_kind") or "").strip()
    if score_kind == "segment_sql" or segment_ordinal > 0:
        segment_type = str(metadata.get("segment_type") or metadata.get("source_surface") or "segment").strip()
        return f"segment:{uid or fallback}:{segment_type}:{segment_ordinal or chunk_id or fallback}"

    if chunk_id:
        return f"chunk:{chunk_id}"

    body_render_source = str(metadata.get("body_render_source") or "").strip()
    if uid and body_render_source:
        return f"message:{uid}:{body_render_source}"
    if uid:
        return f"uid:{uid}"
    return fallback


def _result_competition_score(result: Any, *, exact_wording: bool = False) -> float:
    metadata = result.metadata if isinstance(result.metadata, dict) else {}
    score = float(getattr(result, "score", 0.0) or 0.0)
    calibration = str(metadata.get("score_calibration") or "").strip()
    score_kind = str(metadata.get("score_kind") or "").strip()
    verification_status = str(metadata.get("verification_status") or "").strip()
    body_render_source = str(metadata.get("body_render_source") or "").strip()
    has_attachment = bool(str(metadata.get("attachment_filename") or metadata.get("filename") or "").strip())
    if calibration == "calibrated":
        score += 0.03
    elif calibration == "synthetic":
        score -= 0.02
    if score_kind == "segment_sql":
        score += 0.015
    if has_attachment:
        score += 0.01
        if str(metadata.get("evidence_strength") or "") == "strong_text":
            score += 0.015
        if str(metadata.get("extraction_state") or "").strip().lower() in {"ocr_text_extracted", "archive_contents_extracted"}:
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
        if metadata.get(key) not in (None, "", 0)
    )
    if locator_fields_present >= 2:
        score += 0.012
    elif locator_fields_present == 1:
        score += 0.006
    if verification_status in {"retrieval_exact", "forensic_exact", "hybrid_verified_forensic", "segment_exact"}:
        score += 0.015
    elif verification_status == "near_exact_verified":
        score += 0.008
    if exact_wording:
        if verification_status in {"forensic_exact", "segment_exact"}:
            score += 0.07
        elif verification_status in {"retrieval_exact", "hybrid_verified_forensic"}:
            score += 0.04
        if body_render_source in {"forensic_body_text", "message_segments", "quoted_reply"}:
            score += 0.02
        if verification_status in {"thread_context", "attachment_reference", "mixed_source_reference"}:
            score -= 0.025
    return score


def _result_competition_key(result: Any, *, exact_wording: bool = False) -> tuple[float, float, str]:
    metadata = result.metadata if isinstance(result.metadata, dict) else {}
    return (
        _result_competition_score(result, exact_wording=exact_wording),
        float(getattr(result, "score", 0.0) or 0.0),
        str(getattr(result, "chunk_id", "") or metadata.get("uid") or ""),
    )


def _evidence_bank_keys_with_lane_diversity(
    *,
    ranked: list[tuple[str, Any]],
    lane_hits: dict[str, list[str]],
    bank_limit: int,
    reserve_per_lane: int,
) -> list[str]:
    selected_keys: list[str] = []
    if bank_limit <= 0:
        return selected_keys
    lane_order: list[str] = []
    for key, _result in ranked:
        for lane_id in lane_hits.get(key, []):
            if lane_id.startswith("lane_") and lane_id not in lane_order:
                lane_order.append(lane_id)
    for lane_id in lane_order:
        reserved = 0
        for key, _result in ranked:
            if key in selected_keys or lane_id not in lane_hits.get(key, []):
                continue
            selected_keys.append(key)
            reserved += 1
            if reserved >= max(reserve_per_lane, 0) or len(selected_keys) >= bank_limit:
                break
        if len(selected_keys) >= bank_limit:
            return selected_keys[:bank_limit]
    for key, _result in ranked:
        if key in selected_keys:
            continue
        selected_keys.append(key)
        if len(selected_keys) >= bank_limit:
            break
    return selected_keys[:bank_limit]


def _evidence_bank_keys_with_support_diversity(
    *,
    ranked: list[tuple[str, Any]],
    selected_keys: list[str],
    lane_queries_by_key: dict[str, list[str]],
    bank_limit: int,
) -> list[str]:
    if bank_limit <= 0:
        return []
    selected: list[str] = []
    for key in selected_keys:
        if key in selected:
            continue
        selected.append(key)
        if len(selected) >= bank_limit:
            break

    support_types_present = {
        _support_type_for_result(result, matched_queries=lane_queries_by_key.get(key, []))
        for key, result in ranked
        if key in selected
    }
    for required_type in ("body", "segment", "attachment", "calendar", "comparator", "counterevidence"):
        if required_type in support_types_present:
            continue
        for key, result in ranked:
            if key in selected:
                continue
            if _support_type_for_result(result, matched_queries=lane_queries_by_key.get(key, [])) != required_type:
                continue
            selected.append(key)
            support_types_present.add(required_type)
            if len(selected) >= bank_limit:
                break
        if len(selected) >= bank_limit:
            break

    if len(selected) > bank_limit:
        selected = selected[:bank_limit]
    return selected


__all__ = [
    "_bank_entry",
    "_evidence_bank_keys_with_lane_diversity",
    "_evidence_bank_keys_with_support_diversity",
    "_lane_expansion_terms",
    "_lane_recovered_expansion_terms",
    "_record_lane_match",
    "_result_competition_key",
    "_result_competition_score",
    "_result_identity_key",
    "_result_search_surface",
    "_support_type_for_result",
    "_support_type_for_row",
    "_term_tokens",
]
