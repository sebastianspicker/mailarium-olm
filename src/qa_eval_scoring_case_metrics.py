# mypy: disable-error-code=name-defined
"""Split QA evaluation scoring helpers (qa_eval_scoring_case_metrics)."""

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

# ruff: noqa: F401,F821


def _observed_quoted_speaker_emails(payload: dict[str, Any]) -> list[str]:
    observed: list[str] = []
    for key in ("candidates", "attachment_candidates"):
        for item in payload.get(key, []):
            attribution = item.get("speaker_attribution")
            if not isinstance(attribution, dict):
                continue
            for block in attribution.get("quoted_blocks", []):
                if not isinstance(block, dict):
                    continue
                speaker_email = str(block.get("speaker_email") or "").strip().lower()
                if speaker_email and speaker_email not in observed:
                    observed.append(speaker_email)
    return observed


def _case_bundle_present(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if case.case_scope is None:
        return None
    return isinstance(payload.get("case_bundle"), dict)


def _investigation_blocks_present(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if case.case_scope is None:
        return None
    required_blocks = (
        "case_bundle",
        "actor_identity_graph",
        "case_patterns",
        "finding_evidence_index",
        "evidence_table",
        "quote_attribution_metrics",
    )
    return all(isinstance(payload.get(key), dict) for key in required_blocks)


def _case_bundle_support_uid_hit(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if case.case_scope is None or not case.expected_case_bundle_uids:
        return None
    observed_uids = _bundle_support_uids(payload)
    return any(uid in observed_uids for uid in case.expected_case_bundle_uids)


def _case_bundle_support_uid_recall(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    if case.case_scope is None or not case.expected_case_bundle_uids:
        return None
    observed_uids = _bundle_support_uids(payload)
    matched = [uid for uid in case.expected_case_bundle_uids if uid in observed_uids]
    return _ratio(len(matched), len(case.expected_case_bundle_uids))


def _case_bundle_support_source_id_hit(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if case.case_scope is None or not case.expected_case_bundle_source_ids:
        return None
    observed = _bundle_support_source_ids(payload)
    return any(source_id in observed for source_id in case.expected_case_bundle_source_ids)


def _case_bundle_support_source_id_recall(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    if case.case_scope is None or not case.expected_case_bundle_source_ids:
        return None
    observed = _bundle_support_source_ids(payload)
    matched = [source_id for source_id in case.expected_case_bundle_source_ids if source_id in observed]
    return _ratio(len(matched), len(case.expected_case_bundle_source_ids))


def _multi_source_source_types_match(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if case.case_scope is None or not case.expected_source_types:
        return None
    multi_source_case_bundle = payload.get("multi_source_case_bundle")
    if not isinstance(multi_source_case_bundle, dict):
        return False
    observed = {
        str(source.get("source_type") or "")
        for source in multi_source_case_bundle.get("sources", []) or []
        if isinstance(source, dict)
    }
    return set(case.expected_source_types).issubset(observed)


def _timeline_uids(payload: dict[str, Any]) -> list[str]:
    observed: list[str] = []
    timeline = payload.get("timeline")
    if not isinstance(timeline, dict):
        return observed
    for event in timeline.get("events", []) or []:
        if not isinstance(event, dict):
            continue
        uid = str(event.get("uid") or "")
        if uid and uid not in observed:
            observed.append(uid)
    return observed


def _chronology_uid_hit(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if not case.expected_timeline_uids:
        return None
    observed = _timeline_uids(payload)
    return any(uid in observed for uid in case.expected_timeline_uids)


def _chronology_uid_recall(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    if not case.expected_timeline_uids:
        return None
    observed = _timeline_uids(payload)
    matched = [uid for uid in case.expected_timeline_uids if uid in observed]
    return _ratio(len(matched), len(case.expected_timeline_uids))


def _chronology_source_ids(payload: dict[str, Any]) -> list[str]:
    observed: list[str] = []
    chronology = payload.get("master_chronology")
    if not isinstance(chronology, dict):
        return observed
    for entry in chronology.get("entries", []) or []:
        if not isinstance(entry, dict):
            continue
        source_linkage = entry.get("source_linkage")
        if not isinstance(source_linkage, dict):
            continue
        for key in ("source_ids", "evidence_handles"):
            for value in source_linkage.get(key, []) or []:
                _append_unique(observed, value)
    return observed


def _chronology_source_id_hit(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if not case.expected_timeline_source_ids:
        return None
    observed = _chronology_source_ids(payload)
    return any(source_id in observed for source_id in case.expected_timeline_source_ids)


def _chronology_source_id_recall(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    if not case.expected_timeline_source_ids:
        return None
    observed = _chronology_source_ids(payload)
    matched = [source_id for source_id in case.expected_timeline_source_ids if source_id in observed]
    return _ratio(len(matched), len(case.expected_timeline_source_ids))


__all__ = [
    "_ANSWER_STOPWORDS",
    "_ANSWER_TERM_RE",
    "_case_bundle_present",
    "_case_bundle_support_source_id_hit",
    "_case_bundle_support_source_id_recall",
    "_case_bundle_support_uid_hit",
    "_case_bundle_support_uid_recall",
    "_chronology_source_id_hit",
    "_chronology_source_id_recall",
    "_chronology_source_ids",
    "_chronology_uid_hit",
    "_chronology_uid_recall",
    "_investigation_blocks_present",
    "_multi_source_source_types_match",
    "_observed_quoted_speaker_emails",
    "_timeline_uids",
]
