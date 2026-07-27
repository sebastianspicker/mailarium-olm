"""Generic QA evaluation scoring primitives."""

from __future__ import annotations

import re
from typing import Any

from .qa_eval_cases import QuestionCase

_ANSWER_TERM_RE = re.compile(r"[0-9a-zA-ZäöüÄÖÜß._-]+")
_ANSWER_STOPWORDS = {
    "after",
    "also",
    "and",
    "because",
    "from",
    "have",
    "into",
    "message",
    "that",
    "their",
    "there",
    "these",
    "this",
    "under",
    "with",
    "without",
}


def _normalize_eval_text(value: str) -> str:
    return " ".join((value or "").casefold().split())


def _append_unique(values: list[str], value: Any) -> None:
    compact = str(value or "").strip()
    if compact and compact not in values:
        values.append(compact)


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
    return bool(answer_text) and all(term in answer_text for term in expected_terms)


def _candidate_items(payload: dict[str, Any]):
    """Yield mapping-shaped body and attachment candidates in payload order."""
    for key in ("candidates", "attachment_candidates"):
        for item in payload.get(key, []) or []:
            if isinstance(item, dict):
                yield item


def _observed_support_source_ids(payload: dict[str, Any]) -> list[str]:
    observed: list[str] = []
    for item in _candidate_items(payload):
        _append_unique(observed, item.get("source_id"))
        uid = str(item.get("uid") or "").strip()
        if uid and not str(item.get("source_id") or "").strip():
            _append_unique(observed, f"email:{uid}")
        for container_name in ("provenance", "document_locator"):
            container = item.get(container_name)
            if isinstance(container, dict):
                _append_unique(observed, container.get("evidence_handle"))
    return observed


def _support_source_id_hit(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if not case.expected_support_source_ids:
        return None
    observed = set(_observed_support_source_ids(payload))
    return any(source_id in observed for source_id in case.expected_support_source_ids)


def _support_source_id_recall(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    if not case.expected_support_source_ids:
        return None
    observed = set(_observed_support_source_ids(payload))
    matched = sum(source_id in observed for source_id in case.expected_support_source_ids)
    return _ratio(matched, len(case.expected_support_source_ids))


def _candidate_uids(payload: dict[str, Any]) -> list[str]:
    uids: list[str] = []
    for item in _candidate_items(payload):
        _append_unique(uids, item.get("uid"))
    return uids


def _uids_for_key(payload: dict[str, Any], key: str) -> list[str]:
    uids: list[str] = []
    for item in payload.get(key, []) or []:
        if isinstance(item, dict):
            _append_unique(uids, item.get("uid"))
    return uids


def _forbidden_support_ids_excluded(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if not case.forbidden_support_uids and not case.forbidden_support_source_ids:
        return None
    observed_uids = set(_candidate_uids(payload))
    observed_source_ids = set(_observed_support_source_ids(payload))
    return observed_uids.isdisjoint(case.forbidden_support_uids) and observed_source_ids.isdisjoint(
        case.forbidden_support_source_ids
    )


def _observed_quoted_speaker_emails(payload: dict[str, Any]) -> list[str]:
    observed: list[str] = []
    for item in _candidate_items(payload):
        attribution = item.get("speaker_attribution")
        if not isinstance(attribution, dict):
            continue
        for block in attribution.get("quoted_blocks", []) or []:
            if isinstance(block, dict):
                _append_unique(observed, str(block.get("speaker_email") or "").casefold())
    return observed


def _strong_attachment_support_uid_hit(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if case.bucket != "attachment_lookup" or not case.expected_support_uids:
        return None
    for item in payload.get("attachment_candidates", []) or []:
        if not isinstance(item, dict) or str(item.get("uid") or "") not in case.expected_support_uids:
            continue
        attachment = item.get("attachment")
        if isinstance(attachment, dict) and attachment.get("evidence_strength") == "strong_text":
            return True
    return False


def _strong_attachment_ocr_support_uid_hit(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if case.bucket != "attachment_lookup" or not case.expected_support_uids or "attachment_ocr" not in case.triage_tags:
        return None
    return any(
        _is_strong_ocr_attachment(item, case.expected_support_uids)
        for item in payload.get("attachment_candidates", []) or []
        if isinstance(item, dict)
    )


def _is_strong_ocr_attachment(item: dict[str, Any], expected_uids: list[str]) -> bool:
    attachment = item.get("attachment")
    return (
        str(item.get("uid") or "") in expected_uids
        and isinstance(attachment, dict)
        and attachment.get("evidence_strength") == "strong_text"
        and bool(attachment.get("ocr_used"))
        and str(attachment.get("extraction_state") or "").casefold() == "ocr_text_extracted"
    )


def _weak_evidence_explained(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if (case.expected_ambiguity or "").casefold() != "insufficient":
        return None
    weak_reason_markers = {
        "attachment_only",
        "image_only",
        "metadata_only_reply",
        "source_shell_only",
        "true_blank",
        "weak_scan_body",
    }
    quality = payload.get("answer_quality")
    if isinstance(quality, dict) and str(quality.get("ambiguity_reason") or "") in weak_reason_markers:
        return True
    for key in ("candidates", "attachment_candidates"):
        for item in payload.get(key, []) or []:
            weak_message = item.get("weak_message") if isinstance(item, dict) else None
            if isinstance(weak_message, dict) and weak_message.get("code") in weak_reason_markers:
                return True
    return False


def _resolve_top_uid(payload: dict[str, Any]) -> str | None:
    quality = payload.get("answer_quality")
    if isinstance(quality, dict) and quality.get("top_candidate_uid"):
        return str(quality["top_candidate_uid"])
    for key in ("candidates", "attachment_candidates"):
        items = payload.get(key) or []
        if items and isinstance(items[0], dict) and items[0].get("uid"):
            return str(items[0]["uid"])
    return None


def _long_thread_answer_present(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if "long_thread" not in case.triage_tags:
        return None
    final_answer = payload.get("final_answer")
    return isinstance(final_answer, dict) and bool(str(final_answer.get("text") or "").strip())


def _long_thread_structure_preserved(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if "long_thread" not in case.triage_tags:
        return None
    timeline = payload.get("timeline")
    events = timeline.get("events") if isinstance(timeline, dict) else None
    return bool(payload.get("conversation_groups")) and bool(events)


def _ambiguity_matches(expected: str | None, payload: dict[str, Any]) -> bool | None:
    if expected is None:
        return None
    quality = payload.get("answer_quality")
    quality = quality if isinstance(quality, dict) else {}
    label = str(quality.get("confidence_label") or "").casefold()
    reason = str(quality.get("ambiguity_reason") or "").casefold()
    count = int(payload.get("count") or 0)
    checks = {
        "ambiguous": label == "ambiguous" or bool(reason),
        "clear": label in {"high", "medium"} and not reason,
        "insufficient": label == "low" or count == 0 or reason == "no_results",
    }
    return checks.get(expected.casefold())


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator > 0 else None


def _average_metric(results: list[dict[str, Any]], metric: str) -> dict[str, float | int]:
    values = [float(result[metric]) for result in results if result.get(metric) is not None]
    if not values:
        return {"scorable": 0, "average": 0.0}
    return {"scorable": len(values), "average": round(sum(values) / len(values), 12)}


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
]
