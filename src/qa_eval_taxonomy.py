"""Taxonomy and remediation helpers for QA eval reports."""
# pylint: disable=too-many-branches,too-many-locals,too-many-statements

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .qa_eval_cases import QuestionCase
from .qa_eval_scoring import summarize_evaluation
from .tools.utils import ToolDepsProto


def _append_taxonomy_issue(
    flagged: dict[str, dict[str, Any]],
    *,
    category: str,
    severity: str,
    case_id: str,
    driver: str,
) -> None:
    """Append a taxonomy issue entry to the flagged dictionary.

    Creates or updates a category entry in the flagged dictionary, tracking
    case IDs, counts, and drivers for each issue category.

    Args:
        flagged: Dictionary to store flagged issues by category.
        category: Issue category string.
        severity: Either "failed" or "weak" severity level.
        case_id: Unique identifier for the case.
        driver: String describing the specific failure driver.
    """
    entry = flagged.setdefault(
        category,
        {
            "category": category,
            "flagged_cases": 0,
            "failed_cases": 0,
            "weak_cases": 0,
            "case_ids": [],
            "drivers": [],
        },
    )
    if case_id not in entry["case_ids"]:
        entry["case_ids"].append(case_id)
        entry["flagged_cases"] += 1
        if severity == "failed":
            entry["failed_cases"] += 1
        else:
            entry["weak_cases"] += 1
    if driver not in entry["drivers"]:
        entry["drivers"].append(driver)


def _issue_category_for_case(case: QuestionCase, default: str) -> str:
    """Determine the issue category for a question case.

    Checks the case's triage tags for known categories, returning the first
    match or the provided default.

    Args:
        case: QuestionCase object with triage_tags.
        default: Default category to return if no match is found.

    Returns:
        The matched category string or the default.
    """
    for category in (
        "investigation_bundle_completeness",
        "chronology_analysis",
        "behavioral_tagging",
        "comparator_analysis",
        "actor_witness_mapping",
        "document_request_quality",
        "dashboard_refresh_stability",
        "drafting_guard",
        "legal_support_product_completeness",
        "counter_indicator_handling",
        "overclaiming_guard",
        "report_completeness",
        "quote_attribution",
        "inferred_threading",
        "attachment_extraction",
        "weak_message_handling",
        "long_thread_summarization",
        "final_rendering",
        "retrieval_recall",
    ):
        if category in case.triage_tags:
            return category
    return default


# ── Rule tables for taxonomy checks ────────────────────────────────────
# Each rule: (result_key, default_category, severity, driver).
# severity can be a callable(value) -> str for threshold rules,
# or a plain str for boolean rules.
_BOOLEAN_CHECK_RULES: list[tuple[str, str, str, str]] = [
    ("thread_group_id_match", "inferred_threading", "failed", "thread_group_id_mismatch"),
    ("thread_group_source_match", "inferred_threading", "failed", "thread_group_source_mismatch"),
    ("attachment_answer_success", "attachment_extraction", "failed", "attachment_answer_failed"),
    ("attachment_text_evidence_success", "attachment_extraction", "weak", "weak_attachment_text_evidence"),
    ("long_thread_answer_present", "long_thread_summarization", "failed", "missing_long_thread_answer"),
    ("long_thread_structure_preserved", "long_thread_summarization", "failed", "missing_long_thread_structure"),
    ("case_bundle_present", "investigation_bundle_completeness", "failed", "missing_case_bundle"),
    ("investigation_blocks_present", "investigation_bundle_completeness", "failed", "missing_investigation_blocks"),
    ("case_bundle_support_uid_hit", "investigation_bundle_completeness", "failed", "missing_case_bundle_evidence"),
    ("case_bundle_support_source_id_hit", "investigation_bundle_completeness", "failed", "missing_case_bundle_source_grounding"),
    ("multi_source_source_types_match", "investigation_bundle_completeness", "weak", "missing_expected_source_types"),
    ("chronology_uid_hit", "chronology_analysis", "failed", "missing_timeline_anchor"),
    ("chronology_source_id_hit", "chronology_analysis", "failed", "missing_timeline_source_grounding"),
    ("overclaim_guard_match", "overclaiming_guard", "failed", "claim_level_exceeds_label_ceiling"),
    ("report_completeness", "report_completeness", "failed", "missing_supported_report_sections"),
    ("legal_support_product_completeness", "legal_support_product_completeness", "failed", "missing_legal_support_product"),
    ("legal_support_grounding_hit", "legal_support_product_completeness", "failed", "ungrounded_legal_support_product"),
    ("drafting_ceiling_match", "drafting_guard", "failed", "drafting_ceiling_mismatch"),
    ("draft_section_completeness", "drafting_guard", "failed", "missing_controlled_draft_sections"),
]


# Threshold rules — severity is a callable(value: float) -> str.
# Special sentinel ``_zero_failed_else_weak`` for the common pattern.
def _zero_failed_else_weak(val: float) -> str:
    return "failed" if val == 0.0 else "weak"


_ThresholdSeverity = str | Callable[[float], str]
_THRESHOLD_CHECK_RULES: list[tuple[str, str, _ThresholdSeverity, str]] = [
    ("quote_attribution_precision", "quote_attribution", "weak", "quote_precision_below_one"),
    ("quote_attribution_coverage", "quote_attribution", _zero_failed_else_weak, "quote_coverage_below_one"),
    ("behavior_tag_coverage", "behavioral_tagging", _zero_failed_else_weak, "behavior_tag_coverage_below_one"),
    ("behavior_tag_precision", "behavioral_tagging", "weak", "behavior_tag_precision_below_one"),
    ("counter_indicator_quality", "counter_indicator_handling", _zero_failed_else_weak, "counter_indicator_quality_below_one"),
    ("comparator_matrix_coverage", "comparator_analysis", _zero_failed_else_weak, "comparator_matrix_coverage_below_one"),
    ("dashboard_card_coverage", "dashboard_refresh_stability", _zero_failed_else_weak, "dashboard_card_coverage_below_one"),
    ("actor_map_coverage", "actor_witness_mapping", _zero_failed_else_weak, "actor_map_coverage_below_one"),
    ("checklist_group_coverage", "document_request_quality", _zero_failed_else_weak, "checklist_group_coverage_below_one"),
    ("case_bundle_support_uid_recall", "investigation_bundle_completeness", "weak", "case_bundle_recall_below_one"),
    ("case_bundle_support_source_id_recall", "investigation_bundle_completeness", "weak", "case_bundle_source_recall_below_one"),
    ("chronology_uid_recall", "chronology_analysis", "weak", "timeline_recall_below_one"),
    ("chronology_source_id_recall", "chronology_analysis", "weak", "timeline_source_recall_below_one"),
    ("legal_support_grounding_recall", "legal_support_product_completeness", "weak", "legal_support_grounding_recall_below_one"),
]

# Benchmark rules: (metric, default_category, failed_driver, weak_driver)
_BENCHMARK_RULES: list[tuple[str, str, str, str]] = [
    ("benchmark_actor_recovery", "retrieval_recall", "benchmark_actor_recovery_zero", "benchmark_actor_recovery_partial"),
    (
        "benchmark_issue_family_recovery",
        "retrieval_recall",
        "benchmark_issue_family_recovery_zero",
        "benchmark_issue_family_recovery_partial",
    ),
    (
        "benchmark_chronology_anchor_recovery",
        "chronology_analysis",
        "benchmark_chronology_anchor_recovery_zero",
        "benchmark_chronology_anchor_recovery_partial",
    ),
    (
        "benchmark_manifest_link_recovery",
        "investigation_bundle_completeness",
        "benchmark_manifest_link_recovery_zero",
        "benchmark_manifest_link_recovery_partial",
    ),
    ("benchmark_report_recovery", "report_completeness", "benchmark_report_recovery_zero", "benchmark_report_recovery_partial"),
]

# Forbidden-exclusion rules: (metric, default_category, driver)
_FORBIDDEN_RULES: list[tuple[str, str, str]] = [
    ("forbidden_support_ids_excluded", "retrieval_recall", "forbidden_support_present"),
    ("forbidden_issue_ids_excluded", "overclaiming_guard", "forbidden_issue_present"),
    ("forbidden_actor_ids_excluded", "actor_witness_mapping", "forbidden_actor_present"),
    ("forbidden_dashboard_cards_excluded", "dashboard_refresh_stability", "forbidden_dashboard_card_present"),
    ("forbidden_checklist_groups_excluded", "document_request_quality", "forbidden_checklist_group_present"),
]


def _apply_taxonomy_rules(flagged, *, result, case, case_id) -> None:
    """Apply all taxonomy rule tables to one result row."""
    _apply_retrieval_rules(flagged, result, case, case_id)
    _apply_ambiguity_and_weak_rules(flagged, result, case, case_id)
    _apply_boolean_rules(flagged, result, case, case_id)
    _apply_attachment_ocr_rule(flagged, result, case, case_id)
    _apply_threshold_rules(flagged, result, case, case_id)
    _apply_benchmark_rules(flagged, result, case, case_id)
    _apply_answer_content_rule(flagged, result, case, case_id)
    _apply_forbidden_rules(flagged, result, case, case_id)


def _add_issue(flagged, case, case_id, category, severity, driver) -> None:
    _append_taxonomy_issue(
        flagged, category=_issue_category_for_case(case, category), severity=severity, case_id=case_id, driver=driver
    )


def _apply_retrieval_rules(flagged, result, case, case_id) -> None:
    _apply_primary_retrieval_rules(flagged, result, case, case_id)
    _apply_evidence_precision_rule(flagged, result, case, case_id)
    _apply_source_recall_rule(flagged, result, case, case_id)


def _apply_primary_retrieval_rules(flagged, result, case, case_id) -> None:
    count = int(result.get("count") or 0)
    labeled = bool(case.expected_support_uids or case.expected_support_source_ids or case.expected_top_uid)
    support_hit = result.get("support_uid_hit")
    if _retrieval_hit_failed(labeled, support_hit, result.get("top_uid_match"), count):
        driver = "no_supported_hit" if count == 0 or support_hit is False else "top_uid_mismatch"
        _add_issue(flagged, case, case_id, "retrieval_recall", "failed", driver)
    if labeled and result.get("support_source_id_hit") is False:
        _add_issue(flagged, case, case_id, "retrieval_recall", "failed", "support_source_grounding_missing")


def _apply_evidence_precision_rule(flagged, result, case, case_id) -> None:
    precision = result.get("evidence_precision")
    if precision is not None and float(precision) < 1.0:
        _add_issue(flagged, case, case_id, "retrieval_recall", "weak", "evidence_precision_below_one")


def _apply_source_recall_rule(flagged, result, case, case_id) -> None:
    labeled = bool(case.expected_support_uids or case.expected_support_source_ids or case.expected_top_uid)
    source_recall = result.get("support_source_id_recall")
    if labeled and source_recall is not None and float(source_recall) < 1.0:
        _add_issue(flagged, case, case_id, "retrieval_recall", "weak", "support_source_grounding_recall_below_one")


def _retrieval_hit_failed(labeled: bool, support_hit: Any, top_uid_match: Any, count: int) -> bool:
    return labeled and (support_hit is False or top_uid_match is False or count == 0)


def _apply_ambiguity_and_weak_rules(flagged, result, case, case_id) -> None:
    if result.get("ambiguity_match") is False or result.get("confidence_calibration_match") is False:
        _add_issue(flagged, case, case_id, "final_rendering", "failed", "ambiguity_or_confidence_mismatch")
    weak_explained = result.get("weak_evidence_explained")
    reason = str(result.get("observed_ambiguity_reason") or "")
    weak_reasons = {"weak_scan_body", "source_shell_only", "image_only", "metadata_only_reply", "true_blank", "attachment_only"}
    if case.expected_ambiguity == "insufficient" and weak_explained is False:
        _add_issue(flagged, case, case_id, "weak_message_handling", "failed", "weak_evidence_not_explained")
    elif reason in weak_reasons and weak_explained is not True:
        _add_issue(flagged, case, case_id, "weak_message_handling", "weak", "weak_message_reason_without_explicit_explanation")


def _apply_boolean_rules(flagged, result, case, case_id) -> None:
    for key, category, severity, driver in _BOOLEAN_CHECK_RULES:
        if result.get(key) is False:
            _add_issue(flagged, case, case_id, category, severity, driver)


def _apply_attachment_ocr_rule(flagged, result, case, case_id) -> None:
    if result.get("attachment_ocr_text_evidence_success") is False and "attachment_ocr" in case.triage_tags:
        _add_issue(flagged, case, case_id, "attachment_extraction", "weak", "weak_attachment_ocr_evidence")


def _apply_threshold_rules(flagged, result, case, case_id) -> None:
    for key, category, severity_spec, driver in _THRESHOLD_CHECK_RULES:
        value = result.get(key)
        if value is None or float(value) >= 1.0:
            continue
        severity = severity_spec(float(value)) if callable(severity_spec) else str(severity_spec)
        _add_issue(flagged, case, case_id, category, severity, driver)


def _apply_benchmark_rules(flagged, result, case, case_id) -> None:
    for metric, category, failed_driver, weak_driver in _BENCHMARK_RULES:
        coverage = result.get(metric)
        total = result.get(f"{metric}_total")
        if coverage is None or (total is not None and int(total) <= 0):
            continue
        numeric = float(coverage)
        if numeric == 0.0:
            _add_issue(flagged, case, case_id, category, "failed", failed_driver)
        elif numeric < 1.0:
            _add_issue(flagged, case, case_id, category, "weak", weak_driver)


def _apply_answer_content_rule(flagged, result, case, case_id) -> None:
    if result.get("answer_content_match") is False:
        _add_issue(flagged, case, case_id, "final_rendering", "failed", "answer_content_mismatch")


def _apply_forbidden_rules(flagged, result, case, case_id) -> None:
    for metric, category, driver in _FORBIDDEN_RULES:
        if result.get(metric) is False:
            _add_issue(flagged, case, case_id, category, "failed", driver)


def build_failure_taxonomy(cases: list[QuestionCase], results: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a taxonomy of failures from QA evaluation results.

    Analyzes evaluation results against expected case data to categorize
    failures by issue type, severity, and driver. Returns a structured taxonomy
    with ranked categories.

    Args:
        cases: List of QuestionCase objects with expected values.
        results: List of evaluation result dictionaries.

    Returns:
        Dictionary containing:
            - total_flagged_cases: Total number of unique cases with issues
            - categories: Dictionary of category details
            - ranked_categories: List of categories sorted by severity
    """
    by_case_id = {case.id: case for case in cases}
    flagged: dict[str, dict[str, Any]] = {}

    for result in results:
        case = by_case_id.get(str(result["id"]))
        if case is None:
            continue
        _apply_taxonomy_rules(flagged, result=result, case=case, case_id=case.id)

    ranked_categories = sorted(
        flagged.values(),
        key=lambda item: (-int(item["failed_cases"]), -int(item["weak_cases"]), str(item["category"])),
    )
    return {
        "total_flagged_cases": len({case_id for item in flagged.values() for case_id in item["case_ids"]}),
        "categories": {item["category"]: item for item in ranked_categories},
        "ranked_categories": ranked_categories,
    }


def _recommended_track_for_category(category: str) -> dict[str, str]:
    """Get the recommended remediation track for an issue category.

    Maps issue categories to their corresponding development tracks and
    next steps for remediation.

    Args:
        category: Issue category string.

    Returns:
        Dictionary with "track" and "next_step" keys. Returns a default
        manual triage recommendation if the category is not recognized.
    """
    mapping = {
        "retrieval_recall": {
            "track": "retrieval_quality",
            "next_step": "define and implement retrieval-quality remediation after AQ20",
        },
        "investigation_bundle_completeness": {
            "track": "BA15",
            "next_step": "improve case-bundle completeness and investigation readiness on synthetic corpus data",
        },
        "chronology_analysis": {
            "track": "BA10",
            "next_step": "improve chronology assembly and timeline-anchor retention for behavioural-analysis cases",
        },
        "behavioral_tagging": {
            "track": "BA6",
            "next_step": "improve message-level behaviour tagging precision and recall on labeled cases",
        },
        "counter_indicator_handling": {
            "track": "BA13",
            "next_step": "improve counter-indicator surfacing and alternative-explanation carry-through",
        },
        "overclaiming_guard": {
            "track": "BA17",
            "next_step": "tighten interpretation-policy claim ceilings and overclaim prevention",
        },
        "report_completeness": {
            "track": "BA16",
            "next_step": "improve investigation report section completeness for labeled review cases",
        },
        "legal_support_product_completeness": {
            "track": "LS1",
            "next_step": "restore missing stable legal-support products in the case-analysis payload",
        },
        "comparator_analysis": {
            "track": "LS2",
            "next_step": "repair comparator-matrix coverage and expected lawyer-usable comparison rows",
        },
        "actor_witness_mapping": {
            "track": "LS3",
            "next_step": "repair actor and witness mapping coverage from the shared matter entities",
        },
        "document_request_quality": {
            "track": "LS4",
            "next_step": "repair checklist grouping and preservation-request quality in the legal-support outputs",
        },
        "dashboard_refresh_stability": {
            "track": "LS5",
            "next_step": "restore expected dashboard cards and refreshable summary behavior",
        },
        "drafting_guard": {
            "track": "LS6",
            "next_step": "repair allegation-ceiling enforcement and controlled-draft section completeness",
        },
        "final_rendering": {
            "track": "answer_rendering_tuning",
            "next_step": "tighten answer rendering after retrieval quality improves",
        },
        "attachment_extraction": {"track": "AQ21", "next_step": "improve OCR and strong-text attachment evidence"},
        "weak_message_handling": {
            "track": "weak_message_followup",
            "next_step": "improve weak-evidence phrasing and recovery on live cases",
        },
        "inferred_threading": {"track": "AQ23", "next_step": "validate and improve inferred-thread impact on live data"},
        "quote_attribution": {"track": "AQ22", "next_step": "improve quote-attribution recall while preserving precision"},
        "long_thread_summarization": {
            "track": "AQ24",
            "next_step": "validate and improve long-thread answer survival under live budget pressure",
        },
    }
    return mapping.get(
        category, {"track": "manual_triage", "next_step": "inspect representative failures and define a bounded follow-up"}
    )


def build_remediation_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Build a remediation summary from a QA evaluation report.

    Extracts summary and taxonomy data from the report, enriches each
    category with recommended tracks and next steps, and produces a
    prioritized list of remediation targets.

    Args:
        report: QA evaluation report dictionary containing summary and
            failure_taxonomy keys.

    Returns:
        Dictionary containing:
            - total_cases: Total number of cases
            - bucket_counts: Counts by evaluation bucket
            - top_1_correctness: Top-1 correctness metrics
            - Various other summary metrics
            - failure_taxonomy: Enriched taxonomy with recommendations
            - immediate_next_targets: Top 3 remediation targets

    Raises:
        ValueError: If report is missing required summary or failure_taxonomy.
    """
    summary, taxonomy, ranked_categories = _validated_remediation_inputs(report)
    ranked_targets = _ranked_remediation_targets(ranked_categories)

    return {
        "total_cases": int(summary.get("total_cases") or report.get("total_cases") or 0),
        "bucket_counts": dict(summary.get("bucket_counts") or {}),
        "top_1_correctness": dict(summary.get("top_1_correctness") or {}),
        "support_uid_hit_top_3": dict(summary.get("support_uid_hit_top_3") or {}),
        "confidence_calibration_match": dict(summary.get("confidence_calibration_match") or {}),
        "failure_taxonomy": {
            "total_flagged_cases": int(taxonomy.get("total_flagged_cases") or 0),
            "ranked_categories": ranked_targets,
        },
        "immediate_next_targets": [
            {
                "category": str(item.get("category") or ""),
                "recommended_track": str(item.get("recommended_track") or ""),
                "recommended_next_step": str(item.get("recommended_next_step") or ""),
            }
            for item in ranked_targets[:3]
        ],
    }


def _validated_remediation_inputs(report: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[Any]]:
    summary = report.get("summary")
    taxonomy = report.get("failure_taxonomy")
    if not isinstance(summary, dict) or not isinstance(taxonomy, dict):
        raise ValueError("report must contain summary and failure_taxonomy objects")
    ranked = taxonomy.get("ranked_categories")
    if not isinstance(ranked, list):
        raise ValueError("failure_taxonomy.ranked_categories must be a list")
    return summary, taxonomy, ranked


def _ranked_remediation_targets(categories: list[Any]) -> list[dict[str, Any]]:
    targets = [_remediation_target(item) for item in categories if isinstance(item, dict)]
    targets.sort(key=_remediation_priority, reverse=True)
    return targets


def _remediation_priority(item: dict[str, Any]) -> tuple[int, int, int]:
    return (
        int(item.get("priority_score") or 0),
        int(item.get("failed_cases") or 0),
        int(item.get("flagged_cases") or 0),
    )


def _remediation_target(item: dict[str, Any]) -> dict[str, Any]:
    category = str(item.get("category") or "")
    flagged = int(item.get("flagged_cases") or 0)
    failed = int(item.get("failed_cases") or 0)
    weak = int(item.get("weak_cases") or 0)
    recommendation = _recommended_track_for_category(category)
    return {
        "category": category,
        "priority_score": failed * 3 + weak * 2 + flagged,
        "flagged_cases": flagged,
        "failed_cases": failed,
        "weak_cases": weak,
        "case_ids": [str(case_id) for case_id in item.get("case_ids", [])],
        "drivers": [str(driver) for driver in item.get("drivers", [])],
        "recommended_track": recommendation["track"],
        "recommended_next_step": recommendation["next_step"],
    }


def _scalar_count(conn: Any, query: str) -> int:
    """Execute a SQL query and return a single integer count.

    Args:
        conn: SQLite database connection object.
        query: SQL query string that should return a count.

    Returns:
        Integer count from the first column of the first row, or 0 if
        no results or error.
    """
    row = conn.execute(query).fetchone()
    if not row:
        return 0
    if isinstance(row, dict):
        return int(row.get("count") or 0)
    return int(row[0] or 0)


def build_investigation_corpus_readiness(
    *,
    cases: list[QuestionCase],
    results: list[dict[str, Any]],
    live_deps: ToolDepsProto | None,
) -> dict[str, Any]:
    """Assess whether the investigation corpus is ready for case analysis.

    Checks database connectivity, corpus population, and case bundle
    completeness to determine if the system can support case analysis.

    Args:
        cases: List of QuestionCase objects to analyze.
        results: List of evaluation result dictionaries.
        live_deps: Optional ToolDepsProto providing database access.

    Returns:
        Dictionary containing:
            - live_backend: Backend identifier
            - case_scope_case_count: Number of case-scoped cases
            - expected_case_bundle_uid_count: Expected bundle UID count
            - corpus_populated: Whether the corpus has data
            - supports_case_analysis: Whether case analysis is supported
            - known_blockers: List of blocker identifiers
            - Various corpus statistics (total_emails, etc.)
    """
    case_scoped_cases = [case for case in cases if case.case_scope is not None]
    total_expected_bundle_uids = sum(len(case.expected_case_bundle_uids) for case in case_scoped_cases)
    readiness = _initial_investigation_readiness(live_deps, case_scoped_cases, total_expected_bundle_uids)
    if live_deps is None:
        readiness["known_blockers"] = ["no_live_deps"]
        return readiness
    db = live_deps.get_email_db()
    conn = getattr(db, "conn", None)
    if conn is None:
        readiness["known_blockers"] = ["missing_sqlite_connection"]
        return readiness
    counts = _investigation_corpus_counts(conn)
    readiness.update(counts)
    readiness["corpus_populated"] = counts["total_emails"] > 0 and counts["emails_with_segments_count"] > 0
    blockers = _investigation_blockers(counts, case_scoped_cases)
    summary = summarize_evaluation(results)
    case_bundle_metric = dict(summary.get("case_bundle_present") or {})
    investigation_blocks_metric = dict(summary.get("investigation_blocks_present") or {})
    readiness["supports_case_analysis"] = _supports_case_analysis(
        readiness["corpus_populated"], case_bundle_metric, investigation_blocks_metric
    )
    if not readiness["supports_case_analysis"] and int(case_bundle_metric.get("scorable") or 0) > 0:
        blockers.append("case_analysis_blocks_incomplete")
    readiness["known_blockers"] = blockers
    return readiness


def _initial_investigation_readiness(live_deps, scoped_cases, expected_uid_count) -> dict[str, Any]:
    return {
        "live_backend": getattr(live_deps, "live_backend", None) if live_deps is not None else None,
        "case_scope_case_count": len(scoped_cases),
        "expected_case_bundle_uid_count": expected_uid_count,
        "corpus_populated": False,
        "supports_case_analysis": False,
        "known_blockers": [],
    }


def _supports_case_analysis(corpus_populated: bool, bundle: dict[str, Any], blocks: dict[str, Any]) -> bool:
    return (
        corpus_populated
        and int(bundle.get("scorable") or 0) > 0
        and int(bundle.get("failed") or 0) == 0
        and int(blocks.get("failed") or 0) == 0
    )


def _investigation_corpus_counts(conn: Any) -> dict[str, int]:
    return {
        "total_emails": _scalar_count(conn, "SELECT COUNT(*) FROM emails"),
        "emails_with_segments_count": _scalar_count(conn, "SELECT COUNT(DISTINCT email_uid) FROM message_segments"),
        "attachment_email_count": _scalar_count(conn, "SELECT COUNT(*) FROM emails WHERE COALESCE(has_attachments, 0) != 0"),
    }


def _investigation_blockers(counts: dict[str, int], scoped_cases: list[QuestionCase]) -> list[str]:
    candidates = (
        (counts["total_emails"] <= 0, "empty_email_corpus"),
        (counts["emails_with_segments_count"] <= 0, "missing_message_segments"),
        (not scoped_cases, "no_case_scoped_eval_cases"),
    )
    return [blocker for blocked, blocker in candidates if blocked]
