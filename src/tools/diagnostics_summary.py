"""Summary and artifact-selection helpers for diagnostics tools."""
# pylint: disable=too-many-arguments,too-many-branches,too-many-locals,too-many-statements

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def qa_eval_report_candidates_impl(repo_root: Callable[[], Path]) -> list[Path]:
    """Return candidate AQ eval report artifact paths in preferred order."""
    docs_agent = repo_root() / "docs" / "agent"
    preferred = [
        docs_agent / "qa_eval_report.core.captured.json",
        docs_agent / "qa_eval_report.core.live.json",
    ]
    extras = sorted(docs_agent.glob("qa_eval_report*.json"))
    seen: set[Path] = set()
    ordered: list[Path] = []
    for path in [*preferred, *extras]:
        if path not in seen:
            ordered.append(path)
            seen.add(path)
    return ordered


def qa_eval_remediation_candidates_impl(repo_root: Callable[[], Path]) -> list[Path]:
    """Return candidate AQ remediation-summary artifact paths in preferred order."""
    docs_agent = repo_root() / "docs" / "agent"
    preferred = [
        docs_agent / "qa_eval_remediation.live_expanded.live.json",
        docs_agent / "qa_eval_remediation.core.live.json",
    ]
    extras = sorted(docs_agent.glob("qa_eval_remediation*.json"))
    seen: set[Path] = set()
    ordered: list[Path] = []
    for path in [*preferred, *extras]:
        if path not in seen:
            ordered.append(path)
            seen.add(path)
    return ordered


def inferred_thread_prevalence_candidates_impl(repo_root: Callable[[], Path]) -> list[Path]:
    """Return candidate natural inferred-thread prevalence artifact paths."""
    docs_agent = repo_root() / "docs" / "agent"
    preferred = [docs_agent / "qa_eval_inferred_thread_prevalence.live.json"]
    extras = sorted(docs_agent.glob("qa_eval_inferred_thread_prevalence*.json"))
    seen: set[Path] = set()
    ordered: list[Path] = []
    for path in [*preferred, *extras]:
        if path not in seen:
            ordered.append(path)
            seen.add(path)
    return ordered


def load_eval_report_impl(path: Path, *, repo_root: Callable[[], Path]) -> tuple[str, dict[str, Any]] | None:
    """Load an AQ eval report from a JSON file.

    Args:
        path: Path to the eval report JSON file.
        repo_root: Callable returning the repository root Path.

    Returns:
        A tuple of (source_report, report_dict), or None if the file
        could not be loaded or has no valid summary.
    """
    try:
        raw = path.read_text(encoding="utf-8")
        report = json.loads(raw)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("AQ eval report could not be loaded from %s", path, exc_info=True)
        return None
    summary = report.get("summary")
    if not isinstance(summary, dict):
        return None
    try:
        source_report = str(path.relative_to(repo_root()))
    except ValueError:
        source_report = str(path)
    return source_report, report


def load_remediation_report_impl(path: Path, *, repo_root: Callable[[], Path]) -> tuple[str, dict[str, Any]] | None:
    """Load an AQ remediation report from a JSON file.

    Args:
        path: Path to the remediation report JSON file.
        repo_root: Callable returning the repository root Path.

    Returns:
        A tuple of (source_report, report_dict), or None if the file
        could not be loaded or is not a valid dict.
    """
    try:
        raw = path.read_text(encoding="utf-8")
        report = json.loads(raw)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("AQ remediation report could not be loaded from %s", path, exc_info=True)
        return None
    if not isinstance(report, dict):
        return None
    try:
        source_report = str(path.relative_to(repo_root()))
    except ValueError:
        source_report = str(path)
    return source_report, report


def load_inferred_thread_prevalence_impl(path: Path, *, repo_root: Callable[[], Path]) -> tuple[str, dict[str, Any]] | None:
    """Load an inferred-thread prevalence report from a JSON file.

    Only returns reports with artifact_type "natural_inferred_thread_prevalence".

    Args:
        path: Path to the prevalence report JSON file.
        repo_root: Callable returning the repository root Path.

    Returns:
        A tuple of (source_report, report_dict), or None if the file
        could not be loaded, is not a dict, or has the wrong artifact_type.
    """
    try:
        raw = path.read_text(encoding="utf-8")
        report = json.loads(raw)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("AQ prevalence report could not be loaded from %s", path, exc_info=True)
        return None
    if not isinstance(report, dict):
        return None
    if report.get("artifact_type") != "natural_inferred_thread_prevalence":
        return None
    try:
        source_report = str(path.relative_to(repo_root()))
    except ValueError:
        source_report = str(path)
    return source_report, report


def scored_metric_rate_impl(metric: dict[str, Any], *, rate: Callable[[int, int], float]) -> dict[str, Any]:
    """Return a scored metric with pass-rate semantics."""
    scorable = int(metric.get("scorable") or 0)
    passed = int(metric.get("passed") or 0)
    failed = int(metric.get("failed") or 0)
    return {
        "scorable": scorable,
        "passed": passed,
        "failed": failed,
        "pass_rate": rate(passed, scorable),
    }


def prefer_specialized_summary_impl(
    *,
    current_scorable: int,
    current_source_report: str,
    candidate_scorable: int,
    candidate_source_report: str,
) -> bool:
    """Return whether a specialized metric summary should replace the current one."""
    if candidate_scorable <= 0:
        return False
    if current_scorable <= 0:
        return True
    current_is_live = current_source_report.endswith(".live.json")
    candidate_is_live = candidate_source_report.endswith(".live.json")
    if current_is_live != candidate_is_live:
        return candidate_is_live
    return False


def answer_task_readiness_summary_impl(
    *,
    qa_eval_report_candidates: Callable[[], list[Path]],
    load_eval_report: Callable[[Path], tuple[str, dict[str, Any]] | None],
    qa_eval_remediation_candidates: Callable[[], list[Path]],
    load_remediation_report: Callable[[Path], tuple[str, dict[str, Any]] | None],
    inferred_thread_prevalence_candidates: Callable[[], list[Path]],
    load_inferred_thread_prevalence: Callable[[Path], tuple[str, dict[str, Any]] | None],
    prefer_specialized_summary: Callable[..., bool],
    scored_metric_rate: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    """Return operator-visible answer-task readiness metrics from saved AQ eval reports."""
    reports = _load_candidate_reports(qa_eval_report_candidates, load_eval_report)
    if not reports:
        return {}
    source_report, report = reports[0]
    summary = report.get("summary")
    if not isinstance(summary, dict):
        return {}
    selected = _select_specialized_summaries(reports, prefer_specialized_summary)
    info = _build_answer_summary(source_report, report, summary, selected, scored_metric_rate)
    _add_remediation_summary(info, qa_eval_remediation_candidates, load_remediation_report)
    _add_prevalence_summary(info, inferred_thread_prevalence_candidates, load_inferred_thread_prevalence)
    _add_investigation_readiness(info, selected["investigation"])
    return info


def _load_candidate_reports(candidates, loader) -> list[tuple[str, dict[str, Any]]]:
    return [loaded for path in candidates() if path.exists() for loaded in [loader(path)] if loaded]


def _select_specialized_summaries(reports, prefer) -> dict[str, tuple[str, dict[str, Any], dict[str, Any]]]:
    metrics = {
        "quote": "quote_attribution_precision",
        "thread": "thread_group_id_match",
        "attachment_ocr": "attachment_ocr_text_evidence_success",
        "long_thread": "long_thread_answer_present",
        "investigation": "case_bundle_present",
        "behavioral": "behavior_tag_coverage",
    }
    source, first_report = reports[0]
    first_summary = first_report["summary"]
    selected = dict.fromkeys(metrics, (source, first_summary, first_report))
    for candidate_source, candidate_report in reports:
        candidate_summary = candidate_report.get("summary")
        if not isinstance(candidate_summary, dict):
            continue
        for name, metric in metrics.items():
            current_source, current_summary, _ = selected[name]
            if prefer(
                current_scorable=_metric_scorable(current_summary, metric),
                current_source_report=current_source,
                candidate_scorable=_metric_scorable(candidate_summary, metric),
                candidate_source_report=candidate_source,
            ):
                selected[name] = (candidate_source, candidate_summary, candidate_report)
    return selected


def _metric_scorable(summary: dict[str, Any], metric: str) -> int:
    return int((summary.get(metric) or {}).get("scorable") or 0)


def _build_answer_summary(source, report, summary, selected, rate_metric) -> dict[str, Any]:
    info = {
        "source_report": source,
        "total_cases": int(summary.get("total_cases") or report.get("total_cases") or 0),
        "bucket_counts": dict(summary.get("bucket_counts") or {}),
        "top_1_correctness": rate_metric(dict(summary.get("top_1_correctness") or {})),
        "support_uid_hit_top_3": rate_metric(dict(summary.get("support_uid_hit_top_3") or {})),
        "evidence_precision": dict(summary.get("evidence_precision") or {}),
        "attachment_answer_success": rate_metric(dict(summary.get("attachment_answer_success") or {})),
        "attachment_text_evidence_success": rate_metric(dict(summary.get("attachment_text_evidence_success") or {})),
        "confidence_calibration_match": rate_metric(dict(summary.get("confidence_calibration_match") or {})),
        "weak_evidence_explained": rate_metric(dict(summary.get("weak_evidence_explained") or {})),
    }
    info.update(_specialized_answer_metrics(selected, rate_metric))
    return info


def _specialized_answer_metrics(selected, rate_metric) -> dict[str, Any]:
    attachment_source, attachment, _ = selected["attachment_ocr"]
    thread_source, thread, _ = selected["thread"]
    long_source, long_thread, _ = selected["long_thread"]
    investigation_source, investigation, _ = selected["investigation"]
    behavior_source, behavior, _ = selected["behavioral"]
    quote_source, quote, _ = selected["quote"]
    return {
        "attachment_ocr_text_evidence_success": {
            "source_report": attachment_source,
            **rate_metric(dict(attachment.get("attachment_ocr_text_evidence_success") or {})),
        },
        "thread_group_id_match": {"source_report": thread_source, **rate_metric(dict(thread.get("thread_group_id_match") or {}))},
        "thread_group_source_match": {
            "source_report": thread_source,
            **rate_metric(dict(thread.get("thread_group_source_match") or {})),
        },
        "long_thread_answer_present": {
            "source_report": long_source,
            **rate_metric(dict(long_thread.get("long_thread_answer_present") or {})),
        },
        "long_thread_structure_preserved": {
            "source_report": long_source,
            **rate_metric(dict(long_thread.get("long_thread_structure_preserved") or {})),
        },
        "investigation_case_analysis": _investigation_metrics(investigation_source, investigation, rate_metric),
        "behavioral_analysis_benchmark": _behavioral_metrics(behavior_source, behavior, rate_metric),
        "quote_attribution_precision": _quote_metric(quote_source, quote, "quote_attribution_precision"),
        "quote_attribution_coverage": _quote_metric(quote_source, quote, "quote_attribution_coverage"),
    }


def _investigation_metrics(source, summary, rate_metric) -> dict[str, Any]:
    return {
        "source_report": source,
        "case_bundle_present": rate_metric(dict(summary.get("case_bundle_present") or {})),
        "investigation_blocks_present": rate_metric(dict(summary.get("investigation_blocks_present") or {})),
        "case_bundle_support_uid_hit": rate_metric(dict(summary.get("case_bundle_support_uid_hit") or {})),
        "case_bundle_support_uid_recall": dict(summary.get("case_bundle_support_uid_recall") or {}),
        "multi_source_source_types_match": rate_metric(dict(summary.get("multi_source_source_types_match") or {})),
    }


def _behavioral_metrics(source, summary, rate_metric) -> dict[str, Any]:
    return {
        "available": _metric_scorable(summary, "behavior_tag_coverage") > 0,
        "source_report": source,
        "chronology_uid_hit": rate_metric(dict(summary.get("chronology_uid_hit") or {})),
        "chronology_uid_recall": dict(summary.get("chronology_uid_recall") or {}),
        "behavior_tag_coverage": dict(summary.get("behavior_tag_coverage") or {}),
        "behavior_tag_precision": dict(summary.get("behavior_tag_precision") or {}),
        "counter_indicator_quality": dict(summary.get("counter_indicator_quality") or {}),
        "overclaim_guard_match": rate_metric(dict(summary.get("overclaim_guard_match") or {})),
        "report_completeness": rate_metric(dict(summary.get("report_completeness") or {})),
    }


def _quote_metric(source, summary, metric) -> dict[str, Any]:
    return {"available": _metric_scorable(summary, metric) > 0, "source_report": source, **dict(summary.get(metric) or {})}


def _add_remediation_summary(info, candidates, loader) -> None:
    reports = _load_candidate_reports(candidates, loader)
    if reports:
        source, report = reports[0]
        info["remediation_summary"] = {
            "source_report": source,
            "ranked_categories": report.get("failure_taxonomy", {}).get("ranked_categories", []),
            "immediate_next_targets": report.get("immediate_next_targets", []),
        }


def _add_prevalence_summary(info, candidates, loader) -> None:
    reports = _load_candidate_reports(candidates, loader)
    if not reports:
        return
    source, report = reports[0]
    int_fields = (
        "sample_email_count",
        "emails_with_inferred_thread_id",
        "emails_with_inferred_parent_uid",
        "inferred_only_email_count",
        "distinct_inferred_thread_ids",
    )
    float_fields = ("inferred_thread_id_rate", "inferred_parent_uid_rate", "inferred_only_email_rate")
    payload = {
        "source_report": source,
        **{field: int(report.get(field) or 0) for field in int_fields},
        **{field: float(report.get(field) or 0.0) for field in float_fields},
    }
    payload.update({field: str(report.get(field) or "") for field in ("decision", "recommendation")})
    info["natural_inferred_thread_prevalence"] = payload


def _add_investigation_readiness(info, selection) -> None:
    source, _, report = selection
    readiness = report.get("investigation_corpus_readiness")
    if not isinstance(readiness, dict):
        return
    int_fields = (
        "case_scope_case_count",
        "expected_case_bundle_uid_count",
        "total_emails",
        "emails_with_segments_count",
        "attachment_email_count",
    )
    info["investigation_corpus_readiness"] = {
        "source_report": source,
        "live_backend": readiness.get("live_backend"),
        **{field: int(readiness.get(field) or 0) for field in int_fields},
        "corpus_populated": bool(readiness.get("corpus_populated")),
        "supports_case_analysis": bool(readiness.get("supports_case_analysis")),
        "known_blockers": [str(item) for item in readiness.get("known_blockers", [])],
    }


def qa_readiness_summary_impl(
    db,
    *,
    table_columns: Callable[[Any, str], set[str]],
    scalar_count: Callable[[Any, str], int],
    count_rows: Callable[[Any, str], dict[str, int]],
    rate: Callable[[int, int], float],
) -> dict[str, Any]:
    """Return corpus-level Q&A readiness metrics from existing stored surfaces."""
    columns = table_columns(db, "emails")
    if not columns:
        return {}

    total_emails = scalar_count(db, "SELECT COUNT(*) FROM emails")
    content_email_count = (
        scalar_count(db, "SELECT COUNT(*) FROM emails WHERE body_kind = 'content'") if "body_kind" in columns else 0
    )
    attachment_email_count = (
        scalar_count(db, "SELECT COUNT(*) FROM emails WHERE COALESCE(has_attachments, 0) != 0")
        if "has_attachments" in columns
        else 0
    )
    forensic_body_count = (
        scalar_count(
            db,
            """SELECT COUNT(*) FROM emails
               WHERE forensic_body_text IS NOT NULL AND forensic_body_text != ''""",
        )
        if "forensic_body_text" in columns
        else 0
    )
    raw_source_count = (
        scalar_count(
            db,
            """SELECT COUNT(*) FROM emails
               WHERE raw_source IS NOT NULL AND raw_source != ''""",
        )
        if "raw_source" in columns
        else 0
    )
    emails_with_segments_count = scalar_count(db, "SELECT COUNT(DISTINCT email_uid) FROM message_segments")
    reply_or_forward_count = (
        scalar_count(
            db,
            """SELECT COUNT(*) FROM emails
               WHERE email_type IN ('reply', 'forward')""",
        )
        if "email_type" in columns
        else 0
    )
    reply_context_recovered_count = (
        scalar_count(
            db,
            """SELECT COUNT(*) FROM emails
               WHERE reply_context_from IS NOT NULL AND reply_context_from != ''""",
        )
        if "reply_context_from" in columns
        else 0
    )
    canonical_thread_linked_count = (
        scalar_count(
            db,
            """SELECT COUNT(*) FROM emails
               WHERE
                   (in_reply_to IS NOT NULL AND in_reply_to != '')
                   OR (references_json IS NOT NULL AND references_json != '' AND references_json != '[]')""",
        )
        if {"in_reply_to", "references_json"}.issubset(columns)
        else 0
    )
    inferred_thread_linked_count = (
        scalar_count(
            db,
            """SELECT COUNT(*) FROM emails
               WHERE inferred_parent_uid IS NOT NULL AND inferred_parent_uid != ''""",
        )
        if "inferred_parent_uid" in columns
        else 0
    )
    top_body_empty_reasons = _top_body_empty_reasons(db, count_rows)

    return {
        "total_emails": total_emails,
        "content_email_count": content_email_count,
        "content_email_rate": rate(content_email_count, total_emails),
        "attachment_email_count": attachment_email_count,
        "attachment_email_rate": rate(attachment_email_count, total_emails),
        "forensic_body_count": forensic_body_count,
        "forensic_body_rate": rate(forensic_body_count, total_emails),
        "raw_source_count": raw_source_count,
        "raw_source_rate": rate(raw_source_count, total_emails),
        "emails_with_segments_count": emails_with_segments_count,
        "segment_provenance_rate": rate(emails_with_segments_count, total_emails),
        "reply_or_forward_count": reply_or_forward_count,
        "reply_context_recovered_count": reply_context_recovered_count,
        "reply_context_recovery_rate": rate(reply_context_recovered_count, reply_or_forward_count),
        "canonical_thread_linked_count": canonical_thread_linked_count,
        "canonical_thread_link_rate": rate(canonical_thread_linked_count, total_emails),
        "inferred_thread_linked_count": inferred_thread_linked_count,
        "inferred_thread_link_rate": rate(inferred_thread_linked_count, total_emails),
        "top_body_empty_reasons": top_body_empty_reasons,
    }


def _top_body_empty_reasons(db, count_rows) -> list[dict[str, Any]]:
    rows = count_rows(
        db,
        """SELECT body_empty_reason AS label, COUNT(*) AS count
           FROM emails WHERE body_empty_reason IS NOT NULL AND body_empty_reason != ''
           GROUP BY body_empty_reason ORDER BY count DESC, label ASC LIMIT 5""",
    )
    return [{"label": label, "count": count} for label, count in rows.items()]
