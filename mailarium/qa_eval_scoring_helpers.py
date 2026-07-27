"""Public facade for generic QA scoring helpers."""

from .qa_eval_scoring_core import (
    _ambiguity_matches,
    _answer_content_match,
    _average_metric,
    _candidate_uids,
    _forbidden_support_ids_excluded,
    _long_thread_answer_present,
    _long_thread_structure_preserved,
    _observed_quoted_speaker_emails,
    _ratio,
    _resolve_top_uid,
    _strong_attachment_ocr_support_uid_hit,
    _strong_attachment_support_uid_hit,
    _support_source_id_hit,
    _support_source_id_recall,
    _uids_for_key,
    _weak_evidence_explained,
)
from .qa_eval_scoring_summary import summarize_evaluation

__all__ = [
    "_ambiguity_matches",
    "_answer_content_match",
    "_average_metric",
    "_candidate_uids",
    "_forbidden_support_ids_excluded",
    "_long_thread_answer_present",
    "_long_thread_structure_preserved",
    "_observed_quoted_speaker_emails",
    "_ratio",
    "_resolve_top_uid",
    "_strong_attachment_ocr_support_uid_hit",
    "_strong_attachment_support_uid_hit",
    "_support_source_id_hit",
    "_support_source_id_recall",
    "_uids_for_key",
    "_weak_evidence_explained",
    "summarize_evaluation",
]
