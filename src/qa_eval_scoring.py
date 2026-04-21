"""Pure payload-scoring helpers for QA evaluation."""

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
    candidate_uids = _candidate_uids(payload)
    attachment_candidate_uids = _uids_for_key(payload, "attachment_candidates")
    top_3_candidate_uids = candidate_uids[:3]
    matched_support = [uid for uid in case.expected_support_uids if uid in candidate_uids]
    matched_support_top_3 = [uid for uid in case.expected_support_uids if uid in top_3_candidate_uids]
    top_uid = _resolve_top_uid(payload)
    support_uid_hit = bool(matched_support) if case.expected_support_uids else None
    support_uid_hit_top_3 = bool(matched_support_top_3) if case.expected_support_uids else None
    support_uid_recall = _ratio(len(matched_support), len(case.expected_support_uids))
    support_source_id_hit = _support_source_id_hit(case, payload)
    support_source_id_recall = _support_source_id_recall(case, payload)
    evidence_precision = _ratio(len(matched_support), len(candidate_uids))
    top_uid_match = (top_uid == case.expected_top_uid) if case.expected_top_uid else None
    top_1_correctness = top_uid_match
    ambiguity_match = _ambiguity_matches(case.expected_ambiguity, payload)
    confidence_calibration_match = ambiguity_match
    attachment_support_uid_hit = (
        any(uid in attachment_candidate_uids for uid in case.expected_support_uids)
        if case.bucket == "attachment_lookup" and case.expected_support_uids
        else None
    )
    attachment_answer_success = attachment_support_uid_hit
    attachment_text_evidence_success = _strong_attachment_support_uid_hit(case, payload)
    attachment_ocr_text_evidence_success = _strong_attachment_ocr_support_uid_hit(case, payload)
    weak_evidence_explained = _weak_evidence_explained(case, payload)
    long_thread_answer_present = _long_thread_answer_present(case, payload)
    long_thread_structure_preserved = _long_thread_structure_preserved(case, payload)
    observed_quoted_speaker_emails = _observed_quoted_speaker_emails(payload)
    matched_quoted_speakers = [email for email in case.expected_quoted_speaker_emails if email in observed_quoted_speaker_emails]
    if case.expected_quoted_speaker_emails:
        quote_attribution_precision = _ratio(len(matched_quoted_speakers), len(observed_quoted_speaker_emails))
        quote_attribution_coverage = _ratio(len(matched_quoted_speakers), len(case.expected_quoted_speaker_emails))
    else:
        quote_attribution_precision = None
        quote_attribution_coverage = None
    observed_thread_group_id = str((payload.get("answer_quality") or {}).get("top_thread_group_id") or "")
    observed_thread_group_source = str((payload.get("answer_quality") or {}).get("top_thread_group_source") or "").lower()
    thread_group_id_match = observed_thread_group_id == case.expected_thread_group_id if case.expected_thread_group_id else None
    thread_group_source_match = (
        observed_thread_group_source == case.expected_thread_group_source if case.expected_thread_group_source else None
    )
    case_bundle_present = _case_bundle_present(case, payload)
    investigation_blocks_present = _investigation_blocks_present(case, payload)
    case_bundle_support_uid_hit = _case_bundle_support_uid_hit(case, payload)
    case_bundle_support_uid_recall = _case_bundle_support_uid_recall(case, payload)
    case_bundle_support_source_id_hit = _case_bundle_support_source_id_hit(case, payload)
    case_bundle_support_source_id_recall = _case_bundle_support_source_id_recall(case, payload)
    multi_source_source_types_match = _multi_source_source_types_match(case, payload)
    chronology_uid_hit = _chronology_uid_hit(case, payload)
    chronology_uid_recall = _chronology_uid_recall(case, payload)
    chronology_source_id_hit = _chronology_source_id_hit(case, payload)
    chronology_source_id_recall = _chronology_source_id_recall(case, payload)
    behavior_tag_coverage = _behavior_tag_coverage(case, payload)
    behavior_tag_precision = _behavior_tag_precision(case, payload)
    counter_indicator_quality = _counter_indicator_quality(case, payload)
    overclaim_guard_match = _overclaim_guard_match(case, payload)
    report_completeness = _report_completeness(case, payload)
    legal_support_product_completeness = _legal_support_product_completeness(case, payload)
    legal_support_grounding_hit = _legal_support_grounding_hit(case, payload)
    legal_support_grounding_recall = _legal_support_grounding_recall(case, payload)
    comparator_matrix_coverage = _comparator_matrix_coverage(case, payload)
    dashboard_card_coverage = _dashboard_card_coverage(case, payload)
    actor_map_coverage = _actor_map_coverage(case, payload)
    checklist_group_coverage = _checklist_group_coverage(case, payload)
    drafting_ceiling_match = _drafting_ceiling_match(case, payload)
    draft_section_completeness = _draft_section_completeness(case, payload)
    answer_content_match = _answer_content_match(case, payload)
    archive_harvest_coverage_pass = _archive_harvest_coverage_pass(case, payload)
    archive_harvest_quality_pass = _archive_harvest_quality_pass(case, payload)
    archive_harvest_mixed_source_present = _archive_harvest_mixed_source_present(case, payload)
    archive_harvest_later_round_recovery = _archive_harvest_later_round_recovery(case, payload)
    forbidden_support_ids_excluded = _forbidden_support_ids_excluded(case, payload)
    forbidden_issue_ids_excluded = _forbidden_issue_ids_excluded(case, payload)
    forbidden_actor_ids_excluded = _forbidden_actor_ids_excluded(case, payload)
    forbidden_dashboard_cards_excluded = _forbidden_dashboard_cards_excluded(case, payload)
    forbidden_checklist_groups_excluded = _forbidden_checklist_groups_excluded(case, payload)
    benchmark_recovery: dict[str, Any] = {}
    if case.benchmark_pack:
        from .qa_eval_bootstrap import benchmark_detection_recovery

        benchmark_recovery = benchmark_detection_recovery(benchmark_pack=case.benchmark_pack, payload=payload)

    def _benchmark_coverage(key: str) -> float | None:
        section = benchmark_recovery.get(key) or {}
        if int((section or {}).get("total") or 0) <= 0:
            return None
        value = (section or {}).get("coverage")
        return float(value) if value is not None else None

    def _benchmark_total(key: str) -> int:
        return int((benchmark_recovery.get(key) or {}).get("total") or 0)

    result = {
        "id": case.id,
        "bucket": case.bucket,
        "question": case.question,
        "status": case.status,
        "source": source,
        "count": int(payload.get("count") or 0),
        "top_uid": top_uid,
        "candidate_uids": candidate_uids,
        "attachment_candidate_uids": attachment_candidate_uids,
        "matched_support_uids": matched_support,
        "matched_support_uids_top_3": matched_support_top_3,
        "top_1_correctness": top_1_correctness,
        "support_uid_hit": support_uid_hit,
        "support_uid_hit_top_3": support_uid_hit_top_3,
        "support_uid_recall": support_uid_recall,
        "support_source_id_hit": support_source_id_hit,
        "support_source_id_recall": support_source_id_recall,
        "evidence_precision": evidence_precision,
        "top_uid_match": top_uid_match,
        "ambiguity_match": ambiguity_match,
        "confidence_calibration_match": confidence_calibration_match,
        "attachment_support_uid_hit": attachment_support_uid_hit,
        "attachment_answer_success": attachment_answer_success,
        "attachment_text_evidence_success": attachment_text_evidence_success,
        "attachment_ocr_text_evidence_success": attachment_ocr_text_evidence_success,
        "weak_evidence_explained": weak_evidence_explained,
        "long_thread_answer_present": long_thread_answer_present,
        "long_thread_structure_preserved": long_thread_structure_preserved,
        "observed_quoted_speaker_emails": observed_quoted_speaker_emails,
        "matched_quoted_speaker_emails": matched_quoted_speakers,
        "quote_attribution_precision": quote_attribution_precision,
        "quote_attribution_coverage": quote_attribution_coverage,
        "observed_thread_group_id": observed_thread_group_id,
        "observed_thread_group_source": observed_thread_group_source,
        "thread_group_id_match": thread_group_id_match,
        "thread_group_source_match": thread_group_source_match,
        "case_bundle_present": case_bundle_present,
        "investigation_blocks_present": investigation_blocks_present,
        "case_bundle_support_uid_hit": case_bundle_support_uid_hit,
        "case_bundle_support_uid_recall": case_bundle_support_uid_recall,
        "case_bundle_support_source_id_hit": case_bundle_support_source_id_hit,
        "case_bundle_support_source_id_recall": case_bundle_support_source_id_recall,
        "multi_source_source_types_match": multi_source_source_types_match,
        "chronology_uid_hit": chronology_uid_hit,
        "chronology_uid_recall": chronology_uid_recall,
        "chronology_source_id_hit": chronology_source_id_hit,
        "chronology_source_id_recall": chronology_source_id_recall,
        "behavior_tag_coverage": behavior_tag_coverage,
        "behavior_tag_precision": behavior_tag_precision,
        "counter_indicator_quality": counter_indicator_quality,
        "overclaim_guard_match": overclaim_guard_match,
        "report_completeness": report_completeness,
        "legal_support_product_completeness": legal_support_product_completeness,
        "legal_support_grounding_hit": legal_support_grounding_hit,
        "legal_support_grounding_recall": legal_support_grounding_recall,
        "comparator_matrix_coverage": comparator_matrix_coverage,
        "dashboard_card_coverage": dashboard_card_coverage,
        "actor_map_coverage": actor_map_coverage,
        "checklist_group_coverage": checklist_group_coverage,
        "drafting_ceiling_match": drafting_ceiling_match,
        "draft_section_completeness": draft_section_completeness,
        "answer_content_match": answer_content_match,
        "archive_harvest_coverage_pass": archive_harvest_coverage_pass,
        "archive_harvest_quality_pass": archive_harvest_quality_pass,
        "archive_harvest_mixed_source_present": archive_harvest_mixed_source_present,
        "archive_harvest_later_round_recovery": archive_harvest_later_round_recovery,
        "forbidden_support_ids_excluded": forbidden_support_ids_excluded,
        "forbidden_issue_ids_excluded": forbidden_issue_ids_excluded,
        "forbidden_actor_ids_excluded": forbidden_actor_ids_excluded,
        "forbidden_dashboard_cards_excluded": forbidden_dashboard_cards_excluded,
        "forbidden_checklist_groups_excluded": forbidden_checklist_groups_excluded,
        "benchmark_actor_recovery": _benchmark_coverage("actor_recovery"),
        "benchmark_actor_recovery_total": _benchmark_total("actor_recovery"),
        "benchmark_issue_family_recovery": _benchmark_coverage("issue_family_recovery"),
        "benchmark_issue_family_recovery_total": _benchmark_total("issue_family_recovery"),
        "benchmark_chronology_anchor_recovery": _benchmark_coverage("chronology_anchor_recovery"),
        "benchmark_chronology_anchor_recovery_total": _benchmark_total("chronology_anchor_recovery"),
        "benchmark_manifest_link_recovery": _benchmark_coverage("manifest_link_recovery"),
        "benchmark_manifest_link_recovery_total": _benchmark_total("manifest_link_recovery"),
        "benchmark_report_recovery": _benchmark_coverage("mixed_source_report_completeness"),
        "benchmark_report_recovery_total": _benchmark_total("mixed_source_report_completeness"),
        "benchmark_detection_recovery": benchmark_recovery or None,
        "expected_ambiguity": case.expected_ambiguity,
        "observed_confidence_label": (payload.get("answer_quality") or {}).get("confidence_label"),
        "observed_ambiguity_reason": (payload.get("answer_quality") or {}).get("ambiguity_reason"),
    }

    slice_a_metrics: dict[str, Any] = {
        "slice_a_exact_verified_quote_rate": _slice_a_exact_verified_quote_rate(case, payload),
        "slice_a_near_exact_quote_rate": _slice_a_near_exact_quote_rate(case, payload),
        "slice_a_false_exact_flag": _slice_a_false_exact_flag(case, payload),
        "slice_a_locator_completeness": _slice_a_locator_completeness(case, payload),
        "slice_a_ocr_heavy_attachment_recall": _slice_a_ocr_heavy_attachment_recall(case, payload),
        "slice_a_authored_german_primary_match": _slice_a_authored_german_primary_match(case, payload),
        "slice_a_contradiction_pair_precision": _slice_a_contradiction_pair_precision(case, payload),
        "slice_a_mixed_source_completeness": _slice_a_mixed_source_completeness(case, payload),
        "slice_a_calendar_exclusion_visible": _slice_a_calendar_exclusion_visible(case, payload),
        "slice_a_silence_omission_anchor_match": _slice_a_silence_omission_anchor_match(case, payload),
    }
    for metric, value in slice_a_metrics.items():
        if value is not None:
            result[metric] = value

    return result


def summarize_evaluation(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize evaluation outcomes across all scored cases."""
    return _summarize_evaluation(results)
