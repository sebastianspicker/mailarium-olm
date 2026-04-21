"""Summary and artifact-selection helpers for diagnostics tools."""

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
    try:
        raw = path.read_text(encoding="utf-8")
        report = json.loads(raw)
    except Exception:
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
    try:
        raw = path.read_text(encoding="utf-8")
        report = json.loads(raw)
    except Exception:
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
    try:
        raw = path.read_text(encoding="utf-8")
        report = json.loads(raw)
    except Exception:
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
    loaded_reports = [
        loaded for path in qa_eval_report_candidates() if path.exists() for loaded in [load_eval_report(path)] if loaded
    ]
    if not loaded_reports:
        return {}

    source_report, report = loaded_reports[0]
    summary = report.get("summary")
    if not isinstance(summary, dict):
        return {}
    quote_summary = summary
    quote_source_report = source_report
    thread_summary = summary
    thread_source_report = source_report
    attachment_ocr_summary = summary
    attachment_ocr_source_report = source_report
    long_thread_summary = summary
    long_thread_source_report = source_report
    investigation_summary = summary
    investigation_source_report = source_report
    investigation_corpus_readiness = report.get("investigation_corpus_readiness")
    behavioral_summary = summary
    behavioral_source_report = source_report
    for candidate_source_report, candidate_report in loaded_reports:
        candidate_summary = candidate_report.get("summary")
        if not isinstance(candidate_summary, dict):
            continue
        quote_scorable = int((candidate_summary.get("quote_attribution_precision") or {}).get("scorable") or 0)
        if prefer_specialized_summary(
            current_scorable=int((quote_summary.get("quote_attribution_precision") or {}).get("scorable") or 0),
            current_source_report=quote_source_report,
            candidate_scorable=quote_scorable,
            candidate_source_report=candidate_source_report,
        ):
            quote_summary = candidate_summary
            quote_source_report = candidate_source_report
        thread_scorable = int((candidate_summary.get("thread_group_id_match") or {}).get("scorable") or 0)
        if prefer_specialized_summary(
            current_scorable=int((thread_summary.get("thread_group_id_match") or {}).get("scorable") or 0),
            current_source_report=thread_source_report,
            candidate_scorable=thread_scorable,
            candidate_source_report=candidate_source_report,
        ):
            thread_summary = candidate_summary
            thread_source_report = candidate_source_report
        attachment_ocr_scorable = int((candidate_summary.get("attachment_ocr_text_evidence_success") or {}).get("scorable") or 0)
        if prefer_specialized_summary(
            current_scorable=int((attachment_ocr_summary.get("attachment_ocr_text_evidence_success") or {}).get("scorable") or 0),
            current_source_report=attachment_ocr_source_report,
            candidate_scorable=attachment_ocr_scorable,
            candidate_source_report=candidate_source_report,
        ):
            attachment_ocr_summary = candidate_summary
            attachment_ocr_source_report = candidate_source_report
        long_thread_scorable = int((candidate_summary.get("long_thread_answer_present") or {}).get("scorable") or 0)
        if prefer_specialized_summary(
            current_scorable=int((long_thread_summary.get("long_thread_answer_present") or {}).get("scorable") or 0),
            current_source_report=long_thread_source_report,
            candidate_scorable=long_thread_scorable,
            candidate_source_report=candidate_source_report,
        ):
            long_thread_summary = candidate_summary
            long_thread_source_report = candidate_source_report
        investigation_scorable = int((candidate_summary.get("case_bundle_present") or {}).get("scorable") or 0)
        if prefer_specialized_summary(
            current_scorable=int((investigation_summary.get("case_bundle_present") or {}).get("scorable") or 0),
            current_source_report=investigation_source_report,
            candidate_scorable=investigation_scorable,
            candidate_source_report=candidate_source_report,
        ):
            investigation_summary = candidate_summary
            investigation_source_report = candidate_source_report
            investigation_corpus_readiness = candidate_report.get("investigation_corpus_readiness")
        behavioral_scorable = int((candidate_summary.get("behavior_tag_coverage") or {}).get("scorable") or 0)
        if prefer_specialized_summary(
            current_scorable=int((behavioral_summary.get("behavior_tag_coverage") or {}).get("scorable") or 0),
            current_source_report=behavioral_source_report,
            candidate_scorable=behavioral_scorable,
            candidate_source_report=candidate_source_report,
        ):
            behavioral_summary = candidate_summary
            behavioral_source_report = candidate_source_report
    info = {
        "source_report": source_report,
        "total_cases": int(summary.get("total_cases") or report.get("total_cases") or 0),
        "bucket_counts": dict(summary.get("bucket_counts") or {}),
        "top_1_correctness": scored_metric_rate(dict(summary.get("top_1_correctness") or {})),
        "support_uid_hit_top_3": scored_metric_rate(dict(summary.get("support_uid_hit_top_3") or {})),
        "evidence_precision": dict(summary.get("evidence_precision") or {}),
        "attachment_answer_success": scored_metric_rate(dict(summary.get("attachment_answer_success") or {})),
        "attachment_text_evidence_success": scored_metric_rate(dict(summary.get("attachment_text_evidence_success") or {})),
        "attachment_ocr_text_evidence_success": {
            "source_report": attachment_ocr_source_report,
            **scored_metric_rate(dict(attachment_ocr_summary.get("attachment_ocr_text_evidence_success") or {})),
        },
        "confidence_calibration_match": scored_metric_rate(dict(summary.get("confidence_calibration_match") or {})),
        "weak_evidence_explained": scored_metric_rate(dict(summary.get("weak_evidence_explained") or {})),
        "thread_group_id_match": {
            "source_report": thread_source_report,
            **scored_metric_rate(dict(thread_summary.get("thread_group_id_match") or {})),
        },
        "thread_group_source_match": {
            "source_report": thread_source_report,
            **scored_metric_rate(dict(thread_summary.get("thread_group_source_match") or {})),
        },
        "long_thread_answer_present": {
            "source_report": long_thread_source_report,
            **scored_metric_rate(dict(long_thread_summary.get("long_thread_answer_present") or {})),
        },
        "long_thread_structure_preserved": {
            "source_report": long_thread_source_report,
            **scored_metric_rate(dict(long_thread_summary.get("long_thread_structure_preserved") or {})),
        },
        "investigation_case_analysis": {
            "source_report": investigation_source_report,
            "case_bundle_present": scored_metric_rate(dict(investigation_summary.get("case_bundle_present") or {})),
            "investigation_blocks_present": scored_metric_rate(
                dict(investigation_summary.get("investigation_blocks_present") or {})
            ),
            "case_bundle_support_uid_hit": scored_metric_rate(
                dict(investigation_summary.get("case_bundle_support_uid_hit") or {})
            ),
            "case_bundle_support_uid_recall": dict(investigation_summary.get("case_bundle_support_uid_recall") or {}),
            "multi_source_source_types_match": scored_metric_rate(
                dict(investigation_summary.get("multi_source_source_types_match") or {})
            ),
        },
        "behavioral_analysis_benchmark": {
            "available": int((behavioral_summary.get("behavior_tag_coverage") or {}).get("scorable") or 0) > 0,
            "source_report": behavioral_source_report,
            "chronology_uid_hit": scored_metric_rate(dict(behavioral_summary.get("chronology_uid_hit") or {})),
            "chronology_uid_recall": dict(behavioral_summary.get("chronology_uid_recall") or {}),
            "behavior_tag_coverage": dict(behavioral_summary.get("behavior_tag_coverage") or {}),
            "behavior_tag_precision": dict(behavioral_summary.get("behavior_tag_precision") or {}),
            "counter_indicator_quality": dict(behavioral_summary.get("counter_indicator_quality") or {}),
            "overclaim_guard_match": scored_metric_rate(dict(behavioral_summary.get("overclaim_guard_match") or {})),
            "report_completeness": scored_metric_rate(dict(behavioral_summary.get("report_completeness") or {})),
        },
        "quote_attribution_precision": {
            "available": int((quote_summary.get("quote_attribution_precision") or {}).get("scorable") or 0) > 0,
            "source_report": quote_source_report,
            **dict(quote_summary.get("quote_attribution_precision") or {}),
        },
        "quote_attribution_coverage": {
            "available": int((quote_summary.get("quote_attribution_coverage") or {}).get("scorable") or 0) > 0,
            "source_report": quote_source_report,
            **dict(quote_summary.get("quote_attribution_coverage") or {}),
        },
    }
    loaded_remediation = [
        loaded
        for path in qa_eval_remediation_candidates()
        if path.exists()
        for loaded in [load_remediation_report(path)]
        if loaded
    ]
    if loaded_remediation:
        remediation_source, remediation = loaded_remediation[0]
        ranked = remediation.get("failure_taxonomy", {}).get("ranked_categories", [])
        info["remediation_summary"] = {
            "source_report": remediation_source,
            "ranked_categories": ranked,
            "immediate_next_targets": remediation.get("immediate_next_targets", []),
        }
    loaded_prevalence = [
        loaded
        for path in inferred_thread_prevalence_candidates()
        if path.exists()
        for loaded in [load_inferred_thread_prevalence(path)]
        if loaded
    ]
    if loaded_prevalence:
        prevalence_source, prevalence = loaded_prevalence[0]
        info["natural_inferred_thread_prevalence"] = {
            "source_report": prevalence_source,
            "sample_email_count": int(prevalence.get("sample_email_count") or 0),
            "emails_with_inferred_thread_id": int(prevalence.get("emails_with_inferred_thread_id") or 0),
            "emails_with_inferred_parent_uid": int(prevalence.get("emails_with_inferred_parent_uid") or 0),
            "inferred_only_email_count": int(prevalence.get("inferred_only_email_count") or 0),
            "distinct_inferred_thread_ids": int(prevalence.get("distinct_inferred_thread_ids") or 0),
            "inferred_thread_id_rate": float(prevalence.get("inferred_thread_id_rate") or 0.0),
            "inferred_parent_uid_rate": float(prevalence.get("inferred_parent_uid_rate") or 0.0),
            "inferred_only_email_rate": float(prevalence.get("inferred_only_email_rate") or 0.0),
            "decision": str(prevalence.get("decision") or ""),
            "recommendation": str(prevalence.get("recommendation") or ""),
        }
    if isinstance(investigation_corpus_readiness, dict):
        info["investigation_corpus_readiness"] = {
            "source_report": investigation_source_report,
            "live_backend": investigation_corpus_readiness.get("live_backend"),
            "case_scope_case_count": int(investigation_corpus_readiness.get("case_scope_case_count") or 0),
            "expected_case_bundle_uid_count": int(investigation_corpus_readiness.get("expected_case_bundle_uid_count") or 0),
            "total_emails": int(investigation_corpus_readiness.get("total_emails") or 0),
            "emails_with_segments_count": int(investigation_corpus_readiness.get("emails_with_segments_count") or 0),
            "attachment_email_count": int(investigation_corpus_readiness.get("attachment_email_count") or 0),
            "corpus_populated": bool(investigation_corpus_readiness.get("corpus_populated")),
            "supports_case_analysis": bool(investigation_corpus_readiness.get("supports_case_analysis")),
            "known_blockers": [str(item) for item in investigation_corpus_readiness.get("known_blockers", [])],
        }
    return info


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
    top_body_empty_reasons = [
        {"label": label, "count": count}
        for label, count in count_rows(
            db,
            """SELECT body_empty_reason AS label, COUNT(*) AS count
               FROM emails
               WHERE body_empty_reason IS NOT NULL AND body_empty_reason != ''
               GROUP BY body_empty_reason
               ORDER BY count DESC, label ASC
               LIMIT 5""",
        ).items()
    ]

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
