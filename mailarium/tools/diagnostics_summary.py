"""Summary and artifact-selection helpers for diagnostics tools."""
# pylint: disable=too-many-arguments,too-many-branches,too-many-locals,too-many-statements

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _ordered_unique_paths(preferred: list[Path], extras: list[Path]) -> list[Path]:
    """Combine preferred and discovered artifact paths without reordering duplicates."""
    seen: set[Path] = set()
    ordered: list[Path] = []
    for path in [*preferred, *extras]:
        if path not in seen:
            ordered.append(path)
            seen.add(path)
    return ordered


def qa_eval_report_candidates_impl(repo_root: Callable[[], Path]) -> list[Path]:
    """Return QA-evaluation report artifact paths in preferred order."""
    live_reports = repo_root() / "private" / "tests" / "results" / "qa_eval"
    qa_eval_fixtures = repo_root() / "tests" / "fixtures" / "qa_eval"
    preferred = [
        live_reports / "qa_eval_report.core.live.json",
        qa_eval_fixtures / "qa_eval_report.core.captured.json",
    ]
    extras = [*sorted(live_reports.glob("qa_eval_report*.json")), *sorted(qa_eval_fixtures.glob("qa_eval_report*.json"))]
    return _ordered_unique_paths(preferred, extras)


def qa_eval_remediation_candidates_impl(repo_root: Callable[[], Path]) -> list[Path]:
    """Return QA-evaluation remediation-summary paths in preferred order."""
    live_reports = repo_root() / "private" / "tests" / "results" / "qa_eval"
    preferred = [
        live_reports / "qa_eval_remediation.core.live.json",
    ]
    extras = sorted(live_reports.glob("qa_eval_remediation*.json"))
    return _ordered_unique_paths(preferred, extras)


def inferred_thread_prevalence_candidates_impl(repo_root: Callable[[], Path]) -> list[Path]:
    """Return report paths for natural inferred-thread prevalence."""
    live_reports = repo_root() / "private" / "tests" / "results" / "qa_eval"
    preferred = [live_reports / "qa_eval_inferred_thread_prevalence.live.json"]
    extras = sorted(live_reports.glob("qa_eval_inferred_thread_prevalence*.json"))
    return _ordered_unique_paths(preferred, extras)


def load_eval_report_impl(path: Path, *, repo_root: Callable[[], Path]) -> tuple[str, dict[str, Any]] | None:
    """Load a QA-evaluation report from a JSON file.

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
    """Load a QA-evaluation remediation report from a JSON file.

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
    """Prefer a specialized metric summary only when it preserves stronger readiness evidence."""
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
    """Return operator-visible answer-task readiness metrics from saved QA-evaluation reports."""
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
    return info


def _load_candidate_reports(candidates, loader) -> list[tuple[str, dict[str, Any]]]:
    """Load candidate reports while preserving the caller's fallback behavior."""
    return [loaded for path in candidates() if path.exists() for loaded in [loader(path)] if loaded]


def _select_specialized_summaries(reports, prefer) -> dict[str, tuple[str, dict[str, Any], dict[str, Any]]]:
    """Select specialized summaries using the tool's deterministic policy."""
    metrics = {
        "quote": "quote_attribution_precision",
        "thread": "thread_group_id_match",
        "attachment_ocr": "attachment_ocr_text_evidence_success",
        "long_thread": "long_thread_answer_present",
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
    """Return the number of scorable cases recorded for a summary metric."""
    return int((summary.get(metric) or {}).get("scorable") or 0)


def _build_answer_summary(source, report, summary, selected, rate_metric) -> dict[str, Any]:
    """Create top-level readiness metrics from the selected QA-evaluation report."""
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
    """Extract attachment, thread, long-thread, and quote metrics with their source-report provenance."""
    attachment_source, attachment, _ = selected["attachment_ocr"]
    thread_source, thread, _ = selected["thread"]
    long_source, long_thread, _ = selected["long_thread"]
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
        "quote_attribution_precision": _quote_metric(quote_source, quote, "quote_attribution_precision"),
        "quote_attribution_coverage": _quote_metric(quote_source, quote, "quote_attribution_coverage"),
    }


def _quote_metric(source, summary, metric) -> dict[str, Any]:
    """Mark a quote metric available only when its report contains scorable cases."""
    return {"available": _metric_scorable(summary, metric) > 0, "source_report": source, **dict(summary.get(metric) or {})}


def _add_remediation_summary(info, candidates, loader) -> None:
    """Attach the first remediation report's categories and immediate targets, when available."""
    reports = _load_candidate_reports(candidates, loader)
    if reports:
        source, report = reports[0]
        info["remediation_summary"] = {
            "source_report": source,
            "ranked_categories": report.get("failure_taxonomy", {}).get("ranked_categories", []),
            "immediate_next_targets": report.get("immediate_next_targets", []),
        }


def _add_prevalence_summary(info, candidates, loader) -> None:
    """Attach normalized natural inferred-thread prevalence from the first available report."""
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
    """Return the five most frequent non-empty body-loss reasons from the archive."""
    rows = count_rows(
        db,
        """SELECT body_empty_reason AS label, COUNT(*) AS count
           FROM emails WHERE body_empty_reason IS NOT NULL AND body_empty_reason != ''
           GROUP BY body_empty_reason ORDER BY count DESC, label ASC LIMIT 5""",
    )
    return [{"label": label, "count": count} for label, count in rows.items()]
