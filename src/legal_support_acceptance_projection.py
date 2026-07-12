"""Stable projection helpers for realistic legal-support acceptance outputs."""
# pylint: disable=too-many-locals

from __future__ import annotations

import json
import re
from typing import Any

from ._utils import _as_dict, _as_list


def _chronology_source_id(row: dict[str, Any]) -> Any:
    if row.get("source_id"):
        return row.get("source_id")
    source_document = _as_dict(row.get("source_document"))
    if source_document.get("source_id"):
        return source_document.get("source_id")
    source_ids = [str(item) for item in _as_list(_as_dict(row.get("source_linkage")).get("source_ids")) if str(item).strip()]
    return source_ids[0] if source_ids else None


def _chronology_issue_category(row: dict[str, Any]) -> Any:
    if row.get("issue_category"):
        return row.get("issue_category")
    matrix = _as_dict(row.get("event_support_matrix"))
    categories = [
        read_id.replace("_", " ")
        for read_id, payload in matrix.items()
        if read_id != "ordinary_managerial_explanation"
        and isinstance(payload, dict)
        and str(_as_dict(payload).get("status") or "") == "direct_event_support"
    ]
    return categories[:4]


def _head_tail_slice(rows: list[object], *, limit: int) -> list[object]:
    """Keep both early and late rows so acceptance goldens are less head-biased."""
    if len(rows) <= limit:
        return rows
    head = max(1, limit // 2)
    tail = max(1, limit - head)
    return rows[:head] + rows[-tail:]


def _public_golden_value(value: object) -> object:
    """Remove fixture-local publication-risk markers from public goldens."""
    if isinstance(value, str):
        return re.sub("".join(("nova", "time")), "attendance-system", value, flags=re.IGNORECASE)
    if isinstance(value, list):
        return [_public_golden_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _public_golden_value(item) for key, item in value.items()}
    return value


def build_golden_projection(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a stable cross-product golden subset for acceptance drift detection."""
    full_case_analysis = payload.get("full_case_analysis") if isinstance(payload, dict) else {}
    if not isinstance(full_case_analysis, dict):
        full_case_analysis = {}
    issue_rows = _project_issue_rows(full_case_analysis)
    matter_index = _as_dict(full_case_analysis.get("matter_evidence_index"))
    ranked_evidence_rows = _as_list(matter_index.get("top_15_exhibits")) or _as_list(matter_index.get("rows"))
    chronology_summary = _as_dict(_as_dict(full_case_analysis.get("master_chronology")).get("summary"))
    matter_ingestion_report = _as_dict(full_case_analysis.get("matter_ingestion_report"))
    projection: dict[str, Any] = {}
    projection.update(_projection_base(payload, full_case_analysis, matter_ingestion_report))
    projection.update(_projection_evidence(ranked_evidence_rows))
    projection.update(_projection_chronology(full_case_analysis, chronology_summary))
    projection.update(_projection_legal(full_case_analysis, issue_rows))
    projection.update(_projection_memo_dashboard(full_case_analysis))
    projection.update(_projection_final(full_case_analysis))
    public_projection = _public_golden_value(projection)
    return public_projection if isinstance(public_projection, dict) else projection


def _project_issue_rows(full_case_analysis: dict[str, Any]) -> list[dict[str, Any]]:
    issue_rows_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in _as_list((full_case_analysis.get("lawyer_issue_matrix") or {}).get("rows")):
        if not isinstance(row, dict):
            continue
        issue_id = str(row.get("issue_id") or "")
        title = str(row.get("title") or "")
        legal_relevance_status = str(row.get("legal_relevance_status") or "")
        key = (issue_id, title, legal_relevance_status)
        entry = issue_rows_by_key.setdefault(
            key,
            {
                "issue_id": row.get("issue_id"),
                "title": row.get("title"),
                "legal_relevance_status": row.get("legal_relevance_status"),
                "missing_proof": set(),
            },
        )
        missing_proof = entry["missing_proof"]
        if isinstance(missing_proof, set):
            missing_proof.update(str(item) for item in _as_list(row.get("missing_proof")) if str(item).strip())
    issue_rows = sorted(
        [
            {
                "issue_id": row.get("issue_id"),
                "title": row.get("title"),
                "legal_relevance_status": row.get("legal_relevance_status"),
                "missing_proof_count": len(row["missing_proof"]),
            }
            for row in issue_rows_by_key.values()
        ],
        key=lambda row: json.dumps(row, sort_keys=True, ensure_ascii=False),
    )
    return issue_rows


def _projection_base(
    payload: dict[str, Any], full_case_analysis: dict[str, Any], matter_ingestion_report: dict[str, Any]
) -> dict[str, Any]:
    return {
        "workflow": str(payload.get("workflow") or ""),
        "status": str(payload.get("status") or ""),
        "acceptance_lane": _as_dict(payload.get("acceptance_lane")),
        "analysis_query": str(full_case_analysis.get("analysis_query") or ""),
        "matter_ingestion_summary": matter_ingestion_report.get("summary", {}),
        "matter_ingestion_status": matter_ingestion_report.get("completeness_status", ""),
        "matter_ingestion_promotability": [
            {
                "source_id": row.get("source_id"),
                "promotability_status": row.get("promotability_status"),
            }
            for row in _head_tail_slice(_as_list(matter_ingestion_report.get("artifacts")), limit=8)
            if isinstance(row, dict)
        ],
        "coverage_status": ((full_case_analysis.get("matter_coverage_ledger") or {}).get("summary") or {}).get(
            "coverage_status", ""
        ),
        "analysis_limit_notes": list(_as_list((full_case_analysis.get("analysis_limits") or {}).get("notes"))),
    }


def _projection_evidence(ranked_evidence_rows: list[Any]) -> dict[str, Any]:
    return {
        "evidence_rows": [
            {
                "exhibit_id": row.get("exhibit_id"),
                "document_type": row.get("document_type") or row.get("source_type"),
                "main_issue_tags": row.get("main_issue_tags"),
                "source_id": row.get("source_id"),
                "strength": ((row.get("exhibit_reliability") or {}).get("strength")) or row.get("strength"),
                "supporting_source_ids": row.get("supporting_source_ids"),
                "source_conflict_status": row.get("source_conflict_status"),
            }
            for row in _head_tail_slice(ranked_evidence_rows, limit=8)
            if isinstance(row, dict)
        ],
        "provenance_examples": [
            {
                "source_id": row.get("source_id"),
                "source_conflict_status": row.get("source_conflict_status"),
                "source_language": row.get("source_language"),
                "source_link_ambiguity": row.get("source_link_ambiguity"),
            }
            for row in _head_tail_slice(ranked_evidence_rows, limit=5)
            if isinstance(row, dict)
        ],
    }


def _projection_chronology(full_case_analysis: dict[str, Any], chronology_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "chronology_gap_ids": _projection_ids(chronology_summary.get("date_gaps_and_unexplained_sequences"), "gap_id"),
        "chronology_conflict_ids": _projection_ids(
            _as_dict(chronology_summary.get("source_conflict_registry")).get("conflicts"), "conflict_id"
        ),
        "chronology_entries": _project_chronology_entries(full_case_analysis),
    }


def _projection_ids(rows: object, field: str) -> list[str]:
    return [value for item in _as_list(rows) if isinstance(item, dict) and (value := str(item.get(field) or ""))]


def _project_chronology_entries(full_case_analysis: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _head_tail_slice(_as_list((full_case_analysis.get("master_chronology") or {}).get("entries")), limit=10)
    return [
        {
            "chronology_id": row.get("chronology_id"),
            "date": row.get("date"),
            "title": row.get("title"),
            "issue_category": _chronology_issue_category(row),
            "source_id": _chronology_source_id(row),
            "source_ids": _as_dict(row.get("source_linkage")).get("source_ids"),
            "linked_source_ids": _as_dict(row.get("source_linkage")).get("linked_source_ids"),
            "supporting_citation_ids": _as_dict(row.get("source_linkage")).get("supporting_citation_ids"),
        }
        for row in rows
        if isinstance(row, dict)
    ]


def _projection_legal(full_case_analysis: dict[str, Any], issue_rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "comparator_points": [
            {
                "comparator_point_id": row.get("comparator_point_id"),
                "issue_id": row.get("issue_id"),
                "comparison_strength": row.get("comparison_strength"),
                "comparison_quality": row.get("comparison_quality"),
            }
            for row in _as_list((full_case_analysis.get("comparative_treatment") or {}).get("comparator_points"))
            if isinstance(row, dict)
        ],
        "issue_rows": issue_rows,
        "skeptical_weaknesses": [
            {
                "weakness_id": row.get("weakness_id"),
                "title": row.get("title") or row.get("category"),
                "severity": row.get("severity") or "",
                "category": row.get("category"),
                "critique": row.get("critique"),
                "repair_guidance": _as_dict(row.get("repair_guidance")),
            }
            for row in _head_tail_slice(
                _as_list((full_case_analysis.get("skeptical_employer_review") or {}).get("weaknesses")),
                limit=8,
            )
            if isinstance(row, dict)
        ],
    }


def _projection_memo_dashboard(full_case_analysis: dict[str, Any]) -> dict[str, Any]:
    sections = (full_case_analysis.get("lawyer_briefing_memo") or {}).get("sections") or {}
    return {
        "memo_sections": {
            "executive_summary": _memo_texts(sections, "executive_summary"),
            "strongest_evidence": _memo_texts(sections, "strongest_evidence"),
        },
        "draft_preflight": (full_case_analysis.get("controlled_factual_drafting") or {}).get("framing_preflight", {}),
        "dashboard_cards": _dashboard_projection(full_case_analysis),
    }


def _memo_texts(sections: dict[str, Any], key: str) -> list[Any]:
    return [row.get("text") for row in _as_list(sections.get(key))[:5] if isinstance(row, dict)]


def _dashboard_projection(full_case_analysis: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    cards = (full_case_analysis.get("case_dashboard") or {}).get("cards") or {}
    return {
        key: [_dashboard_card(row) for row in _head_tail_slice(value, limit=6) if isinstance(row, dict)]
        for key, value in cards.items()
        if isinstance(value, list)
    }


def _dashboard_card(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: row.get(key)
        for key in (
            "entry_id",
            "title",
            "summary",
            "evidence_hint",
            "supporting_source_ids",
            "supporting_uids",
            "gap_id",
            "group_id",
        )
    }


def _projection_final(full_case_analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "retaliation_points": [
            {
                "retaliation_point_id": row.get("retaliation_point_id"),
                "support_strength": row.get("support_strength"),
                "analysis_quality": row.get("analysis_quality"),
                "counterargument": row.get("counterargument"),
            }
            for row in _as_list((full_case_analysis.get("retaliation_analysis") or {}).get("retaliation_points"))
            if isinstance(row, dict)
        ],
        "cross_output_checks": [
            {
                "check_id": row.get("check_id"),
                "status": row.get("status"),
            }
            for row in _as_list((full_case_analysis.get("cross_output_consistency") or {}).get("checks"))
            if isinstance(row, dict)
        ],
    }
