"""Failure taxonomy and remediation helpers for generic QA evaluation."""

from __future__ import annotations

from typing import Any

from .qa_eval_cases import QuestionCase

_CHECKS = (
    ("support_uid_hit", "retrieval_recall", "failed", "missing_supported_hit"),
    ("support_source_id_hit", "retrieval_recall", "failed", "missing_source_grounding"),
    ("support_uid_recall", "retrieval_recall", "weak", "support_uid_recall_below_one"),
    ("support_source_id_recall", "retrieval_recall", "weak", "source_recall_below_one"),
    ("evidence_precision", "retrieval_recall", "weak", "evidence_precision_below_one"),
    ("ambiguity_match", "ambiguity_handling", "failed", "ambiguity_mismatch"),
    ("confidence_calibration_match", "ambiguity_handling", "failed", "confidence_mismatch"),
    ("attachment_answer_success", "attachment_extraction", "failed", "attachment_answer_failed"),
    ("attachment_text_evidence_success", "attachment_extraction", "weak", "weak_attachment_text_evidence"),
    ("attachment_ocr_text_evidence_success", "attachment_extraction", "weak", "weak_attachment_ocr_evidence"),
    ("weak_evidence_explained", "ambiguity_handling", "failed", "weak_evidence_unexplained"),
    ("quote_attribution_precision", "quote_attribution", "weak", "quote_precision_below_one"),
    ("quote_attribution_coverage", "quote_attribution", "weak", "quote_coverage_below_one"),
    ("thread_group_id_match", "threading", "failed", "thread_group_mismatch"),
    ("thread_group_source_match", "threading", "failed", "thread_source_mismatch"),
    ("long_thread_answer_present", "threading", "failed", "missing_long_thread_answer"),
    ("long_thread_structure_preserved", "threading", "failed", "missing_long_thread_structure"),
    ("answer_content_match", "answer_quality", "failed", "answer_content_mismatch"),
    ("forbidden_support_ids_excluded", "negative_controls", "failed", "forbidden_support_present"),
)


def _metric_failed(value: Any) -> bool:
    return value is False or (isinstance(value, (int, float)) and not isinstance(value, bool) and value < 1.0)


def _append_issue(
    flagged: dict[str, dict[str, Any]],
    *,
    category: str,
    severity: str,
    case_id: str,
    driver: str,
) -> None:
    """Record one failed or weak check in its category's aggregate."""
    entry = flagged.setdefault(
        category,
        {
            "category": category,
            "case_ids": set(),
            "failed_case_ids": set(),
            "weak_case_ids": set(),
            "drivers": set(),
        },
    )
    entry["case_ids"].add(case_id)
    entry[f"{severity}_case_ids"].add(case_id)
    entry["drivers"].add(driver)


def _finalize_category(entry: dict[str, Any]) -> dict[str, Any]:
    failed_ids = set(entry["failed_case_ids"])
    weak_ids = set(entry["weak_case_ids"]) - failed_ids
    case_ids = set(entry["case_ids"])
    return {
        "category": entry["category"],
        "flagged_cases": len(case_ids),
        "failed_cases": len(failed_ids),
        "weak_cases": len(weak_ids),
        "case_ids": sorted(case_ids),
        "drivers": sorted(entry["drivers"]),
    }


def build_failure_taxonomy(cases: list[QuestionCase], results: list[dict[str, Any]]) -> dict[str, Any]:
    """Group failed QA checks by category, severity, and their contributing cases."""
    known_ids = {case.id for case in cases}
    flagged: dict[str, dict[str, Any]] = {}
    for result in results:
        case_id = str(result.get("id") or "")
        if case_id not in known_ids:
            continue
        for metric, category, severity, driver in _CHECKS:
            value = result.get(metric)
            if value is not None and _metric_failed(value):
                _append_issue(
                    flagged,
                    category=category,
                    severity=severity,
                    case_id=case_id,
                    driver=driver,
                )
    ranked = [_finalize_category(entry) for entry in flagged.values()]
    ranked.sort(key=lambda item: (-item["failed_cases"], -item["weak_cases"], item["category"]))
    return {
        "total_flagged_cases": len({case_id for item in ranked for case_id in item["case_ids"]}),
        "categories": {item["category"]: item for item in ranked},
        "ranked_categories": ranked,
    }


def build_remediation_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Produce prioritized generic QA remediation targets from a saved report."""
    summary = report.get("summary")
    taxonomy = report.get("failure_taxonomy")
    if not isinstance(summary, dict) or not isinstance(taxonomy, dict):
        raise ValueError("report must contain summary and failure_taxonomy objects")
    categories = [item for item in taxonomy.get("ranked_categories", []) if isinstance(item, dict)]
    targets = [
        {
            **item,
            "priority_score": int(item.get("failed_cases") or 0) * 3 + int(item.get("weak_cases") or 0) * 2,
        }
        for item in categories
    ]
    targets.sort(key=lambda item: (-item["priority_score"], str(item.get("category") or "")))
    return {
        "total_cases": int(summary.get("total_cases") or 0),
        "bucket_counts": dict(summary.get("bucket_counts") or {}),
        "failure_taxonomy": {
            "total_flagged_cases": int(taxonomy.get("total_flagged_cases") or 0),
            "ranked_categories": targets,
        },
        "immediate_next_targets": targets[:3],
    }
