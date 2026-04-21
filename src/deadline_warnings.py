"""Operational timing warnings for legal-support workflows."""

from __future__ import annotations

from datetime import date
from typing import Any

DEADLINE_WARNINGS_VERSION = "1"
_DEADLINE_RELEVANT_ISSUES = {
    "retaliation_massregelungsverbot",
    "pr_lpvg_participation",
    "sgb_ix_178_sbv",
    "sgb_ix_167_bem",
    "sgb_ix_164",
    "fuersorgepflicht",
}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _parse_date(value: Any) -> date | None:
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
    issue_rows = [row for row in _as_list(_as_dict(lawyer_issue_matrix).get("rows")) if isinstance(row, dict)]
    checklist_groups = [row for row in _as_list(_as_dict(document_request_checklist).get("groups")) if isinstance(row, dict)]
    if not any((scope, chronology_summary, issue_rows, checklist_groups)):
        return None

    today = _parse_date(as_of_date) or date.today()
    warnings: list[dict[str, Any]] = []

    deadline_issue_ids = [
        str(row.get("issue_id") or "")
        for row in issue_rows
        if (
            str(row.get("issue_id") or "") in _DEADLINE_RELEVANT_ISSUES
            or "potential urgency" in str(row.get("urgency_or_deadline_relevance") or "").lower()
            or "deadline-sensitive" in str(row.get("urgency_or_deadline_relevance") or "").lower()
        )
    ]
    if deadline_issue_ids:
        warnings.append(
            _warning(
                warning_id="timing:deadline_relevance",
                category="possible_deadline_relevance",
                severity="medium",
                summary="Some selected issue tracks look operationally time-sensitive and should receive prompt counsel review.",
                caution=(
                    "This is a cautionary timing signal only. It does not determine any statutory deadline or limitation period."
                ),
                linked_issue_ids=deadline_issue_ids[:6],
            )
        )

    date_candidates = [
        _parse_date(_as_dict(chronology_summary.get("date_range")).get("first")),
        _parse_date(scope.get("date_from")),
    ]
    earliest_date = next((item for item in date_candidates if item is not None), None)
    if earliest_date is not None:
        age_days = (today - earliest_date).days
        if age_days >= 90:
            warnings.append(
                _warning(
                    warning_id="timing:limitation_sensitivity",
                    category="limitation_sensitivity",
                    severity="high" if age_days >= 365 else "medium",
                    summary=(f"Part of the record reaches back {age_days} day(s), so limitation or deadline review may matter."),
                    caution=(
                        "This is an age-of-record warning, not a conclusion about whether any claim is timely or out of time."
                    ),
                    linked_issue_ids=deadline_issue_ids[:4],
                )
            )

    high_urgency_group_ids: list[str] = []
    high_loss_group_ids: list[str] = []
    linked_gap_ids: list[str] = []
    for group in checklist_groups:
        group_id = str(group.get("group_id") or "")
        items = [item for item in _as_list(group.get("items")) if isinstance(item, dict)]
        if any(str(item.get("urgency") or "") == "high" for item in items):
            high_urgency_group_ids.append(group_id)
        if any(str(item.get("risk_of_loss") or "") == "high" for item in items):
            high_loss_group_ids.append(group_id)
        for item in items:
            for gap_id in _as_list(item.get("linked_date_gap_ids")):
                text = _compact(gap_id)
                if text and text not in linked_gap_ids:
                    linked_gap_ids.append(text)
    if high_urgency_group_ids:
        warnings.append(
            _warning(
                warning_id="timing:document_preservation",
                category="document_preservation_urgency",
                severity="high",
                summary="Some requested records look preservation-sensitive and should be secured promptly.",
                caution=(
                    "This warning addresses operational preservation risk only. It does not itself establish a legal hold scope."
                ),
                linked_group_ids=high_urgency_group_ids[:6],
                linked_date_gap_ids=linked_gap_ids[:6],
            )
        )
    if high_loss_group_ids:
        warnings.append(
            _warning(
                warning_id="timing:evidence_loss_risk",
                category="escalating_evidence_loss_risk",
                severity="high" if len(high_loss_group_ids) >= 2 else "medium",
                summary=(
                    "Some records appear vulnerable to retention loss, mailbox churn, "
                    "or rolling overwrite if retrieval is delayed."
                ),
                caution=("This is a practical loss-risk signal, not a conclusion that evidence has already been destroyed."),
                linked_group_ids=high_loss_group_ids[:6],
                linked_date_gap_ids=linked_gap_ids[:6],
            )
        )

    if not warnings:
        return {
            "version": DEADLINE_WARNINGS_VERSION,
            "as_of_date": today.isoformat(),
            "overall_status": "no_material_timing_warning",
            "summary": {
                "warning_count": 0,
                "high_severity_count": 0,
                "categories": [],
            },
            "warnings": [],
        }

    categories = []
    for item in warnings:
        category = str(item.get("category") or "")
        if category and category not in categories:
            categories.append(category)
    return {
        "version": DEADLINE_WARNINGS_VERSION,
        "as_of_date": today.isoformat(),
        "overall_status": "timing_review_recommended",
        "summary": {
            "warning_count": len(warnings),
            "high_severity_count": sum(1 for item in warnings if str(item.get("severity") or "") == "high"),
            "categories": categories,
        },
        "warnings": warnings,
    }
