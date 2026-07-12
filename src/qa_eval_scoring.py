"""Pure payload-scoring helpers for QA evaluation."""
# pylint: disable=too-many-locals,too-many-statements

from __future__ import annotations

from typing import Any

from .qa_eval_cases import QuestionCase
from .qa_eval_scoring_helpers import (
    _actor_map_coverage,
    _ambiguity_matches,
    _answer_content_match,
    _archive_harvest_coverage_pass,
    _archive_harvest_later_round_recovery,
    _archive_harvest_mixed_source_present,
    _archive_harvest_quality_pass,
    _behavior_tag_coverage,
    _behavior_tag_precision,
    _candidate_uids,
    _case_bundle_present,
    _case_bundle_support_source_id_hit,
    _case_bundle_support_source_id_recall,
    _case_bundle_support_uid_hit,
    _case_bundle_support_uid_recall,
    _checklist_group_coverage,
    _chronology_source_id_hit,
    _chronology_source_id_recall,
    _chronology_uid_hit,
    _chronology_uid_recall,
    _comparator_matrix_coverage,
    _counter_indicator_quality,
    _dashboard_card_coverage,
    _draft_section_completeness,
    _drafting_ceiling_match,
    _forbidden_actor_ids_excluded,
    _forbidden_checklist_groups_excluded,
    _forbidden_dashboard_cards_excluded,
    _forbidden_issue_ids_excluded,
    _forbidden_support_ids_excluded,
    _investigation_blocks_present,
    _legal_support_grounding_hit,
    _legal_support_grounding_recall,
    _legal_support_product_completeness,
    _long_thread_answer_present,
    _long_thread_structure_preserved,
    _multi_source_source_types_match,
    _observed_quoted_speaker_emails,
    _overclaim_guard_match,
    _ratio,
    _report_completeness,
    _resolve_top_uid,
    _slice_a_authored_german_primary_match,
    _slice_a_calendar_exclusion_visible,
    _slice_a_contradiction_pair_precision,
    _slice_a_exact_verified_quote_rate,
    _slice_a_false_exact_flag,
    _slice_a_locator_completeness,
    _slice_a_mixed_source_completeness,
    _slice_a_near_exact_quote_rate,
    _slice_a_ocr_heavy_attachment_recall,
    _slice_a_silence_omission_anchor_match,
    _strong_attachment_ocr_support_uid_hit,
    _strong_attachment_support_uid_hit,
    _support_source_id_hit,
    _support_source_id_recall,
    _uids_for_key,
    _weak_evidence_explained,
)
from .qa_eval_scoring_helpers import (
    summarize_evaluation as _summarize_evaluation,
)


def evaluate_payload(case: QuestionCase, payload: dict[str, Any], *, source: str) -> dict[str, Any]:
    """Score one answer-context payload against one labeled question."""
    result = {
        "id": case.id,
        "bucket": case.bucket,
        "question": case.question,
        "status": case.status,
        "source": source,
        "count": int(payload.get("count") or 0),
    }
    result.update(_retrieval_metrics(case, payload))
    result.update(_investigation_metrics(case, payload))
    result.update(_benchmark_metrics(case, payload))
    result.update(_observed_answer_quality(case, payload))
    result.update({name: value for name, value in _slice_a_metrics(case, payload).items() if value is not None})
    return result


def _retrieval_metrics(case: QuestionCase, payload: dict[str, Any]) -> dict[str, Any]:
    candidate_uids = _candidate_uids(payload)
    attachment_uids = _uids_for_key(payload, "attachment_candidates")
    matched = [uid for uid in case.expected_support_uids if uid in candidate_uids]
    matched_top_3 = [uid for uid in case.expected_support_uids if uid in candidate_uids[:3]]
    top_uid = _resolve_top_uid(payload)
    top_uid_match = _optional_match(top_uid, case.expected_top_uid)
    ambiguity = _ambiguity_matches(case.expected_ambiguity, payload)
    attachment_hit = _attachment_support_hit(case, attachment_uids)
    observed_speakers = _observed_quoted_speaker_emails(payload)
    matched_speakers = [email for email in case.expected_quoted_speaker_emails if email in observed_speakers]
    quote_precision, quote_coverage = _quote_metrics(case, observed_speakers, matched_speakers)
    answer_quality = payload.get("answer_quality") or {}
    observed_group_id = str(answer_quality.get("top_thread_group_id") or "")
    observed_group_source = str(answer_quality.get("top_thread_group_source") or "").lower()
    support_hit, support_hit_top_3 = _support_uid_matches(case, matched, matched_top_3)
    thread_id_match, thread_source_match = _thread_group_matches(case, observed_group_id, observed_group_source)
    metrics = {
        "top_uid": top_uid,
        "candidate_uids": candidate_uids,
        "attachment_candidate_uids": attachment_uids,
        "matched_support_uids": matched,
        "matched_support_uids_top_3": matched_top_3,
        "top_1_correctness": top_uid_match,
        "support_uid_hit": support_hit,
        "support_uid_hit_top_3": support_hit_top_3,
        "support_uid_recall": _ratio(len(matched), len(case.expected_support_uids)),
        "support_source_id_hit": _support_source_id_hit(case, payload),
        "support_source_id_recall": _support_source_id_recall(case, payload),
        "evidence_precision": _ratio(len(matched), len(candidate_uids)),
        "top_uid_match": top_uid_match,
        "ambiguity_match": ambiguity,
        "confidence_calibration_match": ambiguity,
        "attachment_support_uid_hit": attachment_hit,
        "attachment_answer_success": attachment_hit,
        "attachment_text_evidence_success": _strong_attachment_support_uid_hit(case, payload),
        "attachment_ocr_text_evidence_success": _strong_attachment_ocr_support_uid_hit(case, payload),
        "weak_evidence_explained": _weak_evidence_explained(case, payload),
        "long_thread_answer_present": _long_thread_answer_present(case, payload),
        "long_thread_structure_preserved": _long_thread_structure_preserved(case, payload),
        "observed_quoted_speaker_emails": observed_speakers,
        "matched_quoted_speaker_emails": matched_speakers,
        "quote_attribution_precision": quote_precision,
        "quote_attribution_coverage": quote_coverage,
        "observed_thread_group_id": observed_group_id,
        "observed_thread_group_source": observed_group_source,
        "thread_group_id_match": thread_id_match,
        "thread_group_source_match": thread_source_match,
    }
    return metrics


def _support_uid_matches(
    case: QuestionCase,
    matched: list[str],
    matched_top_3: list[str],
) -> tuple[bool | None, bool | None]:
    if not case.expected_support_uids:
        return None, None
    return bool(matched), bool(matched_top_3)


def _thread_group_matches(
    case: QuestionCase,
    observed_group_id: str,
    observed_group_source: str,
) -> tuple[bool | None, bool | None]:
    group_id_match = observed_group_id == case.expected_thread_group_id if case.expected_thread_group_id else None
    source_match = observed_group_source == case.expected_thread_group_source if case.expected_thread_group_source else None
    return group_id_match, source_match


def _quote_metrics(case, observed, matched) -> tuple[float | None, float | None]:
    if not case.expected_quoted_speaker_emails:
        return None, None
    return _ratio(len(matched), len(observed)), _ratio(len(matched), len(case.expected_quoted_speaker_emails))


def _optional_match(observed: str | None, expected: str | None) -> bool | None:
    return observed == expected if expected else None


def _attachment_support_hit(case: QuestionCase, attachment_uids: list[str]) -> bool | None:
    if case.bucket != "attachment_lookup" or not case.expected_support_uids:
        return None
    return any(uid in attachment_uids for uid in case.expected_support_uids)


def _investigation_metrics(case: QuestionCase, payload: dict[str, Any]) -> dict[str, Any]:
    metric_functions = {
        "case_bundle_present": _case_bundle_present,
        "investigation_blocks_present": _investigation_blocks_present,
        "case_bundle_support_uid_hit": _case_bundle_support_uid_hit,
        "case_bundle_support_uid_recall": _case_bundle_support_uid_recall,
        "case_bundle_support_source_id_hit": _case_bundle_support_source_id_hit,
        "case_bundle_support_source_id_recall": _case_bundle_support_source_id_recall,
        "multi_source_source_types_match": _multi_source_source_types_match,
        "chronology_uid_hit": _chronology_uid_hit,
        "chronology_uid_recall": _chronology_uid_recall,
        "chronology_source_id_hit": _chronology_source_id_hit,
        "chronology_source_id_recall": _chronology_source_id_recall,
        "behavior_tag_coverage": _behavior_tag_coverage,
        "behavior_tag_precision": _behavior_tag_precision,
        "counter_indicator_quality": _counter_indicator_quality,
        "overclaim_guard_match": _overclaim_guard_match,
        "report_completeness": _report_completeness,
        "legal_support_product_completeness": _legal_support_product_completeness,
        "legal_support_grounding_hit": _legal_support_grounding_hit,
        "legal_support_grounding_recall": _legal_support_grounding_recall,
        "comparator_matrix_coverage": _comparator_matrix_coverage,
        "dashboard_card_coverage": _dashboard_card_coverage,
        "actor_map_coverage": _actor_map_coverage,
        "checklist_group_coverage": _checklist_group_coverage,
        "drafting_ceiling_match": _drafting_ceiling_match,
        "draft_section_completeness": _draft_section_completeness,
        "answer_content_match": _answer_content_match,
        "archive_harvest_coverage_pass": _archive_harvest_coverage_pass,
        "archive_harvest_quality_pass": _archive_harvest_quality_pass,
        "archive_harvest_mixed_source_present": _archive_harvest_mixed_source_present,
        "archive_harvest_later_round_recovery": _archive_harvest_later_round_recovery,
        "forbidden_support_ids_excluded": _forbidden_support_ids_excluded,
        "forbidden_issue_ids_excluded": _forbidden_issue_ids_excluded,
        "forbidden_actor_ids_excluded": _forbidden_actor_ids_excluded,
        "forbidden_dashboard_cards_excluded": _forbidden_dashboard_cards_excluded,
        "forbidden_checklist_groups_excluded": _forbidden_checklist_groups_excluded,
    }
    return {name: function(case, payload) for name, function in metric_functions.items()}


def _benchmark_metrics(case: QuestionCase, payload: dict[str, Any]) -> dict[str, Any]:
    recovery: dict[str, Any] = {}
    if case.benchmark_pack:
        from .qa_eval_bootstrap import benchmark_detection_recovery

        recovery = benchmark_detection_recovery(benchmark_pack=case.benchmark_pack, payload=payload)
    sections = {
        "actor": "actor_recovery",
        "issue_family": "issue_family_recovery",
        "chronology_anchor": "chronology_anchor_recovery",
        "manifest_link": "manifest_link_recovery",
        "report": "mixed_source_report_completeness",
    }
    metrics: dict[str, Any] = {}
    for label, key in sections.items():
        section = recovery.get(key) or {}
        total = int(section.get("total") or 0)
        value = section.get("coverage")
        metrics[f"benchmark_{label}_recovery"] = float(value) if total > 0 and value is not None else None
        metrics[f"benchmark_{label}_recovery_total"] = total
    metrics["benchmark_detection_recovery"] = recovery or None
    return metrics


def _observed_answer_quality(case: QuestionCase, payload: dict[str, Any]) -> dict[str, Any]:
    quality = payload.get("answer_quality") or {}
    return {
        "expected_ambiguity": case.expected_ambiguity,
        "observed_confidence_label": quality.get("confidence_label"),
        "observed_ambiguity_reason": quality.get("ambiguity_reason"),
    }


def _slice_a_metrics(case: QuestionCase, payload: dict[str, Any]) -> dict[str, Any]:
    functions = {
        "slice_a_exact_verified_quote_rate": _slice_a_exact_verified_quote_rate,
        "slice_a_near_exact_quote_rate": _slice_a_near_exact_quote_rate,
        "slice_a_false_exact_flag": _slice_a_false_exact_flag,
        "slice_a_locator_completeness": _slice_a_locator_completeness,
        "slice_a_ocr_heavy_attachment_recall": _slice_a_ocr_heavy_attachment_recall,
        "slice_a_authored_german_primary_match": _slice_a_authored_german_primary_match,
        "slice_a_contradiction_pair_precision": _slice_a_contradiction_pair_precision,
        "slice_a_mixed_source_completeness": _slice_a_mixed_source_completeness,
        "slice_a_calendar_exclusion_visible": _slice_a_calendar_exclusion_visible,
        "slice_a_silence_omission_anchor_match": _slice_a_silence_omission_anchor_match,
    }
    return {name: function(case, payload) for name, function in functions.items()}


def summarize_evaluation(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize evaluation outcomes across all scored cases."""
    return _summarize_evaluation(results)
