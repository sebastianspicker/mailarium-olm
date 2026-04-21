"""Case-analysis payload helpers for answer-context rendering."""

from __future__ import annotations

from typing import Any

from ..actor_resolution import resolve_actor_id
from ..message_behavior import normalize_message_findings_payload
from .search_answer_context_evidence import _as_dict, _as_list


def _apply_actor_ids_to_case_bundle(case_bundle: dict[str, Any], actor_graph: dict[str, Any]) -> None:
    """Annotate case-bundle parties with stable actor ids."""
    scope = case_bundle.get("scope")
    if not isinstance(scope, dict):
        return
    target_person = scope.get("target_person")
    if isinstance(target_person, dict):
        actor_id, resolution = resolve_actor_id(
            actor_graph,
            email=str(target_person.get("email") or ""),
            name=str(target_person.get("name") or ""),
        )
        target_person["actor_id"] = actor_id
        target_person["actor_resolution"] = resolution
    comparator_actors = scope.get("comparator_actors")
    if isinstance(comparator_actors, list):
        for actor in comparator_actors:
            if not isinstance(actor, dict):
                continue
            actor_id, resolution = resolve_actor_id(
                actor_graph,
                email=str(actor.get("email") or ""),
                name=str(actor.get("name") or ""),
            )
            actor["actor_id"] = actor_id
            actor["actor_resolution"] = resolution
    suspected_actors = scope.get("suspected_actors")
    if isinstance(suspected_actors, list):
        for actor in suspected_actors:
            if not isinstance(actor, dict):
                continue
            actor_id, resolution = resolve_actor_id(
                actor_graph,
                email=str(actor.get("email") or ""),
                name=str(actor.get("name") or ""),
            )
            actor["actor_id"] = actor_id
            actor["actor_resolution"] = resolution


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


def _quote_attribution_metrics(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Return case-scoped quote-attribution quality metrics for BA14 analysis."""
    from collections import Counter

    status_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    quote_finding_count = 0
    downgraded_quote_finding_count = 0
    for candidate in candidates:
        speaker_attribution = candidate.get("speaker_attribution")
        if isinstance(speaker_attribution, dict):
            for block in speaker_attribution.get("quoted_blocks", []) or []:
                if not isinstance(block, dict):
                    continue
                status_counts[str(block.get("quote_attribution_status") or "unresolved")] += 1
                source_counts[str(block.get("source") or "unresolved")] += 1
        message_findings = candidate.get("message_findings")
        if not isinstance(message_findings, dict):
            continue
        for block in message_findings.get("quoted_blocks", []) or []:
            if not isinstance(block, dict):
                continue
            findings = block.get("findings")
            if not isinstance(findings, dict):
                continue
            behavior_count = len(list(findings.get("behavior_candidates") or []))
            quote_finding_count += behavior_count
            if bool(block.get("downgraded_due_to_quote_ambiguity", True)):
                downgraded_quote_finding_count += behavior_count

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


def _compact_language_rhetoric_payload(language_rhetoric: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact language-rhetoric payload for budget-sensitive paths."""
    rhetoric = language_rhetoric if isinstance(language_rhetoric, dict) else {}
    authored = _as_dict(rhetoric.get("authored_text"))
    quoted_blocks = _as_list(rhetoric.get("quoted_blocks"))
    return {
        "version": str(rhetoric.get("version") or ""),
        "authored_text": {
            "text_scope": str(authored.get("text_scope") or "authored_text"),
            "signal_count": int(authored.get("signal_count") or 0),
            "signals": [
                {
                    "signal_id": str(signal.get("signal_id") or ""),
                    "label": str(signal.get("label") or ""),
                    "confidence": str(signal.get("confidence") or ""),
                }
                for signal in list(authored.get("signals") or [])[:5]
                if isinstance(signal, dict)
            ],
        },
        "quoted_blocks": [
            {
                "segment_ordinal": int(block.get("segment_ordinal") or 0),
                "segment_type": str(block.get("segment_type") or ""),
                "speaker_email": str(block.get("speaker_email") or ""),
                "quote_attribution_status": str(block.get("quote_attribution_status") or ""),
                "analysis": {
                    "text_scope": str(
                        ((block.get("analysis") or {}).get("text_scope") if isinstance(block.get("analysis"), dict) else "")
                        or "quoted_text"
                    ),
                    "signal_count": int(
                        ((block.get("analysis") or {}).get("signal_count") if isinstance(block.get("analysis"), dict) else 0) or 0
                    ),
                    "signals": [
                        {
                            "signal_id": str(signal.get("signal_id") or ""),
                            "label": str(signal.get("label") or ""),
                            "confidence": str(signal.get("confidence") or ""),
                        }
                        for signal in list(
                            (((block.get("analysis") or {}).get("signals")) if isinstance(block.get("analysis"), dict) else [])
                            or []
                        )[:3]
                        if isinstance(signal, dict)
                    ],
                },
            }
            for block in quoted_blocks[:3]
            if isinstance(block, dict)
        ],
    }


def _compact_message_findings_payload(message_findings: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact message-findings payload for budget-sensitive paths."""
    findings = normalize_message_findings_payload(message_findings)
    authored = _as_dict(findings.get("authored_text"))
    quoted_blocks = _as_list(findings.get("quoted_blocks"))
    compact_authored = {
        "text_scope": str(authored.get("text_scope") or "authored_text"),
        "behavior_candidate_count": int(authored.get("behavior_candidate_count") or 0),
        "behavior_candidates": [
            {
                "behavior_id": str(item.get("behavior_id") or ""),
                "label": str(item.get("label") or ""),
                "confidence": str(item.get("confidence") or ""),
            }
            for item in list(authored.get("behavior_candidates") or [])[:5]
            if isinstance(item, dict)
        ],
        "wording_only_signal_ids": [str(item) for item in list(authored.get("wording_only_signal_ids") or [])[:5] if item],
        "counter_indicators": [str(item) for item in list(authored.get("counter_indicators") or [])[:3] if item],
        "tone_summary": str(authored.get("tone_summary") or ""),
        "relevant_wording": [
            {
                "text": str(item.get("text") or ""),
                "basis_id": str(item.get("basis_id") or ""),
            }
            for item in list(authored.get("relevant_wording") or [])[:4]
            if isinstance(item, dict)
        ],
        "omissions_or_process_signals": [
            {
                "signal": str(item.get("signal") or ""),
                "summary": str(item.get("summary") or ""),
            }
            for item in list(authored.get("omissions_or_process_signals") or [])[:4]
            if isinstance(item, dict)
        ],
        "included_actors": [str(item) for item in list(authored.get("included_actors") or [])[:4] if item],
        "excluded_actors": [str(item) for item in list(authored.get("excluded_actors") or [])[:3] if item],
        "communication_classification": dict(authored.get("communication_classification") or {}),
    }
    return {
        "version": str(findings.get("version") or ""),
        "authored_text": compact_authored,
        "quoted_blocks": [
            {
                "segment_ordinal": int(block.get("segment_ordinal") or 0),
                "segment_type": str(block.get("segment_type") or ""),
                "speaker_email": str(block.get("speaker_email") or ""),
                "quote_attribution_status": str(block.get("quote_attribution_status") or ""),
                "findings": {
                    "behavior_candidate_count": int(
                        (
                            ((block.get("findings") or {}).get("behavior_candidate_count"))
                            if isinstance(block.get("findings"), dict)
                            else 0
                        )
                        or 0,
                    ),
                    "behavior_candidates": [
                        {
                            "behavior_id": str(item.get("behavior_id") or ""),
                            "label": str(item.get("label") or ""),
                            "confidence": str(item.get("confidence") or ""),
                        }
                        for item in list(
                            (
                                ((block.get("findings") or {}).get("behavior_candidates"))
                                if isinstance(block.get("findings"), dict)
                                else []
                            )
                            or []
                        )[:3]
                        if isinstance(item, dict)
                    ],
                },
            }
            for block in quoted_blocks[:3]
            if isinstance(block, dict)
        ],
        "summary": dict(findings.get("summary") or {}),
    }


def _compact_case_patterns_payload(case_patterns: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact case-pattern payload for budget-sensitive paths."""
    patterns = case_patterns if isinstance(case_patterns, dict) else {}
    corpus_review = _as_dict(patterns.get("corpus_behavioral_review"))
    return {
        "version": str(patterns.get("version") or ""),
        "summary": dict(patterns.get("summary") or {}),
        "behavior_patterns": [
            {
                "cluster_id": str(item.get("cluster_id") or ""),
                "key": str(item.get("key") or ""),
                "message_count": int(item.get("message_count") or 0),
                "primary_recurrence": str(item.get("primary_recurrence") or ""),
                "recurrence_flags": [str(flag) for flag in list(item.get("recurrence_flags") or [])[:3] if flag],
                "message_uids": [str(uid) for uid in list(item.get("message_uids") or [])[:3] if uid],
            }
            for item in list(patterns.get("behavior_patterns") or [])[:4]
            if isinstance(item, dict)
        ],
        "directional_summaries": [
            {
                "sender_actor_id": str(item.get("sender_actor_id") or ""),
                "target_actor_id": str(item.get("target_actor_id") or ""),
                "message_count": int(item.get("message_count") or 0),
                "behavior_counts": dict(item.get("behavior_counts") or {}),
            }
            for item in list(patterns.get("directional_summaries") or [])[:3]
            if isinstance(item, dict)
        ],
        "corpus_behavioral_review": {
            "coverage_scope": str(corpus_review.get("coverage_scope") or ""),
            "scope_note": str(corpus_review.get("scope_note") or ""),
            "message_count_reviewed": int(corpus_review.get("message_count_reviewed") or 0),
            "communication_class_counts": dict(corpus_review.get("communication_class_counts") or {}),
            "recurring_phrases": [
                {
                    "phrase": str(item.get("phrase") or ""),
                    "message_count": int(item.get("message_count") or 0),
                    "message_uids": [str(uid) for uid in list(item.get("message_uids") or [])[:3] if uid],
                }
                for item in list(corpus_review.get("recurring_phrases") or [])[:3]
                if isinstance(item, dict)
            ],
            "escalation_points": [
                {
                    "uid": str(item.get("uid") or ""),
                    "date": str(item.get("date") or ""),
                    "strength": str(item.get("strength") or ""),
                    "triggers": [str(trigger) for trigger in list(item.get("triggers") or [])[:3] if trigger],
                }
                for item in list(corpus_review.get("escalation_points") or [])[:3]
                if isinstance(item, dict)
            ],
            "double_standards": [
                {
                    "sender_actor_id": str(item.get("sender_actor_id") or ""),
                    "target_message_uids": [str(uid) for uid in list(item.get("target_message_uids") or [])[:3] if uid],
                    "comparator_message_uids": [str(uid) for uid in list(item.get("comparator_message_uids") or [])[:3] if uid],
                }
                for item in list(corpus_review.get("double_standards") or [])[:3]
                if isinstance(item, dict)
            ],
            "procedural_irregularities": [
                {
                    "uid": str(item.get("uid") or ""),
                    "irregularity_types": [str(signal) for signal in list(item.get("irregularity_types") or [])[:3] if signal],
                }
                for item in list(corpus_review.get("procedural_irregularities") or [])[:3]
                if isinstance(item, dict)
            ],
            "response_timing_shifts": [
                {
                    "from_uid": str(item.get("from_uid") or ""),
                    "to_uid": str(item.get("to_uid") or ""),
                    "shift_label": str(item.get("shift_label") or ""),
                }
                for item in list(corpus_review.get("response_timing_shifts") or [])[:3]
                if isinstance(item, dict)
            ],
            "cc_behavior_changes": [
                {
                    "sender_actor_id": str(item.get("sender_actor_id") or ""),
                    "from_uid": str(item.get("from_uid") or ""),
                    "to_uid": str(item.get("to_uid") or ""),
                    "change_types": [str(change) for change in list(item.get("change_types") or [])[:3] if change],
                }
                for item in list(corpus_review.get("cc_behavior_changes") or [])[:3]
                if isinstance(item, dict)
            ],
            "coordination_windows": [
                {
                    "window_start": str(item.get("window_start") or ""),
                    "window_end": str(item.get("window_end") or ""),
                    "actor_ids": [str(actor) for actor in list(item.get("actor_ids") or [])[:3] if actor],
                    "message_uids": [str(uid) for uid in list(item.get("message_uids") or [])[:4] if uid],
                }
                for item in list(corpus_review.get("coordination_windows") or [])[:3]
                if isinstance(item, dict)
            ],
        },
    }


def _compact_comparative_treatment_payload(comparative_treatment: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact comparative-treatment payload for budget-sensitive paths."""
    analysis = comparative_treatment if isinstance(comparative_treatment, dict) else {}
    return {
        "version": str(analysis.get("version") or ""),
        "target_actor_id": str(analysis.get("target_actor_id") or ""),
        "comparator_count": int(analysis.get("comparator_count") or 0),
        "summary": dict(analysis.get("summary") or {}),
        "comparator_summaries": [
            {
                "comparator_actor_id": str(item.get("comparator_actor_id") or ""),
                "comparator_email": str(item.get("comparator_email") or ""),
                "sender_actor_id": str(item.get("sender_actor_id") or ""),
                "status": str(item.get("status") or ""),
                "comparison_quality": str(item.get("comparison_quality") or ""),
                "comparison_quality_label": str(item.get("comparison_quality_label") or ""),
                "unequal_treatment_signals": [
                    str(signal) for signal in list(item.get("unequal_treatment_signals") or [])[:5] if signal
                ],
                "supports_discrimination_concern": bool(item.get("supports_discrimination_concern")),
                "evidence_chain": {
                    "target_uids": [
                        str(uid) for uid in list((item.get("evidence_chain") or {}).get("target_uids") or [])[:3] if uid
                    ],
                    "comparator_uids": [
                        str(uid) for uid in list((item.get("evidence_chain") or {}).get("comparator_uids") or [])[:3] if uid
                    ],
                },
                "comparator_matrix": {
                    "row_count": int(((item.get("comparator_matrix") or {}).get("row_count")) or 0),
                    "rows": [
                        {
                            "matrix_row_id": str(row.get("matrix_row_id") or ""),
                            "issue_id": str(row.get("issue_id") or ""),
                            "issue_label": str(row.get("issue_label") or ""),
                            "comparison_strength": str(row.get("comparison_strength") or ""),
                            "claimant_treatment": str(row.get("claimant_treatment") or ""),
                            "comparator_treatment": str(row.get("comparator_treatment") or ""),
                            "evidence": [str(uid) for uid in list(row.get("evidence") or [])[:3] if uid],
                            "likely_significance": str(row.get("likely_significance") or ""),
                        }
                        for row in list((item.get("comparator_matrix") or {}).get("rows") or [])[:3]
                        if isinstance(row, dict)
                    ],
                },
            }
            for item in list(analysis.get("comparator_summaries") or [])[:3]
            if isinstance(item, dict)
        ],
    }


def _compact_case_party_payload(party: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact case-party payload while preserving stable actor references."""
    item = party if isinstance(party, dict) else {}
    return {
        "name": str(item.get("name") or ""),
        "email": str(item.get("email") or ""),
        "role_hint": str(item.get("role_hint") or ""),
        "actor_id": str(item.get("actor_id") or ""),
    }


def _compact_institutional_actor_payload(actor: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact institutional-actor payload for budget-sensitive paths."""
    item = actor if isinstance(actor, dict) else {}
    return {
        "label": str(item.get("label") or ""),
        "actor_type": str(item.get("actor_type") or ""),
        "email": str(item.get("email") or ""),
        "function": str(item.get("function") or ""),
    }


def _compact_case_bundle_payload(case_bundle: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact case-bundle payload for budget-sensitive paths."""
    bundle = case_bundle if isinstance(case_bundle, dict) else {}
    scope = _as_dict(bundle.get("scope"))
    return {
        "bundle_id": str(bundle.get("bundle_id") or ""),
        "scope": {
            "case_label": str(scope.get("case_label") or ""),
            "analysis_goal": str(scope.get("analysis_goal") or ""),
            "allegation_focus": [str(item) for item in list(scope.get("allegation_focus") or []) if item],
            "date_from": str(scope.get("date_from") or ""),
            "date_to": str(scope.get("date_to") or ""),
            "target_person": _compact_case_party_payload(scope.get("target_person") if isinstance(scope, dict) else {}),
            "suspected_actors": [
                _compact_case_party_payload(item)
                for item in list(scope.get("suspected_actors") or [])[:3]
                if isinstance(item, dict)
            ],
            "comparator_actors": [
                _compact_case_party_payload(item)
                for item in list(scope.get("comparator_actors") or [])[:3]
                if isinstance(item, dict)
            ],
            "context_people": [
                _compact_case_party_payload(item)
                for item in list(scope.get("context_people") or [])[:4]
                if isinstance(item, dict)
            ],
            "institutional_actors": [
                _compact_institutional_actor_payload(item)
                for item in list(scope.get("institutional_actors") or [])[:6]
                if isinstance(item, dict)
            ],
            "witnesses": [
                _compact_case_party_payload(item) for item in list(scope.get("witnesses") or [])[:3] if isinstance(item, dict)
            ],
            "trigger_events": [dict(item) for item in list(scope.get("trigger_events") or [])[:3] if isinstance(item, dict)],
            "employment_issue_tracks": [str(item) for item in list(scope.get("employment_issue_tracks") or []) if item],
            "employment_issue_tags": [str(item) for item in list(scope.get("employment_issue_tags") or []) if item],
        },
    }


def _compact_actor_identity_graph_payload(actor_graph: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact actor-graph payload for budget-sensitive paths."""
    graph = actor_graph if isinstance(actor_graph, dict) else {}
    return {
        "actors": [
            {
                "actor_id": str(actor.get("actor_id") or ""),
                "primary_email": str(actor.get("primary_email") or ""),
                "primary_name": str(actor.get("primary_name") or ""),
                "role_context": {
                    "supplied_role_facts": [
                        dict(item)
                        for item in list((actor.get("role_context") or {}).get("supplied_role_facts") or [])[:1]
                        if isinstance(item, dict)
                    ],
                },
            }
            for actor in list(graph.get("actors") or [])[:6]
            if isinstance(actor, dict)
        ],
        "unresolved_references": [
            dict(item) for item in list(graph.get("unresolved_references") or []) if isinstance(item, dict)
        ],
        "stats": dict(graph.get("stats") or {}),
    }
