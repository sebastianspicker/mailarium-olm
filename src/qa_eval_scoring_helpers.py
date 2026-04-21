# mypy: disable-error-code=name-defined
# ruff: noqa: F403, F405, RUF022
"""Compatibility facade for split QA evaluation scoring helpers."""

from __future__ import annotations

from . import qa_eval_scoring_behavior_metrics as _qa_eval_scoring_behavior_metrics
from . import qa_eval_scoring_case_metrics as _qa_eval_scoring_case_metrics
from . import qa_eval_scoring_core as _qa_eval_scoring_core
from . import qa_eval_scoring_legal_metrics as _qa_eval_scoring_legal_metrics
from . import qa_eval_scoring_slice_a as _qa_eval_scoring_slice_a
from . import qa_eval_scoring_summary as _qa_eval_scoring_summary
from .qa_eval_scoring_behavior_metrics import *
from .qa_eval_scoring_case_metrics import *
from .qa_eval_scoring_core import *
from .qa_eval_scoring_legal_metrics import *
from .qa_eval_scoring_slice_a import *
from .qa_eval_scoring_summary import *

_SPLIT_MODULES = (
    _qa_eval_scoring_core,
    _qa_eval_scoring_case_metrics,
    _qa_eval_scoring_behavior_metrics,
    _qa_eval_scoring_legal_metrics,
    _qa_eval_scoring_slice_a,
    _qa_eval_scoring_summary,
)
_WRAPPED_EXPORTS: set[str] = set()


def _bind_split_namespace() -> None:
    namespace = {}
    for module in _SPLIT_MODULES:
        namespace.update({name: getattr(module, name) for name in getattr(module, "__all__", ())})
    for module in _SPLIT_MODULES:
        module.__dict__.update(namespace)
    globals().update({key: value for key, value in namespace.items() if key not in _WRAPPED_EXPORTS})


_bind_split_namespace()


__all__ = [
    "_ANSWER_TERM_RE",
    "_ANSWER_STOPWORDS",
    "_normalize_eval_text",
    "_append_unique",
    "_collect_identifiers",
    "_dict_has_substance",
    "_as_dict",
    "_as_list",
    "_expected_answer_terms",
    "_answer_content_match",
    "_archive_harvest_section",
    "_archive_harvest_coverage_pass",
    "_archive_harvest_quality_pass",
    "_archive_harvest_mixed_source_present",
    "_archive_harvest_later_round_recovery",
    "_observed_support_source_ids",
    "_support_source_id_hit",
    "_support_source_id_recall",
    "_bundle_support_source_ids",
    "_bundle_support_uids",
    "_legal_support_product_source_ids",
    "_observed_issue_ids",
    "_observed_actor_ids",
    "_observed_dashboard_card_ids",
    "_observed_checklist_group_ids",
    "_forbidden_values_absent",
    "_candidate_uids",
    "_uids_for_key",
    "_strong_attachment_support_uid_hit",
    "_strong_attachment_ocr_support_uid_hit",
    "_weak_evidence_explained",
    "_resolve_top_uid",
    "_long_thread_answer_present",
    "_long_thread_structure_preserved",
    "_ambiguity_matches",
    "_ratio",
    "_average_metric",
    "_observed_quoted_speaker_emails",
    "_case_bundle_present",
    "_investigation_blocks_present",
    "_case_bundle_support_uid_hit",
    "_case_bundle_support_uid_recall",
    "_case_bundle_support_source_id_hit",
    "_case_bundle_support_source_id_recall",
    "_multi_source_source_types_match",
    "_timeline_uids",
    "_chronology_uid_hit",
    "_chronology_uid_recall",
    "_chronology_source_ids",
    "_chronology_source_id_hit",
    "_chronology_source_id_recall",
    "_observed_behavior_ids",
    "_behavior_tag_coverage",
    "_behavior_tag_precision",
    "_observed_counter_indicator_texts",
    "_counter_indicator_quality",
    "_claim_level_rank",
    "_report_claim_levels",
    "_overclaim_guard_match",
    "_report_completeness",
    "_legal_support_product_completeness",
    "_legal_support_grounding_hit",
    "_legal_support_grounding_recall",
    "_observed_comparator_issue_ids",
    "_comparator_matrix_coverage",
    "_dashboard_card_coverage",
    "_actor_map_coverage",
    "_checklist_group_coverage",
    "_drafting_ceiling_match",
    "_draft_section_completeness",
    "_forbidden_support_ids_excluded",
    "_forbidden_issue_ids_excluded",
    "_forbidden_actor_ids_excluded",
    "_forbidden_dashboard_cards_excluded",
    "_forbidden_checklist_groups_excluded",
    "_slice_a_config",
    "_source_id_from_candidate",
    "_quote_match_class_from_candidate",
    "_quote_support_source_ids",
    "_locator_has_reversible_fields",
    "_slice_a_exact_verified_quote_rate",
    "_slice_a_near_exact_quote_rate",
    "_slice_a_false_exact_flag",
    "_slice_a_locator_completeness",
    "_slice_a_authored_german_primary_match",
    "_slice_a_contradiction_pair_precision",
    "_slice_a_ocr_heavy_attachment_recall",
    "_slice_a_mixed_source_completeness",
    "_slice_a_calendar_exclusion_visible",
    "_slice_a_silence_omission_anchor_match",
    "summarize_evaluation",
]
