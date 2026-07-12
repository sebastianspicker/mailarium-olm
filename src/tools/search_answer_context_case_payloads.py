"""Case-analysis payload helpers for answer-context rendering."""

from __future__ import annotations

from typing import Any

from src._utils import _as_dict

from ..actor_resolution import resolve_actor_id
from ..message_behavior import normalize_message_findings_payload


def _text(value: Any, default: str = "") -> str:
    return str(value) if value else default


def _strings(values: Any, limit: int | None = None) -> list[str]:
    items = list(values or [])
    return [str(item) for item in (items[:limit] if limit is not None else items) if item]


def _dict_items(values: Any, limit: int | None = None) -> list[dict[str, Any]]:
    items = list(values or [])
    return [dict(item) for item in (items[:limit] if limit is not None else items) if isinstance(item, dict)]


def _annotate_actor(actor: Any, actor_graph: dict[str, Any]) -> None:
    if not isinstance(actor, dict):
        return
    actor_id, resolution = resolve_actor_id(
        actor_graph,
        email=_text(actor.get("email")),
        name=_text(actor.get("name")),
    )
    actor["actor_id"] = actor_id
    actor["actor_resolution"] = resolution


def _apply_actor_ids_to_case_bundle(case_bundle: dict[str, Any], actor_graph: dict[str, Any]) -> None:
    """Annotate case-bundle parties with stable actor ids."""
    scope = case_bundle.get("scope")
    if not isinstance(scope, dict):
        return
    _annotate_actor(scope.get("target_person"), actor_graph)
    for key in ("comparator_actors", "suspected_actors"):
        actors = scope.get(key)
        if isinstance(actors, list):
            for actor in actors:
                _annotate_actor(actor, actor_graph)


def _apply_actor_ids_to_candidates(items: list[dict[str, Any]], actor_graph: dict[str, Any]) -> None:
    """Annotate candidates and speaker hints with stable actor ids."""
    for item in items:
        actor_id, resolution = resolve_actor_id(
            actor_graph,
            email=str(item.get("sender_email") or ""),
            name=str(item.get("sender_name") or ""),
        )
        item["sender_actor_id"] = actor_id
        item["sender_actor_resolution"] = resolution
        speaker_attribution = item.get("speaker_attribution")
        if not isinstance(speaker_attribution, dict):
            continue
        authored_speaker = speaker_attribution.get("authored_speaker")
        if isinstance(authored_speaker, dict):
            authored_actor_id, authored_resolution = resolve_actor_id(
                actor_graph,
                email=str(authored_speaker.get("email") or ""),
                name=str(authored_speaker.get("name") or ""),
            )
            authored_speaker["actor_id"] = authored_actor_id
            authored_speaker["actor_resolution"] = authored_resolution
        quoted_blocks = speaker_attribution.get("quoted_blocks")
        if isinstance(quoted_blocks, list):
            for block in quoted_blocks:
                if not isinstance(block, dict):
                    continue
                quoted_actor_id, quoted_resolution = resolve_actor_id(
                    actor_graph,
                    email=str(block.get("speaker_email") or ""),
                )
                block["actor_id"] = quoted_actor_id
                block["actor_resolution"] = quoted_resolution


def _quote_attribution_counts(candidates: list[dict[str, Any]]) -> tuple[Any, Any]:
    """Count quote-attribution statuses and sources in candidate speaker metadata."""
    from collections import Counter

    status_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    for candidate in candidates:
        speaker_attribution = candidate.get("speaker_attribution")
        if not isinstance(speaker_attribution, dict):
            continue
        for block in _dict_items(speaker_attribution.get("quoted_blocks")):
            status_counts[_text(block.get("quote_attribution_status"), "unresolved")] += 1
            source_counts[_text(block.get("source"), "unresolved")] += 1
    return status_counts, source_counts


def _quote_finding_counts(candidates: list[dict[str, Any]]) -> tuple[int, int]:
    """Count total and ambiguity-downgraded quoted behaviour candidates."""
    quote_finding_count = 0
    downgraded_quote_finding_count = 0
    for candidate in candidates:
        message_findings = candidate.get("message_findings")
        if not isinstance(message_findings, dict):
            continue
        for block in _dict_items(message_findings.get("quoted_blocks")):
            findings = _as_dict(block.get("findings"))
            behavior_count = len(list(findings.get("behavior_candidates") or []))
            quote_finding_count += behavior_count
            if bool(block.get("downgraded_due_to_quote_ambiguity", True)):
                downgraded_quote_finding_count += behavior_count
    return quote_finding_count, downgraded_quote_finding_count


def _quote_attribution_metrics(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Return case-scoped quote-attribution quality metrics for BA14 analysis."""
    status_counts, source_counts = _quote_attribution_counts(candidates)
    quote_finding_count, downgraded_quote_finding_count = _quote_finding_counts(candidates)
    quoted_block_count = sum(status_counts.values())
    resolved_block_count = quoted_block_count - int(status_counts.get("unresolved", 0))
    return {
        "version": "1",
        "quoted_block_count": quoted_block_count,
        "resolved_block_count": resolved_block_count,
        "unresolved_block_count": int(status_counts.get("unresolved", 0)),
        "status_counts": dict(sorted(status_counts.items())),
        "source_counts": dict(sorted(source_counts.items())),
        "quote_finding_count": quote_finding_count,
        "downgraded_quote_finding_count": downgraded_quote_finding_count,
        "summary": {
            "authored_text_and_quoted_history_separated": True,
            "inferred_quote_cues_separated": True,
        },
    }


def _compact_signal(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "signal_id": _text(item.get("signal_id")),
        "label": _text(item.get("label")),
        "confidence": _text(item.get("confidence")),
    }


def _compact_rhetoric_analysis(value: Any, default_scope: str) -> dict[str, Any]:
    analysis = _as_dict(value)
    return {
        "text_scope": _text(analysis.get("text_scope"), default_scope),
        "signal_count": int(analysis.get("signal_count") or 0),
        "signals": [_compact_signal(item) for item in _dict_items(analysis.get("signals"), 3)],
    }


def _compact_rhetoric_block(block: dict[str, Any]) -> dict[str, Any]:
    return {
        "segment_ordinal": int(block.get("segment_ordinal") or 0),
        "segment_type": _text(block.get("segment_type")),
        "speaker_email": _text(block.get("speaker_email")),
        "quote_attribution_status": _text(block.get("quote_attribution_status")),
        "analysis": _compact_rhetoric_analysis(block.get("analysis"), "quoted_text"),
    }


def _compact_language_rhetoric_payload(language_rhetoric: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact language-rhetoric payload for budget-sensitive paths."""
    rhetoric = _as_dict(language_rhetoric)
    authored = _compact_rhetoric_analysis(rhetoric.get("authored_text"), "authored_text")
    authored["signals"] = [
        _compact_signal(item) for item in _dict_items(_as_dict(rhetoric.get("authored_text")).get("signals"), 5)
    ]
    return {
        "version": _text(rhetoric.get("version")),
        "authored_text": authored,
        "quoted_blocks": [_compact_rhetoric_block(item) for item in _dict_items(rhetoric.get("quoted_blocks"), 3)],
    }


def _compact_behavior(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "behavior_id": _text(item.get("behavior_id")),
        "label": _text(item.get("label")),
        "confidence": _text(item.get("confidence")),
    }


def _compact_relevant_wording(item: dict[str, Any]) -> dict[str, Any]:
    return {"text": _text(item.get("text")), "basis_id": _text(item.get("basis_id"))}


def _compact_process_signal(item: dict[str, Any]) -> dict[str, Any]:
    return {"signal": _text(item.get("signal")), "summary": _text(item.get("summary"))}


def _compact_authored_findings(authored: dict[str, Any]) -> dict[str, Any]:
    return {
        "text_scope": _text(authored.get("text_scope"), "authored_text"),
        "behavior_candidate_count": int(authored.get("behavior_candidate_count") or 0),
        "behavior_candidates": [_compact_behavior(item) for item in _dict_items(authored.get("behavior_candidates"), 5)],
        "wording_only_signal_ids": _strings(authored.get("wording_only_signal_ids"), 5),
        "counter_indicators": _strings(authored.get("counter_indicators"), 3),
        "tone_summary": _text(authored.get("tone_summary")),
        "relevant_wording": [_compact_relevant_wording(item) for item in _dict_items(authored.get("relevant_wording"), 4)],
        "omissions_or_process_signals": [
            _compact_process_signal(item) for item in _dict_items(authored.get("omissions_or_process_signals"), 4)
        ],
        "included_actors": _strings(authored.get("included_actors"), 4),
        "excluded_actors": _strings(authored.get("excluded_actors"), 3),
        "communication_classification": dict(authored.get("communication_classification") or {}),
    }


def _compact_message_quote(block: dict[str, Any]) -> dict[str, Any]:
    findings = _as_dict(block.get("findings"))
    return {
        "segment_ordinal": int(block.get("segment_ordinal") or 0),
        "segment_type": _text(block.get("segment_type")),
        "speaker_email": _text(block.get("speaker_email")),
        "quote_attribution_status": _text(block.get("quote_attribution_status")),
        "findings": {
            "behavior_candidate_count": int(findings.get("behavior_candidate_count") or 0),
            "behavior_candidates": [_compact_behavior(item) for item in _dict_items(findings.get("behavior_candidates"), 3)],
        },
    }


def _compact_message_findings_payload(message_findings: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact message-findings payload for budget-sensitive paths."""
    findings = normalize_message_findings_payload(message_findings)
    return {
        "version": _text(findings.get("version")),
        "authored_text": _compact_authored_findings(_as_dict(findings.get("authored_text"))),
        "quoted_blocks": [_compact_message_quote(item) for item in _dict_items(findings.get("quoted_blocks"), 3)],
        "summary": dict(findings.get("summary") or {}),
    }


def _project_record(
    item: dict[str, Any],
    *,
    text_fields: tuple[str, ...] = (),
    int_fields: tuple[str, ...] = (),
    dict_fields: tuple[str, ...] = (),
    list_fields: dict[str, int] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {key: _text(item.get(key)) for key in text_fields}
    payload.update({key: int(item.get(key) or 0) for key in int_fields})
    payload.update({key: dict(item.get(key) or {}) for key in dict_fields})
    for key, limit in (list_fields or {}).items():
        payload[key] = _strings(item.get(key), limit)
    return payload


def _project_records(values: Any, limit: int, **kwargs: Any) -> list[dict[str, Any]]:
    return [_project_record(item, **kwargs) for item in _dict_items(values, limit)]


def _compact_corpus_review(review: dict[str, Any]) -> dict[str, Any]:
    return {
        **_project_record(
            review,
            text_fields=("coverage_scope", "scope_note"),
            int_fields=("message_count_reviewed",),
            dict_fields=("communication_class_counts",),
        ),
        "recurring_phrases": _project_records(
            review.get("recurring_phrases"),
            3,
            text_fields=("phrase",),
            int_fields=("message_count",),
            list_fields={"message_uids": 3},
        ),
        "escalation_points": _project_records(
            review.get("escalation_points"), 3, text_fields=("uid", "date", "strength"), list_fields={"triggers": 3}
        ),
        "double_standards": _project_records(
            review.get("double_standards"),
            3,
            text_fields=("sender_actor_id",),
            list_fields={"target_message_uids": 3, "comparator_message_uids": 3},
        ),
        "procedural_irregularities": _project_records(
            review.get("procedural_irregularities"), 3, text_fields=("uid",), list_fields={"irregularity_types": 3}
        ),
        "response_timing_shifts": _project_records(
            review.get("response_timing_shifts"), 3, text_fields=("from_uid", "to_uid", "shift_label")
        ),
        "cc_behavior_changes": _project_records(
            review.get("cc_behavior_changes"),
            3,
            text_fields=("sender_actor_id", "from_uid", "to_uid"),
            list_fields={"change_types": 3},
        ),
        "coordination_windows": _project_records(
            review.get("coordination_windows"),
            3,
            text_fields=("window_start", "window_end"),
            list_fields={"actor_ids": 3, "message_uids": 4},
        ),
    }


def _compact_case_patterns_payload(case_patterns: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact case-pattern payload for budget-sensitive paths."""
    patterns = _as_dict(case_patterns)
    corpus_review = _as_dict(patterns.get("corpus_behavioral_review"))
    return {
        "version": _text(patterns.get("version")),
        "summary": dict(patterns.get("summary") or {}),
        "behavior_patterns": _project_records(
            patterns.get("behavior_patterns"),
            4,
            text_fields=("cluster_id", "key", "primary_recurrence"),
            int_fields=("message_count",),
            list_fields={"recurrence_flags": 3, "message_uids": 3},
        ),
        "directional_summaries": _project_records(
            patterns.get("directional_summaries"),
            3,
            text_fields=("sender_actor_id", "target_actor_id"),
            int_fields=("message_count",),
            dict_fields=("behavior_counts",),
        ),
        "corpus_behavioral_review": _compact_corpus_review(corpus_review),
    }


def _compact_comparative_treatment_payload(comparative_treatment: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact comparative-treatment payload for budget-sensitive paths."""
    analysis = _as_dict(comparative_treatment)
    return {
        "version": _text(analysis.get("version")),
        "target_actor_id": _text(analysis.get("target_actor_id")),
        "comparator_count": int(analysis.get("comparator_count") or 0),
        "summary": dict(analysis.get("summary") or {}),
        "comparator_summaries": [
            _compact_comparator_summary(item) for item in _dict_items(analysis.get("comparator_summaries"), 3)
        ],
    }


def _compact_comparator_matrix_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **_project_record(
            row,
            text_fields=(
                "matrix_row_id",
                "issue_id",
                "issue_label",
                "comparison_strength",
                "claimant_treatment",
                "comparator_treatment",
                "likely_significance",
            ),
            list_fields={"evidence": 3},
        ),
    }


def _compact_comparator_matrix(value: Any) -> dict[str, Any]:
    matrix = _as_dict(value)
    return {
        "row_count": int(matrix.get("row_count") or 0),
        "rows": [_compact_comparator_matrix_row(row) for row in _dict_items(matrix.get("rows"), 3)],
    }


def _compact_comparator_summary(item: dict[str, Any]) -> dict[str, Any]:
    evidence_chain = _as_dict(item.get("evidence_chain"))
    return {
        **_project_record(
            item,
            text_fields=(
                "comparator_actor_id",
                "comparator_email",
                "sender_actor_id",
                "status",
                "comparison_quality",
                "comparison_quality_label",
            ),
            list_fields={"unequal_treatment_signals": 5},
        ),
        "supports_discrimination_concern": bool(item.get("supports_discrimination_concern")),
        "evidence_chain": {
            "target_uids": _strings(evidence_chain.get("target_uids"), 3),
            "comparator_uids": _strings(evidence_chain.get("comparator_uids"), 3),
        },
        "comparator_matrix": _compact_comparator_matrix(item.get("comparator_matrix")),
    }


def _compact_case_party_payload(party: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact case-party payload while preserving stable actor references."""
    item = _as_dict(party)
    return {
        "name": str(item.get("name") or ""),
        "email": str(item.get("email") or ""),
        "role_hint": str(item.get("role_hint") or ""),
        "actor_id": str(item.get("actor_id") or ""),
    }


def _compact_institutional_actor_payload(actor: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact institutional-actor payload for budget-sensitive paths."""
    item = _as_dict(actor)
    return {
        "label": str(item.get("label") or ""),
        "actor_type": str(item.get("actor_type") or ""),
        "email": str(item.get("email") or ""),
        "function": str(item.get("function") or ""),
    }


def _compact_case_bundle_payload(case_bundle: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact case-bundle payload for budget-sensitive paths."""
    bundle = _as_dict(case_bundle)
    return {"bundle_id": _text(bundle.get("bundle_id")), "scope": _compact_case_scope(_as_dict(bundle.get("scope")))}


def _compact_case_parties(scope: dict[str, Any], key: str, limit: int) -> list[dict[str, Any]]:
    return [_compact_case_party_payload(item) for item in _dict_items(scope.get(key), limit)]


def _compact_case_scope(scope: dict[str, Any]) -> dict[str, Any]:
    return {
        **_project_record(scope, text_fields=("case_label", "analysis_goal", "date_from", "date_to")),
        "allegation_focus": _strings(scope.get("allegation_focus")),
        "target_person": _compact_case_party_payload(scope.get("target_person")),
        "suspected_actors": _compact_case_parties(scope, "suspected_actors", 3),
        "comparator_actors": _compact_case_parties(scope, "comparator_actors", 3),
        "context_people": _compact_case_parties(scope, "context_people", 4),
        "institutional_actors": [
            _compact_institutional_actor_payload(item) for item in _dict_items(scope.get("institutional_actors"), 6)
        ],
        "witnesses": _compact_case_parties(scope, "witnesses", 3),
        "trigger_events": _dict_items(scope.get("trigger_events"), 3),
        "employment_issue_tracks": _strings(scope.get("employment_issue_tracks")),
        "employment_issue_tags": _strings(scope.get("employment_issue_tags")),
    }


def _compact_actor_identity_graph_payload(actor_graph: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact actor-graph payload for budget-sensitive paths."""
    graph = _as_dict(actor_graph)
    return {
        "actors": [_compact_graph_actor(actor) for actor in _dict_items(graph.get("actors"), 6)],
        "unresolved_references": _dict_items(graph.get("unresolved_references")),
        "stats": dict(graph.get("stats") or {}),
    }


def _compact_graph_actor(actor: dict[str, Any]) -> dict[str, Any]:
    role_context = _as_dict(actor.get("role_context"))
    return {
        **_project_record(actor, text_fields=("actor_id", "primary_email", "primary_name")),
        "role_context": {"supplied_role_facts": _dict_items(role_context.get("supplied_role_facts"), 1)},
    }
