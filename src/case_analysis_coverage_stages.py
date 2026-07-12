"""Pure assembly stages for matter coverage ledgers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .case_analysis_common import as_dict, as_list


@dataclass(frozen=True, slots=True)
class CoverageContext:
    evidence: dict[str, Any]
    chronology: dict[str, Any]
    issues: dict[str, Any]
    appendix: dict[str, Any]
    stage_source_ids: dict[str, set[str]]


def build_context(evidence: Any, chronology: Any, issues: Any, appendix: Any) -> CoverageContext:
    payloads = tuple(as_dict(value) for value in (evidence, chronology, issues, appendix))
    evidence_payload, chronology_payload, issue_payload, appendix_payload = payloads
    return CoverageContext(
        evidence=evidence_payload,
        chronology=chronology_payload,
        issues=issue_payload,
        appendix=appendix_payload,
        stage_source_ids=_stage_source_ids(evidence_payload, chronology_payload, issue_payload, appendix_payload),
    )


def _stage_source_ids(
    evidence: dict[str, Any], chronology: dict[str, Any], issues: dict[str, Any], appendix: dict[str, Any]
) -> dict[str, set[str]]:
    return {
        "in_evidence_index": {str(row.get("source_id")) for row in _dict_rows(evidence, "rows") if row.get("source_id")},
        "in_chronology": {
            str(source_id)
            for row in _dict_rows(chronology, "entries")
            for source_id in as_list(as_dict(row.get("source_linkage")).get("source_ids"))
            if str(source_id).strip()
        },
        "in_issue_matrix": _issue_source_ids(_dict_rows(issues, "rows")),
        "in_message_appendix": {f"email:{row.get('uid')}" for row in _dict_rows(appendix, "rows") if row.get("uid")},
    }


def _dict_rows(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    return [row for row in as_list(payload.get(key)) if isinstance(row, dict)]


def _issue_source_ids(rows: list[dict[str, Any]]) -> set[str]:
    source_ids: set[str] = set()
    for row in rows:
        source_ids.update(str(value) for value in as_list(row.get("supporting_source_ids")) if str(value).strip())
        source_ids.update(str(doc.get("source_id")) for doc in _dict_rows(row, "strongest_documents") if doc.get("source_id"))
    return source_ids


def coverage_row(source: dict[str, Any], context: CoverageContext) -> dict[str, Any]:
    source_id = str(source.get("source_id") or "")
    support = as_dict(source.get("documentary_support"))
    support_level = str(as_dict(support.get("format_profile")).get("support_level") or "")
    quality_rank = str(as_dict(support.get("extraction_quality")).get("quality_rank") or "")
    text_available = bool(as_dict(source.get("source_weighting")).get("text_available"))
    flags = {key: source_id in values for key, values in context.stage_source_ids.items()}
    status, reason = _analysis_status(any(flags.values()), support_level, quality_rank, text_available)
    return {
        "source_id": source_id,
        "source_type": str(source.get("source_type") or ""),
        "document_kind": str(source.get("document_kind") or ""),
        "support_level": support_level,
        "quality_rank": quality_rank,
        "text_available": text_available,
        "analysis_status": status,
        "status_reason": reason,
        "stage_flags": _stage_flags(source, flags, support_level, text_available),
        "lineage": _lineage(source_id, context),
    }


def _analysis_status(analyzed: bool, support_level: str, quality_rank: str, text_available: bool) -> tuple[str, str]:
    if analyzed:
        return "linked", "This source is linked into at least one downstream legal-support product."
    if support_level == "unsupported":
        return "unsupported_reference_only", "This source is present, but the current pipeline marks it unsupported."
    if support_level == "reference_only" or quality_rank == "low":
        return (
            "degraded_unlinked",
            "This source is present, but its extraction quality is still too weak for strong downstream use.",
        )
    if text_available:
        return "ingested_not_yet_linked", "This source has usable text but has not yet been linked into a downstream product."
    return "metadata_only", "Only metadata or weak reference information is currently available for this source."


def _stage_flags(source: dict[str, Any], flags: dict[str, bool], support_level: str, text_available: bool) -> dict[str, bool]:
    chunked = bool(as_dict(source.get("document_locator")).get("chunk_id") or str(source.get("snippet") or "").strip())
    return {
        "supplied": True,
        "ingested": True,
        "extracted": text_available or support_level != "unsupported",
        "chunked": chunked,
        "cited": flags["in_evidence_index"],
        "linked_to_chronology": flags["in_chronology"],
        "linked_to_issue_matrix": flags["in_issue_matrix"],
        "linked_to_message_appendix": flags["in_message_appendix"],
        "linked_to_export": False,
    }


def _lineage(source_id: str, context: CoverageContext) -> dict[str, Any]:
    return {
        "evidence_index_exhibit_ids": _exhibit_ids(source_id, context.evidence),
        "chronology_entry_ids": _chronology_ids(source_id, context.chronology),
        "issue_ids": [
            str(row.get("issue_id"))
            for row in _dict_rows(context.issues, "rows")
            if _issue_has_source(row, source_id) and row.get("issue_id")
        ],
        "message_uids": _message_uids(source_id, context.appendix),
        "export_ids": [],
    }


def _exhibit_ids(source_id: str, evidence: dict[str, Any]) -> list[str]:
    return [
        str(row.get("exhibit_id"))
        for row in _dict_rows(evidence, "rows")
        if str(row.get("source_id") or "") == source_id and row.get("exhibit_id")
    ]


def _chronology_ids(source_id: str, chronology: dict[str, Any]) -> list[str]:
    return [
        str(row.get("chronology_id"))
        for row in _dict_rows(chronology, "entries")
        if source_id in as_list(as_dict(row.get("source_linkage")).get("source_ids")) and row.get("chronology_id")
    ]


def _message_uids(source_id: str, appendix: dict[str, Any]) -> list[str]:
    return [
        str(row.get("uid")) for row in _dict_rows(appendix, "rows") if f"email:{row.get('uid')}" == source_id and row.get("uid")
    ]


def _issue_has_source(row: dict[str, Any], source_id: str) -> bool:
    direct = [str(value) for value in as_list(row.get("supporting_source_ids")) if str(value).strip()]
    documents = [str(doc.get("source_id") or "") for doc in _dict_rows(row, "strongest_documents")]
    return source_id in direct or source_id in documents


def coverage_summary(rows: list[dict[str, Any]], review_mode: str) -> dict[str, Any]:
    categories = {
        name: [row for row in rows if row["analysis_status"] == status]
        for name, status in (
            ("linked", "linked"),
            ("degraded", "degraded_unlinked"),
            ("unsupported", "unsupported_reference_only"),
        )
    }
    uncovered = [
        row
        for row in rows
        if row["analysis_status"] in {"ingested_not_yet_linked", "metadata_only"} and row["support_level"] != "unsupported"
    ]
    coverage_status = (
        "complete"
        if review_mode == "exhaustive_matter_review" and not uncovered
        else "partial"
        if review_mode == "exhaustive_matter_review"
        else "best_effort"
    )
    return {
        "coverage_status": coverage_status,
        "total_source_count": len(rows),
        "linked_source_count": len(categories["linked"]),
        "degraded_source_count": len(categories["degraded"]),
        "unsupported_source_count": len(categories["unsupported"]),
        "uncovered_ingestible_source_count": len(uncovered),
        "stage_counts": _stage_counts(rows),
        "uncovered_ids": [row["source_id"] for row in uncovered],
    }


def _stage_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    keys = ("extracted", "chunked", "cited", "linked_to_chronology", "linked_to_issue_matrix", "linked_to_message_appendix")
    return {
        "supplied": len(rows),
        "ingested": len(rows),
        **{key: sum(bool(as_dict(row.get("stage_flags")).get(key)) for row in rows) for key in keys},
    }
