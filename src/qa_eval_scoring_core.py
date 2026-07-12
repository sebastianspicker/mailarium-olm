# mypy: disable-error-code=name-defined
# pylint: disable=E0602  # cross-module names injected by compatibility facade
"""Split QA evaluation scoring helpers (qa_eval_scoring_core)."""

from __future__ import annotations

import re
from typing import Any

from ._utils import _as_dict, _as_list
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


def _normalize_eval_text(value: str) -> str:
    """Normalize evaluation text by casefolding and collapsing whitespace."""
    return " ".join((value or "").casefold().split())


def _append_unique(values: list[str], value: Any) -> None:
    """Append a value to a list if it's non-empty and not already present."""
    compact = str(value or "").strip()
    if compact and compact not in values:
        values.append(compact)


def _collect_identifiers(value: Any, *, field_names: set[str], observed: list[str]) -> None:
    """Recursively collect identifier values from nested dicts/lists.

    Args:
        value: The value to search through (dict, list, or other).
        field_names: Set of field names whose values should be collected.
        observed: List to append unique found values to.
    """
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
    """Check if a dict contains any non-empty, non-null values recursively.

    Returns:
        True if the dict has substance (non-empty nested dicts, non-empty lists,
        or non-null/non-empty primitive values), False otherwise.
    """
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


def _expected_answer_terms(case: QuestionCase) -> list[str]:
    """Extract expected answer terms from a question case.

    If explicit expected_answer_terms are provided, use those. Otherwise, derive
    terms from the expected_answer text by tokenizing and filtering stopwords.

    Args:
        case: The question case containing expected answer information.

    Returns:
        List of unique, normalized answer terms (max 8 derived terms).
    """
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
    """Check if the final answer text contains all expected answer terms.

    Args:
        case: The question case with expected answer terms.
        payload: The payload containing the final_answer to check.

    Returns:
        True if all expected terms are found in the answer text, False if not,
        None if no expected terms or no answer text available.
    """
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
    """Extract the archive_harvest section from a payload.

    Looks for archive_harvest in multiple possible locations within the payload
    structure (top-level, retrieval_diagnostics, retrieval_plan).

    Args:
        payload: The payload dict to search through.

    Returns:
        The archive_harvest dict if found, otherwise an empty dict.
    """
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
    """Check if archive harvest coverage gate passed.

    Args:
        case: The question case (unused, for signature compatibility).
        payload: The payload containing archive_harvest data.

    Returns:
        True if coverage gate status is 'pass', None if no archive_harvest found.
    """
    del case
    archive_harvest = _archive_harvest_section(payload)
    if not archive_harvest:
        return None
    return str(_as_dict(archive_harvest.get("coverage_gate")).get("status") or "") == "pass"


def _archive_harvest_quality_pass(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    """Check if archive harvest quality gate passed.

    Args:
        case: The question case (unused, for signature compatibility).
        payload: The payload containing archive_harvest data.

    Returns:
        True if quality gate status is 'pass', None if no archive_harvest found.
    """
    del case
    archive_harvest = _archive_harvest_section(payload)
    if not archive_harvest:
        return None
    return str(_as_dict(archive_harvest.get("quality_gate")).get("status") or "") == "pass"


def _archive_harvest_mixed_source_present(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    """Check if archive harvest contains mixed source evidence.

    Args:
        case: The question case (unused, for signature compatibility).
        payload: The payload containing archive_harvest data.

    Returns:
        True if mixed source candidates or non-email sources are present,
        None if no archive_harvest found.
    """
    del case
    archive_harvest = _archive_harvest_section(payload)
    if not archive_harvest:
        return None
    mixed_source_metrics = _as_dict(archive_harvest.get("mixed_source_metrics"))
    mixed_source_candidate_count = int(archive_harvest.get("mixed_source_candidate_count") or 0)
    return mixed_source_candidate_count > 0 or int(mixed_source_metrics.get("non_email_source_count") or 0) > 0


def _archive_harvest_later_round_recovery(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    """Check if archive harvest recovered evidence in later rounds.

    Args:
        case: The question case (unused, for signature compatibility).
        payload: The payload containing archive_harvest data.

    Returns:
        True if later round evidence or rerun rounds with recovered items exist,
        None if no archive_harvest found.
    """
    del case
    archive_harvest = _archive_harvest_section(payload)
    if not archive_harvest:
        return None
    later_round = [str(item) for item in _as_list(archive_harvest.get("later_round_only_evidence_handles")) if str(item).strip()]
    rerun_rounds = [item for item in _as_list(archive_harvest.get("rerun_rounds")) if isinstance(item, dict)]
    return bool(later_round) or any(int(item.get("recovered_count") or 0) > 0 for item in rerun_rounds[1:])


def _observed_support_source_ids(payload: dict[str, Any]) -> list[str]:
    """Extract observed source IDs from candidates and attachment_candidates.

    Collects source_id, uid (as email:uid), provenance.evidence_handle, and
    document_locator.evidence_handle from candidate items.

    Args:
        payload: The payload dict containing candidates.

    Returns:
        List of unique observed source IDs.
    """
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
    """Check if any expected support source ID is present in observed sources.

    Args:
        case: The question case with expected_support_source_ids.
        payload: The payload to extract observed source IDs from.

    Returns:
        True if at least one expected source ID is found, None if no expected IDs.
    """
    if not case.expected_support_source_ids:
        return None
    observed = _observed_support_source_ids(payload)
    return any(source_id in observed for source_id in case.expected_support_source_ids)


def _support_source_id_recall(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    """Calculate recall ratio of expected support source IDs found in observed.

    Args:
        case: The question case with expected_support_source_ids.
        payload: The payload to extract observed source IDs from.

    Returns:
        Ratio of matched expected source IDs to total expected (0.0-1.0),
        None if no expected IDs.
    """
    if not case.expected_support_source_ids:
        return None
    observed = _observed_support_source_ids(payload)
    matched = [source_id for source_id in case.expected_support_source_ids if source_id in observed]
    return _ratio(len(matched), len(case.expected_support_source_ids))


def _bundle_support_source_ids(payload: dict[str, Any]) -> list[str]:
    """Extract source IDs from legal support product bundles in payload.

    Searches through various bundle keys (multi_source_case_bundle, finding_evidence_index,
    etc.) and collects values from specified field names.

    Args:
        payload: The payload dict containing bundle data.

    Returns:
        List of unique observed source IDs from bundles.
    """
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
    """Extract UIDs from legal support product bundles in payload.

    Searches through bundle keys and collects uid, supporting_uids, and
    message_or_document_id values.

    Args:
        payload: The payload dict containing bundle data.

    Returns:
        List of unique observed UIDs from bundles.
    """
    observed: list[str] = []
    for key in ("multi_source_case_bundle", "finding_evidence_index", "matter_evidence_index", "master_chronology"):
        _collect_identifiers(
            payload.get(key),
            field_names={"uid", "supporting_uids", "message_or_document_id"},
            observed=observed,
        )
    return observed


def _legal_support_product_source_ids(payload: dict[str, Any], *, product_ids: list[str]) -> list[str]:
    """Extract source IDs from specific legal support products in payload.

    Args:
        payload: The payload dict containing product data.
        product_ids: List of product keys to search through.

    Returns:
        List of unique observed source IDs from the specified products.
    """
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
    """Extract observed issue IDs from legal support products.

    Searches through lawyer_issue_matrix, comparative_treatment, and case_dashboard
    for issue_id field values.

    Args:
        payload: The payload dict containing product data.

    Returns:
        List of unique observed issue IDs.
    """
    observed: list[str] = []
    for key in ("lawyer_issue_matrix", "comparative_treatment", "case_dashboard"):
        _collect_identifiers(payload.get(key), field_names={"issue_id"}, observed=observed)
    return observed


def _observed_actor_ids(payload: dict[str, Any]) -> list[str]:
    """Extract observed actor IDs from actor_map and case_dashboard.

    Args:
        payload: The payload dict containing actor data.

    Returns:
        List of unique observed actor IDs.
    """
    observed: list[str] = []
    _collect_identifiers(payload.get("actor_map"), field_names={"actor_id"}, observed=observed)
    _collect_identifiers(payload.get("case_dashboard"), field_names={"actor_id"}, observed=observed)
    return observed


def _observed_dashboard_card_ids(payload: dict[str, Any]) -> list[str]:
    """Extract card IDs from case_dashboard.cards.

    Args:
        payload: The payload dict containing case_dashboard data.

    Returns:
        List of card IDs that have associated rows in the dashboard.
    """
    dashboard = payload.get("case_dashboard")
    if not isinstance(dashboard, dict):
        return []
    cards = dashboard.get("cards")
    if not isinstance(cards, dict):
        return []
    return [str(card_id) for card_id, rows in cards.items() if str(card_id).strip() and isinstance(rows, list)]


def _observed_checklist_group_ids(payload: dict[str, Any]) -> list[str]:
    """Extract group IDs from document_request_checklist.

    Args:
        payload: The payload dict containing checklist data.

    Returns:
        List of unique observed group IDs.
    """
    observed: list[str] = []
    _collect_identifiers(payload.get("document_request_checklist"), field_names={"group_id"}, observed=observed)
    return observed


def _forbidden_values_absent(forbidden_values: list[str], observed_values: list[str]) -> bool | None:
    """Check if none of the forbidden values appear in observed values.

    Args:
        forbidden_values: List of values that should not be present.
        observed_values: List of values to check against forbidden list.

    Returns:
        True if no forbidden values are found in observed, None if no forbidden values.
    """
    forbidden = [str(value).strip() for value in forbidden_values if str(value).strip()]
    if not forbidden:
        return None
    observed = {str(value).strip() for value in observed_values if str(value).strip()}
    return not any(value in observed for value in forbidden)


def _candidate_uids(payload: dict[str, Any]) -> list[str]:
    """Extract unique UIDs from candidates and attachment_candidates.

    Args:
        payload: The payload dict containing candidate data.

    Returns:
        List of unique candidate UIDs.
    """
    uids: list[str] = []
    for key in ("candidates", "attachment_candidates"):
        for item in payload.get(key, []):
            uid = item.get("uid")
            if uid and uid not in uids:
                uids.append(str(uid))
    return uids


def _uids_for_key(payload: dict[str, Any], key: str) -> list[str]:
    """Extract unique UIDs from items at a specific key in payload.

    Args:
        payload: The payload dict to search.
        key: The key whose list value contains items with uid fields.

    Returns:
        List of unique UIDs from the specified key's items.
    """
    uids: list[str] = []
    for item in payload.get(key, []):
        uid = item.get("uid")
        if uid and uid not in uids:
            uids.append(str(uid))
    return uids


def _strong_attachment_support_uid_hit(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    """Check if any expected support UID has strong_text evidence strength in attachments.

    Only applies to attachment_lookup bucket cases.

    Args:
        case: The question case with expected_support_uids.
        payload: The payload containing attachment_candidates.

    Returns:
        True if a matching attachment has evidence_strength='strong_text',
        None if not attachment_lookup bucket or no expected UIDs.
    """
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
    """Check if any expected support UID has strong_text OCR evidence in attachments.

    Only applies to attachment_lookup bucket cases with attachment_ocr triage tag.

    Args:
        case: The question case with expected_support_uids and attachment_ocr tag.
        payload: The payload containing attachment_candidates.

    Returns:
        True if a matching attachment has evidence_strength='strong_text',
        ocr_used=True, and extraction_state='ocr_text_extracted',
        None if conditions are not met.
    """
    if case.bucket != "attachment_lookup" or not case.expected_support_uids or "attachment_ocr" not in case.triage_tags:
        return None
    return any(_is_strong_ocr_attachment(item, case.expected_support_uids) for item in payload.get("attachment_candidates", []))


def _is_strong_ocr_attachment(item: dict[str, Any], expected_uids: list[str]) -> bool:
    attachment = item.get("attachment") or {}
    return (
        str(item.get("uid") or "") in expected_uids
        and isinstance(attachment, dict)
        and str(attachment.get("evidence_strength") or "") == "strong_text"
        and bool(attachment.get("ocr_used"))
        and str(attachment.get("extraction_state") or "").strip().lower() == "ocr_text_extracted"
    )


def _weak_evidence_explained(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    """Check if weak evidence is properly explained when ambiguity is insufficient.

    Only applies when expected_ambiguity is 'insufficient'. Checks for specific
    weak reason markers in answer_quality or candidate weak_message codes.

    Args:
        case: The question case with expected_ambiguity.
        payload: The payload containing answer_quality and candidates.

    Returns:
        True if weak evidence has an explanation, None if ambiguity is not insufficient.
    """
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
    """Resolve the top candidate UID from payload.

    Tries answer_quality.top_candidate_uid first, then falls back to the first
    candidate in candidates or attachment_candidates.

    Args:
        payload: The payload dict containing answer_quality and candidates.

    Returns:
        The top UID as a string, or None if not found.
    """
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
    """Check if final answer text is present for long_thread cases.

    Only applies to cases with 'long_thread' triage tag.

    Args:
        case: The question case with triage_tags.
        payload: The payload containing final_answer.

    Returns:
        True if final answer text is non-empty, False if empty,
        None if not a long_thread case.
    """
    if "long_thread" not in case.triage_tags:
        return None
    final_answer = payload.get("final_answer")
    if not isinstance(final_answer, dict):
        return False
    return bool(str(final_answer.get("text") or "").strip())


def _long_thread_structure_preserved(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    """Check if long thread structure (conversation_groups and timeline) is preserved.

    Only applies to cases with 'long_thread' triage tag.

    Args:
        case: The question case with triage_tags.
        payload: The payload containing conversation_groups and timeline.

    Returns:
        True if both conversation_groups and timeline.events are present,
        None if not a long_thread case.
    """
    if "long_thread" not in case.triage_tags:
        return None
    conversation_groups = payload.get("conversation_groups")
    timeline = payload.get("timeline")
    timeline_events = timeline.get("events") if isinstance(timeline, dict) else None
    return bool(conversation_groups) and bool(timeline_events)


def _ambiguity_matches(expected: str | None, payload: dict[str, Any]) -> bool | None:
    """Check if payload ambiguity matches expected ambiguity level.

    Compares expected ambiguity string ('ambiguous', 'clear', 'insufficient')
    against answer_quality confidence_label and ambiguity_reason.

    Args:
        expected: Expected ambiguity level ('ambiguous', 'clear', 'insufficient').
        payload: The payload containing answer_quality data.

    Returns:
        True if ambiguity matches expected, False if it doesn't,
        None if expected is None or no matching criteria.
    """
    if expected is None:
        return None
    answer_quality = payload.get("answer_quality") or {}
    label = str(answer_quality.get("confidence_label") or "").lower()
    reason = str(answer_quality.get("ambiguity_reason") or "").lower()
    count = int(payload.get("count") or 0)
    normalized = expected.lower()
    checks = {
        "ambiguous": lambda: label == "ambiguous" or bool(reason),
        "clear": lambda: label in {"high", "medium"} and not reason,
        "insufficient": lambda: label == "low" or count == 0 or reason == "no_results",
    }
    check = checks.get(normalized)
    return check() if check else None


def _ratio(numerator: int, denominator: int) -> float | None:
    """Calculate the ratio of numerator to denominator.

    Args:
        numerator: The numerator value.
        denominator: The denominator value (must be > 0).

    Returns:
        The ratio as a float (0.0-1.0), or None if denominator is <= 0.
    """
    if denominator <= 0:
        return None
    return numerator / denominator


def _average_metric(results: list[dict[str, Any]], metric: str) -> dict[str, float | int]:
    """Calculate average of a metric across a list of result dicts.

    Args:
        results: List of result dicts containing the metric.
        metric: The key name of the metric to average.

    Returns:
        Dict with 'scorable' (count of valid values) and 'average' (mean value, rounded to 12 decimals).
        Returns {'scorable': 0, 'average': 0.0} if no valid values found.
    """
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
