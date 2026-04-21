"""Compact refreshable case dashboard derived from shared matter registries."""

from __future__ import annotations

from typing import Any

from .comparative_treatment import shared_comparator_points

CASE_DASHBOARD_VERSION = "1"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = _compact(value)
        if text:
            return text
    return ""


def _quoted_text(row: dict[str, Any]) -> str:
    quoted = _as_dict(row.get("quoted_evidence"))
    return _first_nonempty(
        quoted.get("original_text"),
        quoted.get("translated_text"),
        quoted.get("summary"),
    )


def _exhibit_card(row: dict[str, Any]) -> dict[str, Any] | None:
    summary = _first_nonempty(
        row.get("short_description"),
        row.get("why_it_matters"),
        _quoted_text(row),
    )
    strength = str(row.get("strength") or _as_dict(row.get("exhibit_reliability")).get("strength") or "")
    readiness = str(
        row.get("readiness") or _as_dict(_as_dict(row.get("exhibit_reliability")).get("next_step_logic")).get("readiness") or ""
    )
    if not _first_nonempty(summary, strength, row.get("exhibit_id")) or not (summary or strength):
        return None
    card: dict[str, Any] = {
        "exhibit_id": str(row.get("exhibit_id") or ""),
        "source_id": str(row.get("source_id") or ""),
        "summary": summary,
        "strength": strength,
        "source_language": str(row.get("source_language") or ""),
        "source_conflict_status": str(row.get("source_conflict_status") or ""),
        "supporting_source_ids": [str(item) for item in _as_list(row.get("supporting_source_ids")) if item][:3],
        "supporting_uids": [str(item) for item in _as_list(row.get("supporting_uids")) if item][:3],
        "quoted_evidence": dict(row.get("quoted_evidence") or {}),
        "document_locator": dict(row.get("document_locator") or {}),
    }
    if readiness:
        card["readiness"] = readiness
    if int(row.get("priority_score") or 0) > 0:
        card["priority_score"] = int(row.get("priority_score") or 0)
    return card


def _gap_card(item: dict[str, Any]) -> dict[str, Any] | None:
    summary = _first_nonempty(
        item.get("summary"),
        item.get("priority_label"),
        f"{int(item.get('gap_days') or 0)}-day unexplained gap" if int(item.get("gap_days") or 0) > 0 else "",
    )
    if not summary:
        return None
    return {
        "gap_id": str(item.get("gap_id") or ""),
        "summary": summary,
        "gap_days": int(item.get("gap_days") or 0),
        "priority": str(item.get("priority") or ""),
        "missing_bridge_record_suggestions": [
            str(value) for value in _as_list(item.get("missing_bridge_record_suggestions")) if value
        ][:2],
    }


def _process_irregularity_card(item: dict[str, Any]) -> dict[str, Any] | None:
    summary = _first_nonempty(
        item.get("phrase"),
        item.get("signal"),
        item.get("indicator"),
        item.get("summary"),
        item.get("original_statement_or_promise"),
        item.get("later_action"),
    )
    if not summary:
        return None
    return {"summary": summary}


def _insufficiency_card(summary: str, *, reason: str = "") -> dict[str, Any]:
    card = {"status": "insufficient_evidence", "summary": summary}
    if _compact(reason):
        card["reason"] = _compact(reason)
    return card


def build_case_dashboard(
    *,
    case_bundle: dict[str, Any] | None,
    matter_workspace: dict[str, Any] | None,
    matter_evidence_index: dict[str, Any] | None,
    master_chronology: dict[str, Any] | None,
    lawyer_issue_matrix: dict[str, Any] | None,
    actor_map: dict[str, Any] | None,
    comparative_treatment: dict[str, Any] | None,
    case_patterns: dict[str, Any] | None,
    skeptical_employer_review: dict[str, Any] | None,
    document_request_checklist: dict[str, Any] | None,
    promise_contradiction_analysis: dict[str, Any] | None,
    deadline_warnings: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return a compact card-like dashboard that refreshes from shared entities."""
    matter = _as_dict(_as_dict(matter_workspace).get("matter"))
    issue_rows = [row for row in _as_list(_as_dict(lawyer_issue_matrix).get("rows")) if isinstance(row, dict)]
    evidence_rows = [row for row in _as_list(_as_dict(matter_evidence_index).get("rows")) if isinstance(row, dict)]
    top_exhibits = [row for row in _as_list(_as_dict(matter_evidence_index).get("top_15_exhibits")) if isinstance(row, dict)]
    chronology = _as_dict(master_chronology)
    chronology_entries = [row for row in _as_list(chronology.get("entries")) if isinstance(row, dict)]
    chronology_summary = _as_dict(chronology.get("summary"))
    actors = [row for row in _as_list(_as_dict(actor_map).get("actors")) if isinstance(row, dict)]
    comparator_rows = shared_comparator_points(_as_dict(comparative_treatment))
    behavioural_review = _as_dict(_as_dict(case_patterns).get("corpus_behavioral_review"))
    weaknesses = [row for row in _as_list(_as_dict(skeptical_employer_review).get("weaknesses")) if isinstance(row, dict)]
    request_groups = [row for row in _as_list(_as_dict(document_request_checklist).get("groups")) if isinstance(row, dict)]
    timing_warnings = [row for row in _as_list(_as_dict(deadline_warnings).get("warnings")) if isinstance(row, dict)]
    contradiction_rows = [
        row for row in _as_list(_as_dict(promise_contradiction_analysis).get("contradiction_table")) if isinstance(row, dict)
    ]

    if not any((matter, issue_rows, evidence_rows, chronology_entries, actors, weaknesses, request_groups)):
        return None

    scope = _as_dict(_as_dict(case_bundle).get("scope"))
    target_person = _as_dict(scope.get("target_person"))
    issue_cards = [
        {
            "issue_id": str(row.get("issue_id") or ""),
            "title": str(row.get("title") or ""),
            "status": str(row.get("legal_relevance_status") or ""),
            "evidence_hint": _first_nonempty(row.get("relevant_facts"), row.get("missing_proof")),
        }
        for row in issue_rows[:4]
    ]
    date_cards = [
        {
            "chronology_id": str(row.get("chronology_id") or ""),
            "date": str(row.get("date") or ""),
            "title": _first_nonempty(row.get("title"), row.get("description")),
        }
        for row in chronology_entries[:4]
    ]
    exhibit_cards = [
        card
        for row in sorted(
            top_exhibits,
            key=lambda item: (
                -int(item.get("priority_score") or 0),
                0 if str(item.get("source_conflict_status") or "") == "disputed" else 1,
                str(item.get("exhibit_id") or ""),
            ),
        )[:4]
        if isinstance(row, dict)
        for card in [_exhibit_card(row)]
        if card is not None
    ]
    gap_cards = [
        card
        for item in sorted(
            [item for item in _as_list(chronology_summary.get("date_gaps_and_unexplained_sequences")) if isinstance(item, dict)],
            key=lambda row: (
                {"high": 0, "medium": 1, "low": 2}.get(str(row.get("priority") or ""), 3),
                -int(row.get("gap_days") or 0),
                str(row.get("gap_id") or ""),
            ),
        )[:3]
        if isinstance(item, dict)
        for card in [_gap_card(item)]
        if card is not None
    ]
    target_email = _compact(target_person.get("email")).lower()
    target_name = _compact(target_person.get("name")).lower()
    sorted_actors = sorted(
        actors,
        key=lambda row: (
            0 if (_compact(row.get("email")).lower() == target_email or _compact(row.get("name")).lower() == target_name) else 1,
            0 if _as_dict(row.get("status")).get("decision_maker") else 1,
            0 if _as_dict(row.get("status")).get("gatekeeper") else 1,
            -int(row.get("source_record_count") or 0),
            str(row.get("name") or row.get("email") or row.get("actor_id") or ""),
        ),
    )
    actor_cards = [
        {
            "actor_id": str(row.get("actor_id") or ""),
            "name": _first_nonempty(row.get("name"), row.get("email")),
            "status": dict(row.get("status") or {}),
            "impact": str(row.get("helps_hurts_mixed") or ""),
        }
        for row in sorted_actors[:4]
    ]
    comparator_cards = [
        {
            "comparator_point_id": str(row.get("comparator_point_id") or ""),
            "issue_id": str(row.get("issue_id") or ""),
            "strength": str(row.get("comparison_strength") or ""),
            "summary": _first_nonempty(row.get("point_summary"), row.get("issue_label")),
        }
        for row in comparator_rows[:3]
    ]
    raw_comparator_cards = list(comparator_cards)
    if not comparator_cards:
        comparator_summary = _as_dict(_as_dict(comparative_treatment).get("summary"))
        comparator_insufficiency = _as_dict(_as_dict(comparative_treatment).get("insufficiency"))
        comparator_cards = [
            _insufficiency_card(
                _first_nonempty(
                    comparator_summary.get("insufficiency_reason"),
                    comparator_insufficiency.get("reason"),
                    "Comparator analysis is not yet supported on the current record.",
                )
            )
        ]
    process_irregularity_cards = [
        card
        for item in (
            _as_list(behavioural_review.get("procedural_irregularities"))
            + _as_list(behavioural_review.get("coordination_windows"))
            + contradiction_rows
        )[:4]
        if isinstance(item, dict)
        for card in [_process_irregularity_card(item)]
        if card is not None
    ]
    raw_process_irregularity_cards = list(process_irregularity_cards)
    if not process_irregularity_cards:
        process_irregularity_cards = [
            _insufficiency_card(
                "No supported process-irregularity pattern is currently available in the shared behavior review.",
            )
        ]
    drafting_priority_cards = [
        {
            "summary": _first_nonempty(
                row.get("original_statement_or_promise"),
                row.get("later_action"),
            ),
            "confidence": str(row.get("confidence_level") or ""),
        }
        for row in contradiction_rows[:3]
    ]
    raw_drafting_priority_cards = list(drafting_priority_cards)
    if not drafting_priority_cards:
        contradiction_summary = _as_dict(_as_dict(promise_contradiction_analysis).get("summary"))
        drafting_priority_cards = [
            _insufficiency_card(
                _first_nonempty(
                    contradiction_summary.get("insufficiency_reason"),
                    "No contradiction-driven drafting priority is currently available on the shared record.",
                )
            )
        ]
    risk_cards = [
        {
            "weakness_id": str(row.get("weakness_id") or ""),
            "summary": _first_nonempty(row.get("critique"), _as_dict(row.get("repair_guidance")).get("how_to_fix")),
        }
        for row in weaknesses[:4]
    ]
    next_action_cards = [
        {
            "group_id": str(group.get("group_id") or ""),
            "summary": _first_nonempty(
                _as_dict(_as_list(group.get("items"))[0]).get("request") if _as_list(group.get("items")) else "",
                group.get("title"),
            ),
        }
        for group in request_groups[:4]
    ]
    timing_warning_cards = [
        {
            "warning_id": str(item.get("warning_id") or ""),
            "severity": str(item.get("severity") or ""),
            "summary": str(item.get("summary") or ""),
        }
        for item in timing_warnings[:4]
    ]
    if not any(
        (
            issue_cards,
            date_cards,
            exhibit_cards,
            gap_cards,
            actor_cards,
            raw_comparator_cards,
            raw_process_irregularity_cards,
            raw_drafting_priority_cards,
            risk_cards,
            next_action_cards,
            timing_warning_cards,
        )
    ):
        return None

    cards = {
        "main_claims_or_issues": issue_cards,
        "key_dates": date_cards,
        "strongest_exhibits": exhibit_cards,
        "open_evidence_gaps": gap_cards,
        "main_actors": actor_cards,
        "comparator_points": comparator_cards,
        "process_irregularities": process_irregularity_cards,
        "drafting_priorities": drafting_priority_cards,
        "timing_warnings": timing_warning_cards,
        "risks_or_weak_spots": risk_cards,
        "recommended_next_actions": next_action_cards,
    }
    return {
        "version": CASE_DASHBOARD_VERSION,
        "dashboard_format": "refreshable_case_dashboard",
        "matter_ref": {
            "matter_id": str(matter.get("matter_id") or ""),
            "workspace_id": str(_as_dict(matter_workspace).get("workspace_id") or ""),
            "bundle_id": str(matter.get("bundle_id") or _as_dict(case_bundle).get("bundle_id") or ""),
            "case_label": _first_nonempty(matter.get("case_label"), scope.get("case_label")),
        },
        "summary": {
            "card_count": len(cards),
            "issue_count": len(issue_cards),
            "actor_count": len(actor_cards),
            "exhibit_count": len(exhibit_cards),
            "timing_warning_count": len(timing_warning_cards),
            "refreshable_from_shared_entities": True,
        },
        "cards": cards,
    }
