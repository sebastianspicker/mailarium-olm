# mypy: disable-error-code=name-defined
# pylint: disable=E0602  # cross-module names injected by compatibility facade
"""Split QA evaluation scoring helpers (qa_eval_scoring_slice_a)."""

from __future__ import annotations

import re
from typing import Any

from ._utils import _as_dict, _as_list
from .qa_eval_cases import QuestionCase
from .qa_eval_scoring_core import _append_unique, _ratio

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


def _slice_a_config(case: QuestionCase) -> dict[str, Any]:
    """Extract slice A configuration from a question case."""
    return _as_dict(_as_dict(case.benchmark_pack).get("slice_a"))


def _source_id_from_candidate(item: dict[str, Any]) -> str:
    """Extract a source ID from a candidate item, trying multiple possible fields."""
    source_id = str(item.get("source_id") or "").strip()
    if source_id:
        return source_id
    provenance = _as_dict(item.get("provenance"))
    source_id = str(provenance.get("evidence_handle") or "").strip()
    if source_id:
        return source_id
    locator = _as_dict(item.get("document_locator"))
    source_id = str(locator.get("evidence_handle") or "").strip()
    if source_id:
        return source_id
    uid = str(item.get("uid") or "").strip()
    if uid:
        return f"email:{uid}"
    return ""


def _quote_match_class_from_candidate(item: dict[str, Any]) -> str:
    """Extract the quote match class from a candidate item, trying multiple possible fields."""
    for key in ("quote_match_class", "quote_match", "match_class", "verification_state"):
        value = str(item.get(key) or "").strip().casefold()
        if value:
            return value
    verification = _as_dict(item.get("verification"))
    for key in ("quote_match_class", "quote_match", "match_class", "verification_state"):
        value = str(verification.get(key) or "").strip().casefold()
        if value:
            return value
    return ""


def _quote_support_source_ids(payload: dict[str, Any], *, classes: set[str]) -> list[str]:
    """Extract source IDs from payload that support the given quote match classes."""
    observed: list[str] = []
    metrics = _as_dict(payload.get("quote_attribution_metrics"))
    if "exact" in classes:
        for value in _as_list(metrics.get("exact_support_source_ids")):
            _append_unique(observed, value)
    if "near_exact" in classes:
        for value in _as_list(metrics.get("near_exact_support_source_ids")):
            _append_unique(observed, value)

    exact_aliases = {"exact", "exact_verified", "verbatim_exact"}
    near_aliases = {"near_exact", "normalized_exact", "weak_exact", "fuzzy"}
    accepted_aliases: set[str] = set()
    if "exact" in classes:
        accepted_aliases.update(exact_aliases)
    if "near_exact" in classes:
        accepted_aliases.update(near_aliases)

    for key in ("candidates", "attachment_candidates"):
        for item in _as_list(payload.get(key)):
            if not isinstance(item, dict):
                continue
            match_class = _quote_match_class_from_candidate(item)
            if match_class not in accepted_aliases:
                continue
            _append_unique(observed, _source_id_from_candidate(item))
    return observed


def _locator_has_reversible_fields(locator: dict[str, Any]) -> bool:
    """Check if a locator has any reversible fields that can be used to re-find the source."""
    if not locator:
        return False
    reversible_keys = {
        "attachment_id",
        "surface_id",
        "page",
        "page_number",
        "sheet",
        "sheet_name",
        "cell_range",
        "member_path",
        "message_id",
        "line_span",
        "char_span",
        "line_box",
    }
    return any(key in locator and locator.get(key) not in (None, "", [], {}) for key in reversible_keys)


def _slice_a_exact_verified_quote_rate(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    """Calculate the exact verified quote rate for slice A scoring."""
    config = _slice_a_config(case)
    expected = [str(value).strip() for value in _as_list(config.get("exact_support_source_ids")) if str(value).strip()]
    if not expected:
        return None
    observed = _quote_support_source_ids(payload, classes={"exact"})
    matched = [source_id for source_id in expected if source_id in observed]
    return _ratio(len(matched), len(expected))


def _slice_a_near_exact_quote_rate(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    """Calculate the near-exact quote rate for slice A scoring."""
    config = _slice_a_config(case)
    expected = [str(value).strip() for value in _as_list(config.get("near_exact_support_source_ids")) if str(value).strip()]
    if not expected:
        return None
    observed = _quote_support_source_ids(payload, classes={"near_exact", "exact"})
    matched = [source_id for source_id in expected if source_id in observed]
    return _ratio(len(matched), len(expected))


def _slice_a_false_exact_flag(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    """Check if any forbidden exact source IDs are present in the payload."""
    config = _slice_a_config(case)
    forbidden = [str(value).strip() for value in _as_list(config.get("forbidden_exact_source_ids")) if str(value).strip()]
    if not forbidden:
        return None
    observed = set(_quote_support_source_ids(payload, classes={"exact"}))
    return 1.0 if any(source_id in observed for source_id in forbidden) else 0.0


def _slice_a_locator_completeness(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    """Calculate the locator completeness score for slice A."""
    config = _slice_a_config(case)
    if not bool(config.get("require_locator_coverage")):
        return None
    candidate_rows = [
        item for key in ("candidates", "attachment_candidates") for item in _as_list(payload.get(key)) if isinstance(item, dict)
    ]
    if not candidate_rows:
        return 0.0
    located = 0
    for row in candidate_rows:
        locator = _as_dict(row.get("document_locator"))
        if not locator:
            locator = _as_dict(_as_dict(row.get("provenance")).get("locator"))
        if _locator_has_reversible_fields(locator):
            located += 1
    return _ratio(located, len(candidate_rows))


def _slice_a_authored_german_primary_match(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    """Check if the authored language matches the expected German primary language."""
    config = _slice_a_config(case)
    expected_authored = str(config.get("expected_authored_language") or "").strip().casefold()
    if not expected_authored:
        return None

    analytics = _as_dict(payload.get("language_analytics"))
    observed_authored = _observed_dominant_language(analytics, "authored")
    if not observed_authored:
        return False

    expected_quoted = str(config.get("expected_quoted_language") or "").strip().casefold()
    if expected_quoted:
        observed_quoted = _observed_dominant_language(analytics, "quoted")
        if observed_quoted != expected_quoted:
            return False
    return observed_authored == expected_authored


def _observed_dominant_language(analytics: dict[str, Any], surface: str) -> str:
    rollup = _as_dict(analytics.get("surface_rollup"))
    dominant = _as_dict(analytics.get("dominant_languages"))
    candidates = (
        analytics.get(f"{surface}_dominant_language"),
        rollup.get(f"{surface}_dominant_language"),
        dominant.get(surface),
    )
    return next((str(value).strip().casefold() for value in candidates if str(value or "").strip()), "")


def _slice_a_contradiction_pair_precision(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    """Calculate the precision of contradiction pairs for slice A scoring."""
    config = _slice_a_config(case)
    required_pairs = int(config.get("required_contradiction_pairs") or 0)
    if required_pairs <= 0:
        return None

    pairs = _contradiction_pairs(payload)
    if not pairs:
        return 0.0

    def _pair_source(pair: dict[str, Any], *, side: str) -> str:
        block = _as_dict(pair.get(side))
        for key in ("source_id", "evidence_handle"):
            value = str(block.get(key) or "").strip()
            if value:
                return value
        return str(pair.get(f"{side}_source_id") or pair.get(f"{side}_evidence_handle") or "").strip()

    def _pair_locator(pair: dict[str, Any], *, side: str) -> dict[str, Any]:
        block = _as_dict(pair.get(side))
        locator = _as_dict(block.get("locator"))
        if locator:
            return locator
        return _as_dict(pair.get(f"{side}_locator"))

    valid_pairs = sum(_valid_contradiction_pair(pair, _pair_source, _pair_locator) for pair in pairs)
    return _ratio(valid_pairs, len(pairs))


def _contradiction_pairs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    findings = _as_list(_as_dict(payload.get("finding_evidence_index")).get("findings"))
    return [
        pair
        for finding in findings
        if isinstance(finding, dict)
        for pair in _as_list(finding.get("contradiction_pairs"))
        if isinstance(pair, dict)
    ]


def _valid_contradiction_pair(pair, source_fn, locator_fn) -> bool:
    left_source = source_fn(pair, side="left")
    right_source = source_fn(pair, side="right")
    return (
        bool(left_source)
        and bool(right_source)
        and left_source != right_source
        and _locator_has_reversible_fields(locator_fn(pair, side="left"))
        and _locator_has_reversible_fields(locator_fn(pair, side="right"))
    )


def _slice_a_ocr_heavy_attachment_recall(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    """Check if OCR was used on heavy attachments for slice A scoring."""
    config = _slice_a_config(case)
    if not bool(config.get("require_ocr_attachment_recall")):
        return None
    if not case.expected_support_uids:
        return False
    for item in _as_list(payload.get("attachment_candidates")):
        if not isinstance(item, dict):
            continue
        uid = str(item.get("uid") or "")
        if uid not in case.expected_support_uids:
            continue
        attachment = _as_dict(item.get("attachment"))
        if (
            bool(attachment.get("ocr_used"))
            and str(attachment.get("evidence_strength") or "") == "strong_text"
            and str(attachment.get("extraction_state") or "").strip().lower() == "ocr_text_extracted"
        ):
            return True
    return False


def _slice_a_mixed_source_completeness(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    """Calculate the mixed source completeness score for slice A."""
    config = _slice_a_config(case)
    required_source_types = {str(value).strip() for value in _as_list(config.get("required_source_types")) if str(value).strip()}
    if not required_source_types:
        return None
    sources = _as_list(_as_dict(payload.get("multi_source_case_bundle")).get("sources"))
    observed = {str(_as_dict(source).get("source_type") or "").strip() for source in sources if isinstance(source, dict)}
    matched = len(required_source_types.intersection(observed))
    return _ratio(matched, len(required_source_types))


def _slice_a_calendar_exclusion_visible(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    """Check if calendar evidence is visible in the payload for slice A."""
    config = _slice_a_config(case)
    if not bool(config.get("require_calendar_evidence")):
        return None
    sources = _as_list(_as_dict(payload.get("multi_source_case_bundle")).get("sources"))
    source_types = {
        str(_as_dict(source).get("source_type") or "").strip().casefold() for source in sources if isinstance(source, dict)
    }
    return bool(source_types.intersection({"calendar", "calendar_event", "meeting"}))


def _slice_a_silence_omission_anchor_match(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    """Check if silence omission anchor match is present for slice A scoring."""
    config = _slice_a_config(case)
    if not bool(config.get("require_reply_expectation_anchor")):
        return None
    reply_pairing = _as_dict(payload.get("reply_pairing"))
    expected_edges = _as_list(reply_pairing.get("expected_reply_edges"))
    missing_edges = _as_list(reply_pairing.get("missing_reply_edges"))
    has_reply_expectation = any(isinstance(item, dict) for item in [*expected_edges, *missing_edges])
    timeline_events = _as_list(_as_dict(payload.get("timeline")).get("events"))
    chronology_entries = _as_list(_as_dict(payload.get("master_chronology")).get("entries"))
    has_chronology_anchor = any(isinstance(item, dict) for item in [*timeline_events, *chronology_entries])
    return has_reply_expectation and has_chronology_anchor


__all__ = [
    "_ANSWER_STOPWORDS",
    "_ANSWER_TERM_RE",
    "_locator_has_reversible_fields",
    "_quote_match_class_from_candidate",
    "_quote_support_source_ids",
    "_slice_a_authored_german_primary_match",
    "_slice_a_calendar_exclusion_visible",
    "_slice_a_config",
    "_slice_a_contradiction_pair_precision",
    "_slice_a_exact_verified_quote_rate",
    "_slice_a_false_exact_flag",
    "_slice_a_locator_completeness",
    "_slice_a_mixed_source_completeness",
    "_slice_a_near_exact_quote_rate",
    "_slice_a_ocr_heavy_attachment_recall",
    "_slice_a_silence_omission_anchor_match",
    "_source_id_from_candidate",
]
