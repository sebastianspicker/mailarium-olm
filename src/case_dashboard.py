"""Compact refreshable case dashboard derived from shared matter registries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._utils import _as_dict, _as_list, _compact, _first_nonempty
from .comparative_treatment import shared_comparator_points

CASE_DASHBOARD_VERSION = "1"


@dataclass(slots=True)
class _DashboardContext:
    case_bundle: dict[str, Any]
    workspace: dict[str, Any]
    evidence: dict[str, Any]
    chronology: dict[str, Any]
    issues: dict[str, Any]
    actors: dict[str, Any]
    comparison: dict[str, Any]
    patterns: dict[str, Any]
    review: dict[str, Any]
    checklist: dict[str, Any]
    contradictions: dict[str, Any]
    deadlines: dict[str, Any]


def _quoted_text(row: dict[str, Any]) -> str:
    quoted = _as_dict(row.get("quoted_evidence"))
    return _first_nonempty(quoted.get("original_text"), quoted.get("translated_text"), quoted.get("summary"))


def _exhibit_card(row: dict[str, Any]) -> dict[str, Any] | None:
    summary = _first_nonempty(row.get("short_description"), row.get("why_it_matters"), _quoted_text(row))
    reliability = _as_dict(row.get("exhibit_reliability"))
    strength = str(row.get("strength") or reliability.get("strength") or "")
    readiness = str(row.get("readiness") or _as_dict(reliability.get("next_step_logic")).get("readiness") or "")
    if not _first_nonempty(summary, strength, row.get("exhibit_id")) or not (summary or strength):
        return None
    card = _exhibit_card_fields(row, summary, strength)
    if readiness:
        card["readiness"] = readiness
    priority = int(row.get("priority_score") or 0)
    if priority > 0:
        card["priority_score"] = priority
    return card


def _exhibit_card_fields(row: dict[str, Any], summary: str, strength: str) -> dict[str, Any]:
    return {
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


def _gap_card(item: dict[str, Any]) -> dict[str, Any] | None:
    days = int(item.get("gap_days") or 0)
    summary = _first_nonempty(item.get("summary"), item.get("priority_label"), f"{days}-day unexplained gap" if days > 0 else "")
    if not summary:
        return None
    return {
        "gap_id": str(item.get("gap_id") or ""),
        "summary": summary,
        "gap_days": days,
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
    return {"summary": summary} if summary else None


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
    context = _DashboardContext(
        *(
            _as_dict(value)
            for value in (
                case_bundle,
                matter_workspace,
                matter_evidence_index,
                master_chronology,
                lawyer_issue_matrix,
                actor_map,
                comparative_treatment,
                case_patterns,
                skeptical_employer_review,
                document_request_checklist,
                promise_contradiction_analysis,
                deadline_warnings,
            )
        )
    )
    if not _has_dashboard_sources(context):
        return None
    cards, substantive = _dashboard_cards(context)
    if not any(substantive):
        return None
    return _dashboard_payload(context, cards)


def _rows(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    return [row for row in _as_list(payload.get(key)) if isinstance(row, dict)]


def _has_dashboard_sources(context: _DashboardContext) -> bool:
    sources = (
        _as_dict(context.workspace.get("matter")),
        _rows(context.issues, "rows"),
        _rows(context.evidence, "rows"),
        _rows(context.chronology, "entries"),
        _rows(context.actors, "actors"),
        _rows(context.review, "weaknesses"),
        _rows(context.checklist, "groups"),
    )
    return any(sources)


def _dashboard_cards(context: _DashboardContext) -> tuple[dict[str, list[dict[str, Any]]], tuple[list[dict[str, Any]], ...]]:
    issue_cards = _issue_cards(_rows(context.issues, "rows"))
    date_cards = _date_cards(_rows(context.chronology, "entries"))
    exhibit_cards = _exhibit_cards(_rows(context.evidence, "top_15_exhibits"))
    gap_cards = _gap_cards(_as_dict(context.chronology.get("summary")))
    actor_cards = _actor_cards(context)
    comparator_cards, raw_comparators = _comparator_cards(context.comparison)
    process_cards, raw_process = _process_cards(context)
    drafting_cards, raw_drafting = _drafting_cards(context.contradictions)
    risk_cards = _risk_cards(_rows(context.review, "weaknesses"))
    action_cards = _action_cards(_rows(context.checklist, "groups"))
    timing_cards = _timing_cards(_rows(context.deadlines, "warnings"))
    cards = {
        "main_claims_or_issues": issue_cards,
        "key_dates": date_cards,
        "strongest_exhibits": exhibit_cards,
        "open_evidence_gaps": gap_cards,
        "main_actors": actor_cards,
        "comparator_points": comparator_cards,
        "process_irregularities": process_cards,
        "drafting_priorities": drafting_cards,
        "timing_warnings": timing_cards,
        "risks_or_weak_spots": risk_cards,
        "recommended_next_actions": action_cards,
    }
    return cards, (
        issue_cards,
        date_cards,
        exhibit_cards,
        gap_cards,
        actor_cards,
        raw_comparators,
        raw_process,
        raw_drafting,
        risk_cards,
        action_cards,
        timing_cards,
    )


def _issue_cards(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "issue_id": str(row.get("issue_id") or ""),
            "title": str(row.get("title") or ""),
            "status": str(row.get("legal_relevance_status") or ""),
            "evidence_hint": _first_nonempty(row.get("relevant_facts"), row.get("missing_proof")),
        }
        for row in rows[:4]
    ]


def _date_cards(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "chronology_id": str(row.get("chronology_id") or ""),
            "date": str(row.get("date") or ""),
            "title": _first_nonempty(row.get("title"), row.get("description")),
        }
        for row in rows[:4]
    ]


def _exhibit_cards(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        rows,
        key=lambda item: (
            -int(item.get("priority_score") or 0),
            0 if str(item.get("source_conflict_status") or "") == "disputed" else 1,
            str(item.get("exhibit_id") or ""),
        ),
    )[:4]
    return [card for row in ordered if (card := _exhibit_card(row)) is not None]


def _gap_cards(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _rows(summary, "date_gaps_and_unexplained_sequences")
    ordered = sorted(
        rows,
        key=lambda row: (
            {"high": 0, "medium": 1, "low": 2}.get(str(row.get("priority") or ""), 3),
            -int(row.get("gap_days") or 0),
            str(row.get("gap_id") or ""),
        ),
    )[:3]
    return [card for row in ordered if (card := _gap_card(row)) is not None]


def _actor_cards(context: _DashboardContext) -> list[dict[str, Any]]:
    target = _as_dict(_as_dict(context.case_bundle.get("scope")).get("target_person"))
    target_email, target_name = _compact(target.get("email")).lower(), _compact(target.get("name")).lower()
    ordered = sorted(_rows(context.actors, "actors"), key=lambda row: _actor_sort_key(row, target_email, target_name))
    return [
        {
            "actor_id": str(row.get("actor_id") or ""),
            "name": _first_nonempty(row.get("name"), row.get("email")),
            "status": dict(row.get("status") or {}),
            "impact": str(row.get("helps_hurts_mixed") or ""),
        }
        for row in ordered[:4]
    ]


def _actor_sort_key(row: dict[str, Any], target_email: str, target_name: str) -> tuple[int, int, int, int, str]:
    target_match = _compact(row.get("email")).lower() == target_email or _compact(row.get("name")).lower() == target_name
    status = _as_dict(row.get("status"))
    identity = _first_nonempty(row.get("name"), row.get("email"), row.get("actor_id"))
    return (
        0 if target_match else 1,
        0 if status.get("decision_maker") else 1,
        0 if status.get("gatekeeper") else 1,
        -int(row.get("source_record_count") or 0),
        identity,
    )


def _comparator_cards(comparison: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cards = [
        {
            "comparator_point_id": str(row.get("comparator_point_id") or ""),
            "issue_id": str(row.get("issue_id") or ""),
            "strength": str(row.get("comparison_strength") or ""),
            "summary": _first_nonempty(row.get("point_summary"), row.get("issue_label")),
        }
        for row in shared_comparator_points(comparison)[:3]
    ]
    raw = list(cards)
    if not cards:
        summary, insufficiency = _as_dict(comparison.get("summary")), _as_dict(comparison.get("insufficiency"))
        cards = [
            _insufficiency_card(
                _first_nonempty(
                    summary.get("insufficiency_reason"),
                    insufficiency.get("reason"),
                    "Comparator analysis is not yet supported on the current record.",
                )
            )
        ]
    return cards, raw


def _process_cards(context: _DashboardContext) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    review = _as_dict(context.patterns.get("corpus_behavioral_review"))
    rows = (
        _as_list(review.get("procedural_irregularities"))
        + _as_list(review.get("coordination_windows"))
        + _rows(context.contradictions, "contradiction_table")
    )[:4]
    cards = [card for row in rows if isinstance(row, dict) and (card := _process_irregularity_card(row)) is not None]
    raw = list(cards)
    return (
        cards
        or [
            _insufficiency_card("No supported process-irregularity pattern is currently available in the shared behavior review.")
        ]
    ), raw


def _drafting_cards(contradictions: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cards = [
        {
            "summary": _first_nonempty(row.get("original_statement_or_promise"), row.get("later_action")),
            "confidence": str(row.get("confidence_level") or ""),
        }
        for row in _rows(contradictions, "contradiction_table")[:3]
    ]
    raw = list(cards)
    if not cards:
        cards = [
            _insufficiency_card(
                _first_nonempty(
                    _as_dict(contradictions.get("summary")).get("insufficiency_reason"),
                    "No contradiction-driven drafting priority is currently available on the shared record.",
                )
            )
        ]
    return cards, raw


def _risk_cards(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "weakness_id": str(row.get("weakness_id") or ""),
            "summary": _first_nonempty(row.get("critique"), _as_dict(row.get("repair_guidance")).get("how_to_fix")),
        }
        for row in rows[:4]
    ]


def _action_cards(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "group_id": str(group.get("group_id") or ""),
            "summary": _first_nonempty(
                _as_dict(_as_list(group.get("items"))[0]).get("request") if _as_list(group.get("items")) else "",
                group.get("title"),
            ),
        }
        for group in groups[:4]
    ]


def _timing_cards(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "warning_id": str(row.get("warning_id") or ""),
            "severity": str(row.get("severity") or ""),
            "summary": str(row.get("summary") or ""),
        }
        for row in rows[:4]
    ]


def _dashboard_payload(context: _DashboardContext, cards: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    matter = _as_dict(context.workspace.get("matter"))
    scope = _as_dict(context.case_bundle.get("scope"))
    return {
        "version": CASE_DASHBOARD_VERSION,
        "dashboard_format": "refreshable_case_dashboard",
        "matter_ref": {
            "matter_id": str(matter.get("matter_id") or ""),
            "workspace_id": str(context.workspace.get("workspace_id") or ""),
            "bundle_id": str(matter.get("bundle_id") or context.case_bundle.get("bundle_id") or ""),
            "case_label": _first_nonempty(matter.get("case_label"), scope.get("case_label")),
        },
        "summary": {
            "card_count": len(cards),
            "issue_count": len(cards["main_claims_or_issues"]),
            "actor_count": len(cards["main_actors"]),
            "exhibit_count": len(cards["strongest_exhibits"]),
            "timing_warning_count": len(cards["timing_warnings"]),
            "refreshable_from_shared_entities": True,
        },
        "cards": cards,
    }
