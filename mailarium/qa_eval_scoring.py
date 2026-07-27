"""Pure payload-scoring helpers for QA evaluation."""
# pylint: disable=too-many-locals,too-many-statements

from __future__ import annotations

from typing import Any

from .qa_eval_cases import QuestionCase
from .qa_eval_scoring_helpers import (
    _ambiguity_matches,
    _answer_content_match,
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
    result["answer_content_match"] = _answer_content_match(case, payload)
    result["forbidden_support_ids_excluded"] = _forbidden_support_ids_excluded(case, payload)
    result.update(_observed_answer_quality(case, payload))
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
        "evidence_precision": _ratio(len(matched), len(candidate_uids)) if case.expected_support_uids else None,
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


def _observed_answer_quality(case: QuestionCase, payload: dict[str, Any]) -> dict[str, Any]:
    quality = payload.get("answer_quality") or {}
    return {
        "expected_ambiguity": case.expected_ambiguity,
        "observed_confidence_label": quality.get("confidence_label"),
        "observed_ambiguity_reason": quality.get("ambiguity_reason"),
    }


def summarize_evaluation(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize evaluation outcomes across all scored cases."""
    return _summarize_evaluation(results)
