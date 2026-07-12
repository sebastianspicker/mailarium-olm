"""Operational timing warnings for legal-support workflows."""
# pylint: disable=too-many-arguments,too-many-branches,too-many-locals

from __future__ import annotations

from datetime import date
from typing import Any

from ._utils import _as_dict, _as_list, _compact

DEADLINE_WARNINGS_VERSION = "1"
_DEADLINE_RELEVANT_ISSUES = {
    "retaliation_massregelungsverbot",
    "pr_lpvg_participation",
    "sgb_ix_178_sbv",
    "sgb_ix_167_bem",
    "sgb_ix_164",
    "fuersorgepflicht",
}


def _parse_date(value: Any) -> date | None:
    """Parse a value into a date object.

    Args:
        value: The value to parse as a date.

    Returns:
        A date object if the value can be parsed as an ISO format date,
        otherwise None.
    """
    text = _compact(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _warning(
    *,
    warning_id: str,
    category: str,
    severity: str,
    summary: str,
    caution: str,
    linked_issue_ids: list[str] | None = None,
    linked_group_ids: list[str] | None = None,
    linked_date_gap_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "warning_id": warning_id,
        "category": category,
        "severity": severity,
        "summary": summary,
        "caution": caution,
        "not_final_legal_advice": True,
        "linked_issue_ids": [str(item) for item in linked_issue_ids or [] if _compact(item)],
        "linked_group_ids": [str(item) for item in linked_group_ids or [] if _compact(item)],
        "linked_date_gap_ids": [str(item) for item in linked_date_gap_ids or [] if _compact(item)],
    }


def build_deadline_warnings(
    *,
    case_bundle: dict[str, Any] | None,
    master_chronology: dict[str, Any] | None,
    lawyer_issue_matrix: dict[str, Any] | None,
    document_request_checklist: dict[str, Any] | None,
    as_of_date: str | None = None,
) -> dict[str, Any] | None:
    """Return cautious operational timing warnings without computing legal deadlines."""
    scope = _as_dict(_as_dict(case_bundle).get("scope"))
    chronology_summary = _as_dict(_as_dict(master_chronology).get("summary"))
    issue_rows = _dict_rows(_as_dict(lawyer_issue_matrix).get("rows"))
    checklist_groups = _dict_rows(_as_dict(document_request_checklist).get("groups"))
    if not any((scope, chronology_summary, issue_rows, checklist_groups)):
        return None
    today = _parse_date(as_of_date) or date.today()
    warnings: list[dict[str, Any]] = []
    issue_ids = _deadline_issue_ids(issue_rows)
    _append_deadline_relevance(warnings, issue_ids)
    _append_record_age_warning(warnings, today, scope, chronology_summary, issue_ids)
    urgent, loss_risk, gap_ids = _checklist_timing(checklist_groups)
    _append_preservation_warning(warnings, urgent, gap_ids)
    _append_loss_warning(warnings, loss_risk, gap_ids)
    return _warning_payload(warnings, today)


def _dict_rows(value: object) -> list[dict[str, Any]]:
    return [row for row in _as_list(value) if isinstance(row, dict)]


def _deadline_issue_ids(rows: list[dict[str, Any]]) -> list[str]:
    ids = []
    for row in rows:
        issue_id = str(row.get("issue_id") or "")
        urgency = str(row.get("urgency_or_deadline_relevance") or "").lower()
        if issue_id in _DEADLINE_RELEVANT_ISSUES or "potential urgency" in urgency or "deadline-sensitive" in urgency:
            ids.append(issue_id)
    return ids


def _append_deadline_relevance(warnings: list[dict[str, Any]], issue_ids: list[str]) -> None:
    if issue_ids:
        warnings.append(
            _warning(
                warning_id="timing:deadline_relevance",
                category="possible_deadline_relevance",
                severity="medium",
                summary="Some selected issue tracks look operationally time-sensitive and should receive prompt counsel review.",
                caution=(
                    "This is a cautionary timing signal only. It does not determine any statutory deadline or limitation period."
                ),
                linked_issue_ids=issue_ids[:6],
            )
        )


def _append_record_age_warning(warnings, today, scope, chronology_summary, issue_ids) -> None:
    candidates = [_parse_date(_as_dict(chronology_summary.get("date_range")).get("first")), _parse_date(scope.get("date_from"))]
    earliest = next((item for item in candidates if item is not None), None)
    if earliest is None:
        return
    age_days = (today - earliest).days
    if age_days < 90:
        return
    warnings.append(
        _warning(
            warning_id="timing:limitation_sensitivity",
            category="limitation_sensitivity",
            severity="high" if age_days >= 365 else "medium",
            summary=f"Part of the record reaches back {age_days} day(s), so limitation or deadline review may matter.",
            caution="This is an age-of-record warning, not a conclusion about whether any claim is timely or out of time.",
            linked_issue_ids=issue_ids[:4],
        )
    )


def _checklist_timing(groups):
    urgent, loss_risk, gaps = [], [], []
    for group in groups:
        group_id, is_urgent, has_loss_risk = _group_timing(group, gaps)
        if is_urgent:
            urgent.append(group_id)
        if has_loss_risk:
            loss_risk.append(group_id)
    return urgent, loss_risk, gaps


def _group_timing(group, gaps):
    items = _dict_rows(group.get("items"))
    for item in items:
        for gap_id in _as_list(item.get("linked_date_gap_ids")):
            text = _compact(gap_id)
            if text and text not in gaps:
                gaps.append(text)
    is_urgent = any(str(item.get("urgency") or "") == "high" for item in items)
    has_loss_risk = any(str(item.get("risk_of_loss") or "") == "high" for item in items)
    return str(group.get("group_id") or ""), is_urgent, has_loss_risk


def _append_preservation_warning(warnings, groups, gaps) -> None:
    if groups:
        warnings.append(
            _warning(
                warning_id="timing:document_preservation",
                category="document_preservation_urgency",
                severity="high",
                summary="Some requested records look preservation-sensitive and should be secured promptly.",
                caution=(
                    "This warning addresses operational preservation risk only. It does not itself establish a legal hold scope."
                ),
                linked_group_ids=groups[:6],
                linked_date_gap_ids=gaps[:6],
            )
        )


def _append_loss_warning(warnings, groups, gaps) -> None:
    if groups:
        warnings.append(
            _warning(
                warning_id="timing:evidence_loss_risk",
                category="escalating_evidence_loss_risk",
                severity="high" if len(groups) >= 2 else "medium",
                summary=(
                    "Some records appear vulnerable to retention loss, mailbox churn, or rolling overwrite "
                    "if retrieval is delayed."
                ),
                caution="This is a practical loss-risk signal, not a conclusion that evidence has already been destroyed.",
                linked_group_ids=groups[:6],
                linked_date_gap_ids=gaps[:6],
            )
        )


def _warning_payload(warnings: list[dict[str, Any]], today: date) -> dict[str, Any]:
    categories: list[str] = []
    for item in warnings:
        category = str(item.get("category") or "")
        if category and category not in categories:
            categories.append(category)
    status = "timing_review_recommended" if warnings else "no_material_timing_warning"
    return {
        "version": DEADLINE_WARNINGS_VERSION,
        "as_of_date": today.isoformat(),
        "overall_status": status,
        "summary": {
            "warning_count": len(warnings),
            "high_severity_count": sum(1 for item in warnings if str(item.get("severity") or "") == "high"),
            "categories": categories,
        },
        "warnings": warnings,
    }
