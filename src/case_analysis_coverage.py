"""Coverage-ledger helpers for case-analysis payloads."""

from __future__ import annotations

from typing import Any

from .case_analysis_common import as_dict, as_list
from .mcp_models import EmailCaseAnalysisInput


def matter_coverage_ledger(
    *,
    params: EmailCaseAnalysisInput,
    multi_source_case_bundle: dict[str, Any] | None,
    matter_evidence_index: dict[str, Any] | None,
    master_chronology: dict[str, Any] | None,
    lawyer_issue_matrix: dict[str, Any] | None,
    message_appendix: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return coverage and lineage accounting for one matter-analysis run."""
    bundle = as_dict(multi_source_case_bundle)
    sources = [row for row in as_list(bundle.get("sources")) if isinstance(row, dict)]
    evidence_source_ids = {
        str(row.get("source_id") or "")
        for row in as_list(as_dict(matter_evidence_index).get("rows"))
        if isinstance(row, dict) and str(row.get("source_id") or "")
    }
    chronology_source_ids = {
        str(source_id)
        for row in as_list(as_dict(master_chronology).get("entries"))
        if isinstance(row, dict)
        for source_id in as_list(as_dict(row.get("source_linkage")).get("source_ids"))
        if str(source_id).strip()
    }
    issue_source_ids = {
        str(source_id)
        for row in as_list(as_dict(lawyer_issue_matrix).get("rows"))
        if isinstance(row, dict)
        for source_id in (
            [
                str(document.get("source_id") or "")
                for document in as_list(row.get("strongest_documents"))
                if isinstance(document, dict) and str(document.get("source_id") or "")
            ]
            + [str(source_id) for source_id in as_list(row.get("supporting_source_ids")) if str(source_id).strip()]
        )
        if source_id
    }
    message_source_ids = {
        f"email:{uid}"
        for row in as_list(as_dict(message_appendix).get("rows"))
        if isinstance(row, dict)
        for uid in [str(row.get("uid") or "")]
        if uid
    }
    rows: list[dict[str, Any]] = []
    for source in sources:
        source_id = str(source.get("source_id") or "")
        if not source_id:
            continue
        documentary_support = as_dict(source.get("documentary_support"))
        format_profile = as_dict(documentary_support.get("format_profile"))
        extraction_quality = as_dict(documentary_support.get("extraction_quality"))
        stage_flags = {
            "in_evidence_index": source_id in evidence_source_ids,
            "in_chronology": source_id in chronology_source_ids,
            "in_issue_matrix": source_id in issue_source_ids,
            "in_message_appendix": source_id in message_source_ids,
        }
        analyzed = any(stage_flags.values())
        support_level = str(format_profile.get("support_level") or "")
        quality_rank = str(extraction_quality.get("quality_rank") or "")
        text_available = bool(as_dict(source.get("source_weighting")).get("text_available"))
        extracted = text_available or support_level not in {"unsupported"}
        chunked = bool(as_dict(source.get("document_locator")).get("chunk_id") or str(source.get("snippet") or "").strip())
        lineage = {
            "evidence_index_exhibit_ids": [
                str(row.get("exhibit_id") or "")
                for row in as_list(as_dict(matter_evidence_index).get("rows"))
                if isinstance(row, dict) and str(row.get("source_id") or "") == source_id and str(row.get("exhibit_id") or "")
            ],
            "chronology_entry_ids": [
                str(row.get("chronology_id") or "")
                for row in as_list(as_dict(master_chronology).get("entries"))
                if isinstance(row, dict)
                and source_id in as_list(as_dict(row.get("source_linkage")).get("source_ids"))
                and str(row.get("chronology_id") or "")
            ],
            "issue_ids": [
                str(row.get("issue_id") or "")
                for row in as_list(as_dict(lawyer_issue_matrix).get("rows"))
                if isinstance(row, dict)
                and (
                    source_id in [str(item) for item in as_list(row.get("supporting_source_ids")) if str(item).strip()]
                    or source_id
                    in [
                        str(document.get("source_id") or "")
                        for document in as_list(row.get("strongest_documents"))
                        if isinstance(document, dict)
                    ]
                )
                and str(row.get("issue_id") or "")
            ],
            "message_uids": [
                str(row.get("uid") or "")
                for row in as_list(as_dict(message_appendix).get("rows"))
                if isinstance(row, dict) and f"email:{row.get('uid')}" == source_id and str(row.get("uid") or "")
            ],
            "export_ids": [],
        }
        if analyzed:
            analysis_status = "linked"
            status_reason = "This source is linked into at least one downstream legal-support product."
        elif support_level == "unsupported":
            analysis_status = "unsupported_reference_only"
            status_reason = "This source is present, but the current pipeline marks it unsupported."
        elif support_level == "reference_only" or quality_rank == "low":
            analysis_status = "degraded_unlinked"
            status_reason = "This source is present, but its extraction quality is still too weak for strong downstream use."
        elif text_available:
            analysis_status = "ingested_not_yet_linked"
            status_reason = "This source has usable text but has not yet been linked into a downstream product."
        else:
            analysis_status = "metadata_only"
            status_reason = "Only metadata or weak reference information is currently available for this source."
        rows.append(
            {
                "source_id": source_id,
                "source_type": str(source.get("source_type") or ""),
                "document_kind": str(source.get("document_kind") or ""),
                "support_level": support_level,
                "quality_rank": quality_rank,
                "text_available": text_available,
                "analysis_status": analysis_status,
                "status_reason": status_reason,
                "stage_flags": {
                    "supplied": True,
                    "ingested": True,
                    "extracted": extracted,
                    "chunked": chunked,
                    "cited": stage_flags["in_evidence_index"],
                    "linked_to_chronology": stage_flags["in_chronology"],
                    "linked_to_issue_matrix": stage_flags["in_issue_matrix"],
                    "linked_to_message_appendix": stage_flags["in_message_appendix"],
                    "linked_to_export": False,
                },
                "lineage": lineage,
            }
        )
    uncovered_ingestible = [
        row
        for row in rows
        if row["analysis_status"] in {"ingested_not_yet_linked", "metadata_only"} and row["support_level"] not in {"unsupported"}
    ]
    degraded_rows = [row for row in rows if row["analysis_status"] == "degraded_unlinked"]
    unsupported_rows = [row for row in rows if row["analysis_status"] == "unsupported_reference_only"]
    linked_rows = [row for row in rows if row["analysis_status"] == "linked"]
    coverage_status = "best_effort"
    if params.review_mode == "exhaustive_matter_review":
        coverage_status = "complete" if not uncovered_ingestible else "partial"
    return {
        "version": "1",
        "review_mode": params.review_mode,
        "source_scope": params.source_scope,
        "summary": {
            "coverage_status": coverage_status,
            "total_source_count": len(rows),
            "linked_source_count": len(linked_rows),
            "degraded_source_count": len(degraded_rows),
            "unsupported_source_count": len(unsupported_rows),
            "uncovered_ingestible_source_count": len(uncovered_ingestible),
            "stage_counts": {
                "supplied": len(rows),
                "ingested": len(rows),
                "extracted": sum(1 for row in rows if bool(as_dict(row.get("stage_flags")).get("extracted"))),
                "chunked": sum(1 for row in rows if bool(as_dict(row.get("stage_flags")).get("chunked"))),
                "cited": sum(1 for row in rows if bool(as_dict(row.get("stage_flags")).get("cited"))),
                "linked_to_chronology": sum(
                    1 for row in rows if bool(as_dict(row.get("stage_flags")).get("linked_to_chronology"))
                ),
                "linked_to_issue_matrix": sum(
                    1 for row in rows if bool(as_dict(row.get("stage_flags")).get("linked_to_issue_matrix"))
                ),
                "linked_to_message_appendix": sum(
                    1 for row in rows if bool(as_dict(row.get("stage_flags")).get("linked_to_message_appendix"))
                ),
            },
        },
        "rows": rows,
        "uncovered_ingestible_source_ids": [row["source_id"] for row in uncovered_ingestible],
    }
