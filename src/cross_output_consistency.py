"""Cross-output consistency checks for legal-support work products."""
# pylint: disable=too-many-arguments,too-many-branches,too-many-locals,too-many-statements

from __future__ import annotations

from typing import Any

from ._utils import _as_dict, _as_list, _compact
from .trigger_retaliation import shared_retaliation_points

CROSS_OUTPUT_CONSISTENCY_VERSION = "1"

_READ_TO_ISSUE_IDS: dict[str, tuple[str, ...]] = {
    "disability_disadvantage": ("agg_disadvantage", "sgb_ix_164", "fuersorgepflicht"),
    "retaliation_after_protected_event": (
        "retaliation_massregelungsverbot",
        "burden_shifting_indicators",
    ),
    "eingruppierung_dispute": (
        "eingruppierung_tarifliche_bewertung",
        "burden_shifting_indicators",
    ),
    "prevention_duty_gap": ("sgb_ix_167_bem", "fuersorgepflicht"),
    "participation_duty_gap": ("sgb_ix_178_sbv", "pr_lpvg_participation", "fuersorgepflicht"),
}
_SUPPORTING_EVENT_STATUSES = {"direct_event_support", "contextual_support_only"}
_STRICT_CEILINGS = {"observed_facts_only", "insufficient_for_adversarial_draft"}


def _check(
    *,
    check_id: str,
    title: str,
    status: str,
    summary: str,
    affected_outputs: list[str],
    details: list[str] | None = None,
    linked_ids: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "title": title,
        "status": status,
        "summary": summary,
        "affected_outputs": [item for item in affected_outputs if _compact(item)],
        "details": [item for item in details or [] if _compact(item)],
        "linked_ids": {
            key: [str(item) for item in values if _compact(item)]
            for key, values in (linked_ids or {}).items()
            if isinstance(values, list)
        },
    }


def _collect_referenced_ids(rows: list[dict[str, Any]], field: str) -> list[str]:
    """Collect unique non-empty string values from a field across rows."""
    ids: list[str] = []
    for row in rows:
        for item in _as_list(row.get(field)):
            text = _compact(item)
            if text and text not in ids:
                ids.append(text)
    return ids


def build_cross_output_consistency(
    *,
    master_chronology: dict[str, Any] | None,
    matter_evidence_index: dict[str, Any] | None,
    lawyer_issue_matrix: dict[str, Any] | None,
    lawyer_briefing_memo: dict[str, Any] | None,
    case_dashboard: dict[str, Any] | None,
    skeptical_employer_review: dict[str, Any] | None,
    controlled_factual_drafting: dict[str, Any] | None,
    retaliation_timeline_assessment: dict[str, Any] | None = None,
    actor_map: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return machine-detectable parity checks across major legal-support outputs."""
    chronology_entries = _dict_rows(_as_dict(master_chronology).get("entries"))
    evidence_rows = _dict_rows(_as_dict(matter_evidence_index).get("rows"))
    issue_rows = _dict_rows(_as_dict(lawyer_issue_matrix).get("rows"))
    memo_sections = _as_dict(_as_dict(lawyer_briefing_memo).get("sections"))
    dashboard_cards = _as_dict(_as_dict(case_dashboard).get("cards"))
    skeptical_weaknesses = _dict_rows(_as_dict(skeptical_employer_review).get("weaknesses"))
    retaliation_points = shared_retaliation_points(retaliation_timeline_assessment=_as_dict(retaliation_timeline_assessment))
    drafting = _as_dict(controlled_factual_drafting)
    draft_sections = _as_dict(_as_dict(drafting.get("controlled_draft")).get("sections"))
    actor_rows = _dict_rows(_as_dict(actor_map).get("actors"))

    if not _has_consistency_input(
        chronology_entries, evidence_rows, issue_rows, memo_sections, dashboard_cards, skeptical_weaknesses, draft_sections
    ):
        return None

    chronology_ids = set(_row_ids(chronology_entries, "chronology_id"))
    evidence_by_id = _index_rows(evidence_rows, "exhibit_id")
    issue_by_id = _index_rows(issue_rows, "issue_id")
    actor_by_id = _index_rows(actor_rows, "actor_id")
    top_exhibit_ids = _row_ids(_dict_rows(_as_dict(matter_evidence_index).get("top_15_exhibits"))[:4], "exhibit_id")

    checks: list[dict[str, Any]] = []

    _append_chronology_reference_check(checks, memo_sections, dashboard_cards, draft_sections, chronology_ids)

    _append_retaliation_check(checks, issue_by_id, retaliation_points)

    _append_issue_reference_check(checks, memo_sections, dashboard_cards, draft_sections, issue_by_id)

    _append_exhibit_check(checks, memo_sections, dashboard_cards, draft_sections, evidence_by_id, top_exhibit_ids)

    _append_chronology_issue_check(checks, chronology_entries, issue_by_id)

    _append_actor_check(checks, dashboard_cards, actor_by_id)

    _append_skeptical_check(checks, memo_sections, dashboard_cards, skeptical_weaknesses)

    _append_draft_check(checks, drafting, draft_sections)

    return _consistency_result(checks)


def _dict_rows(value: object) -> list[dict[str, Any]]:
    return [row for row in _as_list(value) if isinstance(row, dict)]


def _has_consistency_input(*values: object) -> bool:
    return any(values)


def _row_ids(rows: list[dict[str, Any]], field: str) -> list[str]:
    return [value for row in rows if (value := _compact(row.get(field)))]


def _index_rows(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    return {value: row for row in rows if (value := _compact(row.get(field)))}


def _consistency_result(checks: list[dict[str, Any]]) -> dict[str, Any]:
    mismatch_count = sum(1 for check in checks if check.get("status") == "mismatch")
    pass_count = sum(1 for check in checks if check.get("status") == "pass")
    affected = sorted({output for check in checks for output in _as_list(check.get("affected_outputs")) if _compact(output)})
    return {
        "version": CROSS_OUTPUT_CONSISTENCY_VERSION,
        "overall_status": "review_required" if mismatch_count else "consistent",
        "machine_review_required": bool(mismatch_count),
        "summary": {"check_count": len(checks), "pass_count": pass_count, "mismatch_count": mismatch_count},
        "affected_outputs": affected,
        "checks": checks,
    }


def _append_chronology_reference_check(checks, memo_sections, dashboard_cards, draft_sections, chronology_ids) -> None:
    memo_timeline = [row for row in _as_list(memo_sections.get("timeline")) if isinstance(row, dict)]
    dashboard_dates = [row for row in _as_list(dashboard_cards.get("key_dates")) if isinstance(row, dict)]
    draft_facts = [row for row in _as_list(draft_sections.get("established_facts")) if isinstance(row, dict)]
    chronology_ref_rows = memo_timeline + dashboard_dates + draft_facts
    missing_chronology_ids = [
        item for item in _collect_referenced_ids(chronology_ref_rows, "supporting_chronology_ids") if item not in chronology_ids
    ]
    checks.append(
        _check(
            check_id="chronology_references",
            title="Chronology References",
            status="mismatch" if missing_chronology_ids else "pass",
            summary=(
                "Some downstream outputs reference chronology entries that are missing from the shared chronology registry."
                if missing_chronology_ids
                else "Downstream chronology references resolve against the shared chronology registry."
            ),
            affected_outputs=["master_chronology", "lawyer_briefing_memo", "case_dashboard", "controlled_factual_drafting"],
            details=[f"Missing chronology id: {item}" for item in missing_chronology_ids[:6]],
            linked_ids={"chronology_ids": missing_chronology_ids[:6]},
        )
    )


def _append_retaliation_check(checks, issue_by_id, retaliation_points) -> None:
    retaliation_issue_present = "retaliation_massregelungsverbot" in issue_by_id
    retaliation_support_present = any(
        str(row.get("support_strength") or "") in {"moderate", "limited"} for row in retaliation_points
    )
    checks.append(
        _check(
            check_id="retaliation_support_alignment",
            title="Retaliation Support Alignment",
            status="mismatch" if retaliation_support_present and not retaliation_issue_present else "pass",
            summary=(
                "Retaliation timing support exists, but the issue matrix does not expose a retaliation issue row."
                if retaliation_support_present and not retaliation_issue_present
                else "Retaliation timing support and the downstream issue matrix remain aligned."
            ),
            affected_outputs=[
                "retaliation_timeline_assessment",
                "lawyer_issue_matrix",
                "lawyer_briefing_memo",
                "controlled_factual_drafting",
            ],
            linked_ids={"retaliation_point_ids": [str(row.get("retaliation_point_id") or "") for row in retaliation_points[:4]]},
        )
    )


def _append_issue_reference_check(checks, memo_sections, dashboard_cards, draft_sections, issue_by_id) -> None:
    memo_issues = _dict_rows(memo_sections.get("core_theories"))
    dashboard_issues = _dict_rows(dashboard_cards.get("main_claims_or_issues"))
    draft_issue_rows = _section_rows(draft_sections, ("concerns", "requests_for_clarification", "formal_demands"))
    missing_issue_ids = _missing_references(memo_issues + draft_issue_rows, "supporting_issue_ids", issue_by_id)
    dashboard_issue_ids = _row_ids(dashboard_issues, "issue_id")
    dashboard_issue_mismatches = [item for item in dashboard_issue_ids if item not in issue_by_id]
    mismatches = [*missing_issue_ids, *dashboard_issue_mismatches]
    checks.append(
        _check(
            check_id="issue_references",
            title="Issue References",
            status="mismatch" if mismatches else "pass",
            summary=(
                "Some downstream outputs reference issue rows that are missing from the shared issue matrix."
                if mismatches
                else "Issue references remain aligned across the issue matrix, memo, dashboard, and draft outputs."
            ),
            affected_outputs=["lawyer_issue_matrix", "lawyer_briefing_memo", "case_dashboard", "controlled_factual_drafting"],
            details=[f"Missing issue id: {item}" for item in mismatches[:6]],
            linked_ids={"issue_ids": mismatches[:6]},
        )
    )


def _section_rows(sections: dict[str, Any], names: tuple[str, ...]) -> list[dict[str, Any]]:
    return [row for name in names for row in _dict_rows(sections.get(name))]


def _missing_references(rows, field, registry):
    return [item for item in _collect_referenced_ids(rows, field) if item not in registry]


def _append_exhibit_check(checks, memo_sections, dashboard_cards, draft_sections, evidence_by_id, top_exhibit_ids) -> None:
    memo_evidence = _dict_rows(memo_sections.get("strongest_evidence"))
    dashboard_exhibits = _dict_rows(dashboard_cards.get("strongest_exhibits"))
    draft_exhibit_rows = _section_rows(
        draft_sections, ("established_facts", "concerns", "requests_for_clarification", "formal_demands")
    )
    missing_exhibit_ids = _missing_references(memo_evidence + draft_exhibit_rows, "supporting_exhibit_ids", evidence_by_id)
    dashboard_exhibit_ids = _row_ids(dashboard_exhibits, "exhibit_id")
    ranking_mismatches = [item for item in dashboard_exhibit_ids if top_exhibit_ids and item not in top_exhibit_ids]
    strength_mismatches = _strength_mismatches(dashboard_exhibits, evidence_by_id)
    mismatch = bool(missing_exhibit_ids or ranking_mismatches or strength_mismatches)
    checks.append(
        _check(
            check_id="exhibit_rankings_and_strength",
            title="Exhibit Rankings And Strength",
            status="mismatch" if mismatch else "pass",
            summary=(
                "Some downstream exhibit references drift from the shared evidence index or its ranking/strength data."
                if mismatch
                else "Exhibit references and strength summaries remain aligned with the shared evidence index."
            ),
            affected_outputs=["matter_evidence_index", "lawyer_briefing_memo", "case_dashboard", "controlled_factual_drafting"],
            details=(
                [f"Missing exhibit id: {item}" for item in missing_exhibit_ids[:4]]
                + [f"Dashboard exhibit falls outside current top ranking: {item}" for item in ranking_mismatches[:4]]
                + [f"Dashboard exhibit strength mismatch: {item}" for item in strength_mismatches[:4]]
            ),
            linked_ids={
                "exhibit_ids": [*missing_exhibit_ids, *ranking_mismatches, *strength_mismatches][:8],
            },
        )
    )


def _strength_mismatches(dashboard_exhibits, evidence_by_id):
    mismatches = []
    for row in dashboard_exhibits:
        exhibit_id = _compact(row.get("exhibit_id"))
        if not exhibit_id or exhibit_id not in evidence_by_id:
            continue
        expected = _compact(_as_dict(evidence_by_id[exhibit_id].get("exhibit_reliability")).get("strength"))
        actual = _compact(row.get("strength"))
        if expected and actual and expected != actual:
            mismatches.append(exhibit_id)
    return mismatches


def _append_chronology_issue_check(checks, chronology_entries, issue_by_id) -> None:
    missing_issue_rows_for_chronology: list[str] = []
    for entry in chronology_entries:
        event_support_matrix = _as_dict(entry.get("event_support_matrix"))
        for read_id, payload in event_support_matrix.items():
            read_payload = _as_dict(payload)
            if not read_payload.get("selected_in_case_scope"):
                continue
            if str(read_payload.get("status") or "") not in _SUPPORTING_EVENT_STATUSES:
                continue
            mapped_issue_ids = _READ_TO_ISSUE_IDS.get(read_id, ())
            if mapped_issue_ids and not any(issue_id in issue_by_id for issue_id in mapped_issue_ids):
                missing_issue_rows_for_chronology.append(read_id)
    checks.append(
        _check(
            check_id="chronology_issue_matrix_alignment",
            title="Chronology And Issue Matrix Alignment",
            status="mismatch" if missing_issue_rows_for_chronology else "pass",
            summary=(
                "Chronology-supported issue reads are missing from the lawyer issue matrix."
                if missing_issue_rows_for_chronology
                else "Chronology-supported issue reads are represented in the lawyer issue matrix."
            ),
            affected_outputs=["master_chronology", "lawyer_issue_matrix"],
            details=[
                f"Missing issue row for chronology-supported read: {item}" for item in missing_issue_rows_for_chronology[:6]
            ],
            linked_ids={"issue_ids": missing_issue_rows_for_chronology[:6]},
        )
    )


def _append_actor_check(checks, dashboard_cards, actor_by_id) -> None:
    dashboard_actor_rows = [row for row in _as_list(dashboard_cards.get("main_actors")) if isinstance(row, dict)]
    actor_role_mismatches: list[str] = []
    for row in dashboard_actor_rows:
        actor_id = _compact(row.get("actor_id"))
        actor = _as_dict(actor_by_id.get(actor_id))
        if not actor_id or not actor:
            continue
        if _as_dict(row.get("status")) != _as_dict(actor.get("status")):
            actor_role_mismatches.append(actor_id)
    checks.append(
        _check(
            check_id="actor_role_parity",
            title="Actor Role Parity",
            status="mismatch" if actor_role_mismatches else "pass",
            summary=(
                "Dashboard actor roles drift from the shared actor map."
                if actor_role_mismatches
                else "Dashboard actor roles remain aligned with the shared actor map."
            ),
            affected_outputs=["actor_map", "case_dashboard"],
            details=[f"Actor status mismatch: {item}" for item in actor_role_mismatches[:6]],
            linked_ids={"actor_ids": actor_role_mismatches[:6]},
        )
    )


def _append_skeptical_check(checks, memo_sections, dashboard_cards, skeptical_weaknesses) -> None:
    memo_weaknesses = [row for row in _as_list(memo_sections.get("weaknesses_or_risks")) if isinstance(row, dict)]
    dashboard_risks = [row for row in _as_list(dashboard_cards.get("risks_or_weak_spots")) if isinstance(row, dict)]
    skeptical_parity_mismatches: list[str] = []
    if skeptical_weaknesses and not memo_weaknesses:
        skeptical_parity_mismatches.append("memo_missing_weaknesses")
    if skeptical_weaknesses and not dashboard_risks:
        skeptical_parity_mismatches.append("dashboard_missing_risks")
    checks.append(
        _check(
            check_id="skeptical_review_parity",
            title="Skeptical Review Parity",
            status="mismatch" if skeptical_parity_mismatches else "pass",
            summary=(
                "Claimant-facing outputs omit weakness coverage that exists in the skeptical employer-side review."
                if skeptical_parity_mismatches
                else "Skeptical-review risks are carried through to claimant-facing summary outputs."
            ),
            affected_outputs=["skeptical_employer_review", "lawyer_briefing_memo", "case_dashboard"],
            details=[item.replace("_", " ") for item in skeptical_parity_mismatches],
            linked_ids={},
        )
    )


def _append_draft_check(checks, drafting, draft_sections) -> None:
    preflight = _as_dict(drafting.get("framing_preflight"))
    allegation_ceiling = _as_dict(preflight.get("allegation_ceiling"))
    draft = _as_dict(drafting.get("controlled_draft"))
    ceiling_level = _compact(allegation_ceiling.get("ceiling_level"))
    applied_ceiling = _compact(draft.get("allegation_ceiling_applied"))
    draft_concerns = [row for row in _as_list(draft_sections.get("concerns")) if isinstance(row, dict)]
    draft_mismatches: list[str] = []
    if ceiling_level and applied_ceiling and ceiling_level != applied_ceiling:
        draft_mismatches.append("applied_ceiling_does_not_match_preflight")
    if ceiling_level in _STRICT_CEILINGS and draft_concerns:
        draft_mismatches.append("draft_concerns_exceed_current_ceiling")
    checks.append(
        _check(
            check_id="draft_preflight_alignment",
            title="Draft Preflight Alignment",
            status="mismatch" if draft_mismatches else "pass",
            summary=(
                "The controlled draft exceeds or diverges from its framing preflight."
                if draft_mismatches
                else "The controlled draft remains aligned with its framing preflight and allegation ceiling."
            ),
            affected_outputs=["controlled_factual_drafting"],
            details=[item.replace("_", " ") for item in draft_mismatches],
            linked_ids={},
        )
    )
