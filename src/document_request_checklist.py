"""Concrete document-request and preservation checklist generation."""

from __future__ import annotations

from typing import Any

DOCUMENT_REQUEST_CHECKLIST_VERSION = "1"

_GROUP_RULES: tuple[dict[str, Any], ...] = (
    {
        "group_id": "personnel_file",
        "title": "Personnel File",
        "keywords": ("personnel", "personalakte", "hr file", "employment file"),
        "custodian": "HR / personnel administration",
        "urgency": "medium",
        "risk_of_loss": "medium",
        "preservation_action": "Preserve the current personnel file, amendments, and related HR correspondence in native form.",
    },
    {
        "group_id": "home_office_mobile_work",
        "title": "Home Office / Mobile Work Documents",
        "keywords": ("home office", "mobile work", "remote work", "telearbeit"),
        "custodian": "HR and line management",
        "urgency": "medium",
        "risk_of_loss": "medium",
        "preservation_action": (
            "Preserve mobile-work approvals, policy versions, and any later changes to remote-work arrangements."
        ),
    },
    {
        "group_id": "taetigkeitsdarstellung_job_evaluation",
        "title": "Tätigkeitsdarstellung And Job Evaluation Records",
        "keywords": ("tätigkeits", "taetigkeits", "job evaluation", "eingruppierung", "tarif", "classification"),
        "custodian": "HR, compensation, and line management",
        "urgency": "medium",
        "risk_of_loss": "medium",
        "preservation_action": (
            "Preserve the operative role description, job evaluation papers, and any draft or revised classification records."
        ),
    },
    {
        "group_id": "task_change_communications",
        "title": "Task-Change Communications",
        "keywords": ("task change", "duty change", "assignment", "workflow", "approval", "instruction"),
        "custodian": "Line management and departmental administration",
        "urgency": "high",
        "risk_of_loss": "medium",
        "preservation_action": (
            "Preserve emails, chat records, and meeting notes showing assignment changes or changed reporting expectations."
        ),
    },
    {
        "group_id": "sbv_records",
        "title": "SBV Records",
        "keywords": ("sbv", "schwerbehindertenvertretung", "178 sgb ix"),
        "custodian": "SBV office and HR",
        "urgency": "high",
        "risk_of_loss": "medium",
        "preservation_action": "Preserve SBV consultation requests, notices, minutes, and any response trail.",
    },
    {
        "group_id": "pr_records",
        "title": "PR / LPVG Records",
        "keywords": ("personalrat", "betriebsrat", "lpvg", "mitbestimmung", "pr "),
        "custodian": "Personalrat / works council and HR",
        "urgency": "high",
        "risk_of_loss": "medium",
        "preservation_action": "Preserve participation notices, agenda items, minutes, and follow-up correspondence.",
    },
    {
        "group_id": "bem_prevention_records",
        "title": "BEM / Prevention Records",
        "keywords": ("bem", "prävention", "praevention", "167 sgb ix", "workability"),
        "custodian": "HR, occupational health, and disability management functions",
        "urgency": "high",
        "risk_of_loss": "medium",
        "preservation_action": (
            "Preserve BEM invitations, prevention notes, attendance, and outcome records before routine cleanup or mailbox loss."
        ),
    },
    {
        "group_id": "accommodation_records",
        "title": "Accommodation Records",
        "keywords": ("accommodation", "adjustment", "medical", "164 sgb ix", "support measure"),
        "custodian": "HR, occupational health, and line management",
        "urgency": "high",
        "risk_of_loss": "medium",
        "preservation_action": (
            "Preserve accommodation requests, responses, medical-workability coordination notes, and implementation records."
        ),
    },
    {
        "group_id": "time system_attendance_records",
        "title": "time system / Attendance Records",
        "keywords": ("time system", "attendance", "time record", "working time", "timesheet"),
        "custodian": "Timekeeping / payroll administration",
        "urgency": "high",
        "risk_of_loss": "high",
        "preservation_action": (
            "Preserve raw attendance exports, correction logs, and approval trails "
            "before rolling retention windows overwrite them."
        ),
    },
    {
        "group_id": "calendar_meeting_records",
        "title": "Calendar Invites / Meeting Notes",
        "keywords": ("calendar", "meeting", "invite", "appointment", "minutes", "meeting note"),
        "custodian": "Meeting organizers and mailbox custodians",
        "urgency": "high",
        "risk_of_loss": "high",
        "preservation_action": (
            "Preserve native calendar items, attendee updates, and meeting notes before mailbox or client-side sync loss."
        ),
    },
    {
        "group_id": "comparator_evidence",
        "title": "Comparator Evidence",
        "keywords": ("comparator", "vergleich", "peer", "similarly situated"),
        "custodian": "HR, line management, and relevant decision-makers",
        "urgency": "medium",
        "risk_of_loss": "medium",
        "preservation_action": (
            "Preserve peer-treatment records and policy application examples in a "
            "way that keeps dates and decision context intact."
        ),
    },
)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _match_group(request_text: str) -> dict[str, Any]:
    normalized = " ".join(str(request_text or "").lower().split())
    for rule in _GROUP_RULES:
        if any(keyword in normalized for keyword in rule["keywords"]):
            return rule
    return {
        "group_id": "general_document_requests",
        "title": "General Document Requests",
        "custodian": "HR, line management, or the most likely business owner",
        "urgency": "medium",
        "risk_of_loss": "medium",
        "preservation_action": "Preserve the underlying document, its metadata, and any related routing correspondence.",
    }


def _request_item(
    *,
    item_id: str,
    request_text: str,
    why_it_matters: str,
    likely_custodian: str,
    would_prove_or_disprove: str,
    urgency: str,
    risk_of_loss: str,
    preservation_action: str,
    linked_date_gap_ids: list[str] | None = None,
    supporting_finding_ids: list[str] | None = None,
    supporting_source_ids: list[str] | None = None,
    supporting_uids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "request": request_text,
        "why_it_matters": why_it_matters,
        "likely_custodian": likely_custodian,
        "would_prove_or_disprove": would_prove_or_disprove,
        "urgency": urgency,
        "risk_of_loss": risk_of_loss,
        "preservation_action": preservation_action,
        "linked_date_gap_ids": linked_date_gap_ids or [],
        "supporting_finding_ids": supporting_finding_ids or [],
        "supporting_source_ids": supporting_source_ids or [],
        "supporting_uids": supporting_uids or [],
    }


def build_document_request_checklist(
    *,
    matter_evidence_index: dict[str, Any] | None,
    skeptical_employer_review: dict[str, Any] | None,
    missing_information_entries: list[dict[str, Any]] | None = None,
    lawyer_issue_matrix: dict[str, Any] | None = None,
    case_scope_quality: dict[str, Any] | None = None,
    analysis_limits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a grouped records-request and preservation workflow."""
    evidence_index = _as_dict(matter_evidence_index)
    skeptical_review = _as_dict(skeptical_employer_review)
    lawyer_issue_rows = [item for item in _as_list(_as_dict(lawyer_issue_matrix).get("rows")) if isinstance(item, dict)]
    scope_quality = _as_dict(case_scope_quality)
    limits = _as_dict(analysis_limits)
    missing_exhibits = [item for item in _as_list(evidence_index.get("top_10_missing_exhibits")) if isinstance(item, dict)]
    weakness_items = [item for item in _as_list(skeptical_review.get("weaknesses")) if isinstance(item, dict)]
    missing_information_entries = [item for item in (missing_information_entries or []) if isinstance(item, dict)]

    grouped: dict[str, dict[str, Any]] = {}

    for index, missing in enumerate(missing_exhibits, start=1):
        request_text = str(missing.get("requested_exhibit") or "").strip()
        if not request_text:
            continue
        rule = _match_group(request_text)
        group = grouped.setdefault(
            str(rule["group_id"]),
            {
                "group_id": str(rule["group_id"]),
                "title": str(rule["title"]),
                "items": [],
            },
        )
        group["items"].append(
            _request_item(
                item_id=f"request:{rule['group_id']}:{index}",
                request_text=request_text,
                why_it_matters=str(
                    missing.get("why_missing_matters") or "This document would help test or repair the current proof gap."
                ),
                likely_custodian=str(rule["custodian"]),
                would_prove_or_disprove=(
                    f"Would help prove or disprove the current {missing.get('issue_track_title') or 'issue'} "
                    "theory and close the linked missing-proof gap."
                ),
                urgency=str(rule["urgency"]),
                risk_of_loss=str(rule["risk_of_loss"]),
                preservation_action=str(rule["preservation_action"]),
                linked_date_gap_ids=[str(item) for item in _as_list(missing.get("linked_date_gap_ids")) if item],
            )
        )

    # Convert broader missing-information flags into concrete preservation requests when possible.
    for entry in missing_information_entries:
        statement = str(entry.get("statement") or "").strip()
        if not statement:
            continue
        if "org or dependency context is missing" in statement.lower():
            rule = _match_group("personnel file role facts")
            group = grouped.setdefault(
                str(rule["group_id"]),
                {"group_id": str(rule["group_id"]), "title": str(rule["title"]), "items": []},
            )
            group["items"].append(
                _request_item(
                    item_id=f"request:{rule['group_id']}:org_context",
                    request_text="Personnel file entries, organization charts, and current role-fact records",
                    why_it_matters="Structured org context is missing and limits hierarchy and dependency review.",
                    likely_custodian=str(rule["custodian"]),
                    would_prove_or_disprove=(
                        "Would prove or disprove who held decision authority, reporting control, or dependency leverage."
                    ),
                    urgency=str(rule["urgency"]),
                    risk_of_loss=str(rule["risk_of_loss"]),
                    preservation_action=str(rule["preservation_action"]),
                )
            )
        if "comparator" in statement.lower():
            rule = _match_group("comparator evidence")
            group = grouped.setdefault(
                str(rule["group_id"]),
                {"group_id": str(rule["group_id"]), "title": str(rule["title"]), "items": []},
            )
            group["items"].append(
                _request_item(
                    item_id=f"request:{rule['group_id']}:missing_comparator",
                    request_text="Role-matched comparator treatment records under the same policy and decision-maker",
                    why_it_matters="Comparator paths remain unavailable and weaken unequal-treatment review.",
                    likely_custodian=str(rule["custodian"]),
                    would_prove_or_disprove=(
                        "Would prove or disprove whether the claimant was treated differently from similarly situated peers."
                    ),
                    urgency=str(rule["urgency"]),
                    risk_of_loss=str(rule["risk_of_loss"]),
                    preservation_action=str(rule["preservation_action"]),
                )
            )

    missing_fields = {str(item) for item in _as_list(scope_quality.get("missing_recommended_fields")) if str(item).strip()}
    if "comparator_actors" in missing_fields:
        rule = _match_group("comparator evidence")
        group = grouped.setdefault(
            str(rule["group_id"]),
            {"group_id": str(rule["group_id"]), "title": str(rule["title"]), "items": []},
        )
        group["items"].append(
            _request_item(
                item_id=f"request:{rule['group_id']}:case_scope",
                request_text="Role-matched comparator identities and their treatment records under the same manager or policy",
                why_it_matters="Comparator actors are missing from the supplied case scope.",
                likely_custodian=str(rule["custodian"]),
                would_prove_or_disprove=(
                    "Would prove or disprove whether the claimant was treated differently from similarly situated peers."
                ),
                urgency=str(rule["urgency"]),
                risk_of_loss=str(rule["risk_of_loss"]),
                preservation_action=str(rule["preservation_action"]),
            )
        )
    if "org_context" in missing_fields:
        rule = _match_group("personnel file role facts")
        group = grouped.setdefault(
            str(rule["group_id"]),
            {"group_id": str(rule["group_id"]), "title": str(rule["title"]), "items": []},
        )
        group["items"].append(
            _request_item(
                item_id=f"request:{rule['group_id']}:org_scope",
                request_text="Organization charts, reporting lines, and role-fact records for the relevant actors",
                why_it_matters="Org or dependency context is missing from the supplied case scope.",
                likely_custodian=str(rule["custodian"]),
                would_prove_or_disprove=(
                    "Would prove or disprove decision authority, gatekeeping position, and dependency leverage."
                ),
                urgency=str(rule["urgency"]),
                risk_of_loss=str(rule["risk_of_loss"]),
                preservation_action=str(rule["preservation_action"]),
            )
        )
    if "alleged_adverse_actions" in missing_fields or "retaliation_focus_without_alleged_adverse_actions" in {
        str(item) for item in _as_list(limits.get("downgrade_reasons")) if str(item).strip()
    }:
        rule = _match_group("task change communications")
        group = grouped.setdefault(
            str(rule["group_id"]),
            {"group_id": str(rule["group_id"]), "title": str(rule["title"]), "items": []},
        )
        group["items"].append(
            _request_item(
                item_id=f"request:{rule['group_id']}:adverse_actions",
                request_text=(
                    "Dated records for project withdrawal, tighter controls, exclusion, "
                    "or similar adverse actions after rights assertions"
                ),
                why_it_matters=(
                    "Retaliation review is weakened because explicit adverse actions "
                    "are not yet structured in the supplied scope."
                ),
                likely_custodian=str(rule["custodian"]),
                would_prove_or_disprove=(
                    "Would prove or disprove whether adverse treatment intensified after protected activity."
                ),
                urgency="high",
                risk_of_loss=str(rule["risk_of_loss"]),
                preservation_action=str(rule["preservation_action"]),
            )
        )

    for index, row in enumerate(lawyer_issue_rows, start=1):
        missing_proof = [str(item) for item in _as_list(row.get("missing_proof")) if str(item).strip()]
        if not missing_proof:
            continue
        issue_title = str(row.get("title") or row.get("issue_id") or "issue")
        seed_text = " ".join([issue_title, *missing_proof])
        rule = _match_group(seed_text)
        group = grouped.setdefault(
            str(rule["group_id"]),
            {"group_id": str(rule["group_id"]), "title": str(rule["title"]), "items": []},
        )
        group["items"].append(
            _request_item(
                item_id=f"request:{rule['group_id']}:issue:{index}",
                request_text=f"{issue_title}: " + "; ".join(missing_proof[:2]),
                why_it_matters=f"The current {issue_title} row still lists missing proof that weakens counsel-facing review.",
                likely_custodian=str(rule["custodian"]),
                would_prove_or_disprove=f"Would prove or disprove the current {issue_title} theory on a source-bound footing.",
                urgency=str(rule["urgency"]),
                risk_of_loss=str(rule["risk_of_loss"]),
                preservation_action=str(rule["preservation_action"]),
            )
        )

    # Add preservation-sensitive stress-test items from skeptical review.
    for index, weakness in enumerate(weakness_items, start=1):
        category = str(weakness.get("category") or "")
        if category not in {"chronology_problem", "missing_documentation", "ordinary_management_explanation"}:
            continue
        rule = _match_group("calendar meeting records" if category == "chronology_problem" else "task change communications")
        group = grouped.setdefault(
            str(rule["group_id"]),
            {"group_id": str(rule["group_id"]), "title": str(rule["title"]), "items": []},
        )
        request_text = (
            "Native calendar invites, attendee changes, and meeting notes around the disputed sequence"
            if category == "chronology_problem"
            else "Task-change communications, approvals, and workflow instructions that test the ordinary-management explanation"
        )
        group["items"].append(
            _request_item(
                item_id=f"request:{rule['group_id']}:repair:{index}",
                request_text=request_text,
                why_it_matters=str(weakness.get("why_it_matters") or ""),
                likely_custodian=str(rule["custodian"]),
                would_prove_or_disprove=str(
                    _as_dict(weakness.get("repair_guidance")).get("evidence_that_would_repair")
                    or "Would help prove or disprove the stressed weakness."
                ),
                urgency="high" if category == "chronology_problem" else str(rule["urgency"]),
                risk_of_loss="high" if category == "chronology_problem" else str(rule["risk_of_loss"]),
                preservation_action=str(rule["preservation_action"]),
                linked_date_gap_ids=[str(item) for item in _as_list(weakness.get("linked_date_gap_ids")) if item],
                supporting_finding_ids=[str(item) for item in _as_list(weakness.get("supporting_finding_ids")) if item],
                supporting_source_ids=[str(item) for item in _as_list(weakness.get("supporting_source_ids")) if item],
                supporting_uids=[str(item) for item in _as_list(weakness.get("supporting_uids")) if item],
            )
        )

    groups = sorted(grouped.values(), key=lambda item: (str(item.get("title") or ""), str(item.get("group_id") or "")))
    for group in groups:
        items = [item for item in _as_list(group.get("items")) if isinstance(item, dict)]
        group["item_count"] = len(items)
        group["linked_date_gap_ids"] = list(
            dict.fromkeys(str(item) for row in items for item in _as_list(row.get("linked_date_gap_ids")) if str(item).strip())
        )
        group["supporting_finding_ids"] = list(
            dict.fromkeys(str(item) for row in items for item in _as_list(row.get("supporting_finding_ids")) if str(item).strip())
        )
        group["supporting_source_ids"] = list(
            dict.fromkeys(str(item) for row in items for item in _as_list(row.get("supporting_source_ids")) if str(item).strip())
        )
        group["supporting_uids"] = list(
            dict.fromkeys(str(item) for row in items for item in _as_list(row.get("supporting_uids")) if str(item).strip())
        )
        group["items"] = items

    return {
        "version": DOCUMENT_REQUEST_CHECKLIST_VERSION,
        "group_count": len(groups),
        "groups": groups,
    }
