"""Coverage-ledger helpers for case-analysis payloads."""

from __future__ import annotations

from typing import Any

from .case_analysis_common import as_dict, as_list
from .case_analysis_coverage_stages import build_context, coverage_row, coverage_summary
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
    context = build_context(matter_evidence_index, master_chronology, lawyer_issue_matrix, message_appendix)
    bundle = as_dict(multi_source_case_bundle)
    rows = [
        coverage_row(source, context)
        for source in as_list(bundle.get("sources"))
        if isinstance(source, dict) and source.get("source_id")
    ]
    summary = coverage_summary(rows, params.review_mode)
    uncovered_ids = summary.pop("uncovered_ids")
    return {
        "version": "1",
        "review_mode": params.review_mode,
        "source_scope": params.source_scope,
        "summary": summary,
        "rows": rows,
        "uncovered_ingestible_source_ids": uncovered_ids,
    }
