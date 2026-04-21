# mypy: disable-error-code=name-defined
"""Split QA evaluation scoring helpers (qa_eval_scoring_core)."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .qa_eval_cases import QuestionCase

_ANSWER_TERM_RE = re.compile(r"[0-9a-zA-ZäöüÄÖÜß._-]+")
_ANSWER_STOPWORDS = {
    "aber",
    "after",
    "and",
    "auch",
    "because",
    "beim",
    "beziehungsweise",
    "dann",
    "dass",
    "dem",
    "denn",
    "der",
    "des",
    "die",
    "dies",
    "does",
    "eine",
    "einer",
    "eines",
    "evidence",
    "from",
    "have",
    "into",
    "kein",
    "keine",
    "likely",
    "message",
    "nach",
    "oder",
    "over",
    "says",
    "sein",
    "some",
    "that",
    "their",
    "there",
    "these",
    "this",
    "under",
    "used",
    "with",
    "without",
}

# ruff: noqa: F401


def _normalize_eval_text(value: str) -> str:
    return " ".join((value or "").casefold().split())


def _append_unique(values: list[str], value: Any) -> None:
    compact = str(value or "").strip()
    if compact and compact not in values:
        values.append(compact)


def _collect_identifiers(value: Any, *, field_names: set[str], observed: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in field_names:
                if isinstance(item, list):
                    for member in item:
                        _append_unique(observed, member)
                else:
                    _append_unique(observed, item)
            _collect_identifiers(item, field_names=field_names, observed=observed)
        return
    if isinstance(value, list):
        for item in value:
            _collect_identifiers(item, field_names=field_names, observed=observed)


def _dict_has_substance(value: dict[str, Any]) -> bool:
    for item in value.values():
        if isinstance(item, dict) and item and _dict_has_substance(item):
            return True
        if isinstance(item, list) and any(
            (isinstance(member, dict) and bool(member)) or member not in (None, "", [], {}) for member in item
        ):
            return True
        if item not in (None, "", [], {}):
            return True
    return False


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _expected_answer_terms(case: QuestionCase) -> list[str]:
    explicit = [str(term).strip().casefold() for term in case.expected_answer_terms if str(term).strip()]
    if explicit:
        return list(dict.fromkeys(explicit))
    normalized_answer = _normalize_eval_text(case.expected_answer)
    if not normalized_answer:
        return []
    derived = [
        token.casefold()
        for token in _ANSWER_TERM_RE.findall(normalized_answer)
        if len(token) >= 4 and token.casefold() not in _ANSWER_STOPWORDS
    ]
    return list(dict.fromkeys(derived[:8]))


def _answer_content_match(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    expected_terms = _expected_answer_terms(case)
    if not expected_terms:
        return None
    final_answer = payload.get("final_answer")
    if not isinstance(final_answer, dict):
        return False
    answer_text = _normalize_eval_text(str(final_answer.get("text") or ""))
    if not answer_text:
        return False
    return all(term in answer_text for term in expected_terms)


def _archive_harvest_section(payload: dict[str, Any]) -> dict[str, Any]:
    archive_harvest = payload.get("archive_harvest")
    if isinstance(archive_harvest, dict):
        return archive_harvest
    retrieval_diagnostics = payload.get("retrieval_diagnostics")
    if isinstance(retrieval_diagnostics, dict):
        candidate = retrieval_diagnostics.get("archive_harvest")
        if isinstance(candidate, dict):
            return candidate
    retrieval_plan = payload.get("retrieval_plan")
    if isinstance(retrieval_plan, dict):
        candidate = retrieval_plan.get("archive_harvest")
        if isinstance(candidate, dict):
            return candidate
    return {}


def _archive_harvest_coverage_pass(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    del case
    archive_harvest = _archive_harvest_section(payload)
    if not archive_harvest:
        return None
    return str(_as_dict(archive_harvest.get("coverage_gate")).get("status") or "") == "pass"


def _archive_harvest_quality_pass(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    del case
    archive_harvest = _archive_harvest_section(payload)
    if not archive_harvest:
        return None
    return str(_as_dict(archive_harvest.get("quality_gate")).get("status") or "") == "pass"


def _archive_harvest_mixed_source_present(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    del case
    archive_harvest = _archive_harvest_section(payload)
    if not archive_harvest:
        return None
    mixed_source_metrics = _as_dict(archive_harvest.get("mixed_source_metrics"))
    mixed_source_candidate_count = int(archive_harvest.get("mixed_source_candidate_count") or 0)
    return mixed_source_candidate_count > 0 or int(mixed_source_metrics.get("non_email_source_count") or 0) > 0


def _archive_harvest_later_round_recovery(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    del case
    archive_harvest = _archive_harvest_section(payload)
    if not archive_harvest:
        return None
    later_round = [str(item) for item in _as_list(archive_harvest.get("later_round_only_evidence_handles")) if str(item).strip()]
    rerun_rounds = [item for item in _as_list(archive_harvest.get("rerun_rounds")) if isinstance(item, dict)]
    return bool(later_round) or any(int(item.get("recovered_count") or 0) > 0 for item in rerun_rounds[1:])


def _observed_support_source_ids(payload: dict[str, Any]) -> list[str]:
    observed: list[str] = []
    for key in ("candidates", "attachment_candidates"):
        for item in payload.get(key, []) or []:
            if not isinstance(item, dict):
                continue
            _append_unique(observed, item.get("source_id"))
            uid = str(item.get("uid") or "").strip()
            if uid and not str(item.get("source_id") or "").strip():
                _append_unique(observed, f"email:{uid}")
            provenance = item.get("provenance")
            if isinstance(provenance, dict):
                _append_unique(observed, provenance.get("evidence_handle"))
            locator = item.get("document_locator")
            if isinstance(locator, dict):
                _append_unique(observed, locator.get("evidence_handle"))
    return observed


def _support_source_id_hit(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if not case.expected_support_source_ids:
        return None
    observed = _observed_support_source_ids(payload)
    return any(source_id in observed for source_id in case.expected_support_source_ids)


def _support_source_id_recall(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    if not case.expected_support_source_ids:
        return None
    observed = _observed_support_source_ids(payload)
    matched = [source_id for source_id in case.expected_support_source_ids if source_id in observed]
    return _ratio(len(matched), len(case.expected_support_source_ids))


def _bundle_support_source_ids(payload: dict[str, Any]) -> list[str]:
    observed: list[str] = []
    for key in (
        "multi_source_case_bundle",
        "finding_evidence_index",
        "matter_evidence_index",
        "master_chronology",
        "investigation_report",
        "lawyer_issue_matrix",
        "case_dashboard",
        "document_request_checklist",
        "controlled_factual_drafting",
    ):
        _collect_identifiers(
            payload.get(key),
            field_names={"source_id", "source_ids", "supporting_source_ids", "evidence_handle", "evidence_handles"},
            observed=observed,
        )
    return observed


def _bundle_support_uids(payload: dict[str, Any]) -> list[str]:
    observed: list[str] = []
    for key in ("multi_source_case_bundle", "finding_evidence_index", "matter_evidence_index", "master_chronology"):
        _collect_identifiers(
            payload.get(key),
            field_names={"uid", "supporting_uids", "message_or_document_id"},
            observed=observed,
        )
    return observed


def _legal_support_product_source_ids(payload: dict[str, Any], *, product_ids: list[str]) -> list[str]:
    observed: list[str] = []
    for product_id in product_ids:
        product = payload.get(product_id)
        if not isinstance(product, dict):
            continue
        _collect_identifiers(
            product,
            field_names={"source_id", "source_ids", "supporting_source_ids", "evidence_handle", "evidence_handles"},
            observed=observed,
        )
    return observed


def _observed_issue_ids(payload: dict[str, Any]) -> list[str]:
    observed: list[str] = []
    for key in ("lawyer_issue_matrix", "comparative_treatment", "case_dashboard"):
        _collect_identifiers(payload.get(key), field_names={"issue_id"}, observed=observed)
    return observed


def _observed_actor_ids(payload: dict[str, Any]) -> list[str]:
    observed: list[str] = []
    _collect_identifiers(payload.get("actor_map"), field_names={"actor_id"}, observed=observed)
    _collect_identifiers(payload.get("case_dashboard"), field_names={"actor_id"}, observed=observed)
    return observed


def _observed_dashboard_card_ids(payload: dict[str, Any]) -> list[str]:
    dashboard = payload.get("case_dashboard")
    if not isinstance(dashboard, dict):
        return []
    cards = dashboard.get("cards")
    if not isinstance(cards, dict):
        return []
    return [str(card_id) for card_id, rows in cards.items() if str(card_id).strip() and isinstance(rows, list)]


def _observed_checklist_group_ids(payload: dict[str, Any]) -> list[str]:
    observed: list[str] = []
    _collect_identifiers(payload.get("document_request_checklist"), field_names={"group_id"}, observed=observed)
    return observed


def _forbidden_values_absent(forbidden_values: list[str], observed_values: list[str]) -> bool | None:
    forbidden = [str(value).strip() for value in forbidden_values if str(value).strip()]
    if not forbidden:
        return None
    observed = {str(value).strip() for value in observed_values if str(value).strip()}
    return not any(value in observed for value in forbidden)


def _candidate_uids(payload: dict[str, Any]) -> list[str]:
    uids: list[str] = []
    for key in ("candidates", "attachment_candidates"):
        for item in payload.get(key, []):
            uid = item.get("uid")
            if uid and uid not in uids:
                uids.append(str(uid))
    return uids


def _uids_for_key(payload: dict[str, Any], key: str) -> list[str]:
    uids: list[str] = []
    for item in payload.get(key, []):
        uid = item.get("uid")
        if uid and uid not in uids:
            uids.append(str(uid))
    return uids


def _strong_attachment_support_uid_hit(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if case.bucket != "attachment_lookup" or not case.expected_support_uids:
        return None
    for item in payload.get("attachment_candidates", []):
        uid = str(item.get("uid") or "")
        if uid not in case.expected_support_uids:
            continue
        attachment = item.get("attachment") or {}
        if not isinstance(attachment, dict):
            continue
        if str(attachment.get("evidence_strength") or "") == "strong_text":
            return True
    return False


def _strong_attachment_ocr_support_uid_hit(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if case.bucket != "attachment_lookup" or not case.expected_support_uids or "attachment_ocr" not in case.triage_tags:
        return None
    for item in payload.get("attachment_candidates", []):
        uid = str(item.get("uid") or "")
        if uid not in case.expected_support_uids:
            continue
        attachment = item.get("attachment") or {}
        if not isinstance(attachment, dict):
            continue
        if (
            str(attachment.get("evidence_strength") or "") == "strong_text"
            and bool(attachment.get("ocr_used"))
            and str(attachment.get("extraction_state") or "").strip().lower() == "ocr_text_extracted"
        ):
            return True
    return False


def _weak_evidence_explained(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if (case.expected_ambiguity or "").lower() != "insufficient":
        return None
    weak_reason_markers = {
        "weak_scan_body",
        "source_shell_only",
        "image_only",
        "metadata_only_reply",
        "true_blank",
        "attachment_only",
    }
    answer_quality = payload.get("answer_quality") or {}
    ambiguity_reason = str(answer_quality.get("ambiguity_reason") or "")
    if ambiguity_reason in weak_reason_markers:
        return True
    for key in ("candidates", "attachment_candidates"):
        for item in payload.get(key, []):
            weak_message = item.get("weak_message")
            if isinstance(weak_message, dict) and weak_message.get("code") in weak_reason_markers:
                return True
    return False


def _resolve_top_uid(payload: dict[str, Any]) -> str | None:
    answer_quality = payload.get("answer_quality") or {}
    top_uid = answer_quality.get("top_candidate_uid")
    if top_uid:
        return str(top_uid)
    for key in ("candidates", "attachment_candidates"):
        items = payload.get(key) or []
        if items:
            uid = items[0].get("uid")
            if uid:
                return str(uid)
    return None


def _long_thread_answer_present(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if "long_thread" not in case.triage_tags:
        return None
    final_answer = payload.get("final_answer")
    if not isinstance(final_answer, dict):
        return False
    return bool(str(final_answer.get("text") or "").strip())


def _long_thread_structure_preserved(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if "long_thread" not in case.triage_tags:
        return None
    conversation_groups = payload.get("conversation_groups")
    timeline = payload.get("timeline")
    timeline_events = timeline.get("events") if isinstance(timeline, dict) else None
    return bool(conversation_groups) and bool(timeline_events)


def _ambiguity_matches(expected: str | None, payload: dict[str, Any]) -> bool | None:
    if expected is None:
        return None
    answer_quality = payload.get("answer_quality") or {}
    label = str(answer_quality.get("confidence_label") or "").lower()
    reason = str(answer_quality.get("ambiguity_reason") or "").lower()
    count = int(payload.get("count") or 0)
    normalized = expected.lower()
    if normalized == "ambiguous":
        return label == "ambiguous" or bool(reason)
    if normalized == "clear":
        return label in {"high", "medium"} and not reason
    if normalized == "insufficient":
        return label == "low" or count == 0 or reason == "no_results"
    return None


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _average_metric(results: list[dict[str, Any]], metric: str) -> dict[str, float | int]:
    values = [float(result[metric]) for result in results if result.get(metric) is not None]
    if not values:
        return {"scorable": 0, "average": 0.0}
    return {"scorable": len(values), "average": round(sum(values) / len(values), 12)}


__all__ = [
    "_ANSWER_STOPWORDS",
    "_ANSWER_TERM_RE",
    "_ambiguity_matches",
    "_answer_content_match",
    "_append_unique",
    "_archive_harvest_coverage_pass",
    "_archive_harvest_later_round_recovery",
    "_archive_harvest_mixed_source_present",
    "_archive_harvest_quality_pass",
    "_archive_harvest_section",
    "_as_dict",
    "_as_list",
    "_average_metric",
    "_bundle_support_source_ids",
    "_bundle_support_uids",
    "_candidate_uids",
    "_collect_identifiers",
    "_dict_has_substance",
    "_expected_answer_terms",
    "_forbidden_values_absent",
    "_legal_support_product_source_ids",
    "_long_thread_answer_present",
    "_long_thread_structure_preserved",
    "_normalize_eval_text",
    "_observed_actor_ids",
    "_observed_checklist_group_ids",
    "_observed_dashboard_card_ids",
    "_observed_issue_ids",
    "_observed_support_source_ids",
    "_ratio",
    "_resolve_top_uid",
    "_strong_attachment_ocr_support_uid_hit",
    "_strong_attachment_support_uid_hit",
    "_support_source_id_hit",
    "_support_source_id_recall",
    "_uids_for_key",
    "_weak_evidence_explained",
]
