# mypy: disable-error-code=name-defined
"""Split QA evaluation scoring helpers (qa_eval_scoring_behavior_metrics)."""

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


def _observed_behavior_ids(payload: dict[str, Any]) -> list[str]:
    observed: list[str] = []
    for candidate in payload.get("candidates", []) or []:
        if not isinstance(candidate, dict):
            continue
        message_findings = candidate.get("message_findings")
        if not isinstance(message_findings, dict):
            continue
        authored_text = message_findings.get("authored_text")
        if isinstance(authored_text, dict):
            for behavior in authored_text.get("behavior_candidates", []) or []:
                if not isinstance(behavior, dict):
                    continue
                behavior_id = str(behavior.get("behavior_id") or "")
                if behavior_id and behavior_id not in observed:
                    observed.append(behavior_id)
        for block in message_findings.get("quoted_blocks", []) or []:
            if not isinstance(block, dict):
                continue
            analysis = block.get("analysis")
            if not isinstance(analysis, dict):
                continue
            for behavior in analysis.get("behavior_candidates", []) or []:
                if not isinstance(behavior, dict):
                    continue
                behavior_id = str(behavior.get("behavior_id") or "")
                if behavior_id and behavior_id not in observed:
                    observed.append(behavior_id)
    return observed


def _behavior_tag_coverage(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    if not case.expected_behavior_ids:
        return None
    observed = _observed_behavior_ids(payload)
    matched = [behavior_id for behavior_id in case.expected_behavior_ids if behavior_id in observed]
    return _ratio(len(matched), len(case.expected_behavior_ids))


def _behavior_tag_precision(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    if not case.expected_behavior_ids:
        return None
    observed = _observed_behavior_ids(payload)
    if not observed:
        return 0.0
    matched = [behavior_id for behavior_id in observed if behavior_id in case.expected_behavior_ids]
    return _ratio(len(matched), len(observed))


def _observed_counter_indicator_texts(payload: dict[str, Any]) -> list[str]:
    observed: list[str] = []

    def _append(value: str) -> None:
        normalized = _normalize_eval_text(value)
        if normalized and normalized not in observed:
            observed.append(normalized)

    for candidate in payload.get("candidates", []) or []:
        if not isinstance(candidate, dict):
            continue
        message_findings = candidate.get("message_findings")
        if not isinstance(message_findings, dict):
            continue
        authored_text = message_findings.get("authored_text")
        if isinstance(authored_text, dict):
            for item in authored_text.get("counter_indicators", []) or []:
                _append(str(item))
        for block in message_findings.get("quoted_blocks", []) or []:
            if not isinstance(block, dict):
                continue
            analysis = block.get("analysis")
            if not isinstance(analysis, dict):
                continue
            for item in analysis.get("counter_indicators", []) or []:
                _append(str(item))

    finding_index = payload.get("finding_evidence_index")
    if isinstance(finding_index, dict):
        for finding in finding_index.get("findings", []) or []:
            if not isinstance(finding, dict):
                continue
            for item in finding.get("counter_indicators", []) or []:
                _append(str(item))
            for item in finding.get("alternative_explanations", []) or []:
                _append(str(item))

    report = payload.get("investigation_report")
    if isinstance(report, dict):
        sections = report.get("sections")
        if isinstance(sections, dict):
            overall = sections.get("overall_assessment")
            if isinstance(overall, dict):
                for entry in overall.get("entries", []) or []:
                    if not isinstance(entry, dict):
                        continue
                    for item in entry.get("alternative_explanations", []) or []:
                        _append(str(item))
                    for item in entry.get("ambiguity_disclosures", []) or []:
                        _append(str(item))
            missing = sections.get("missing_information")
            if isinstance(missing, dict):
                for entry in missing.get("entries", []) or []:
                    if isinstance(entry, dict):
                        _append(str(entry.get("statement") or ""))
    return observed


def _counter_indicator_quality(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    if not case.expected_counter_indicator_markers:
        return None
    observed = _observed_counter_indicator_texts(payload)
    matched = 0
    for marker in case.expected_counter_indicator_markers:
        normalized_marker = _normalize_eval_text(marker)
        if any(normalized_marker in item for item in observed):
            matched += 1
    return _ratio(matched, len(case.expected_counter_indicator_markers))


def _claim_level_rank(level: str | None) -> int:
    return {
        "insufficient_evidence": 1,
        "pattern_concern": 2,
        "observed_fact": 3,
        "stronger_interpretation": 4,
    }.get(str(level or ""), 0)


def _report_claim_levels(payload: dict[str, Any]) -> list[str]:
    report = payload.get("investigation_report")
    if not isinstance(report, dict):
        return []
    sections = report.get("sections")
    if not isinstance(sections, dict):
        return []
    levels: list[str] = []
    for section in sections.values():
        if not isinstance(section, dict):
            continue
        for entry in section.get("entries", []) or []:
            if not isinstance(entry, dict):
                continue
            level = str(entry.get("claim_level") or "")
            if level:
                levels.append(level)
    return levels


def _overclaim_guard_match(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if not case.expected_max_claim_level:
        return None
    observed_levels = _report_claim_levels(payload)
    if not observed_levels:
        return False
    max_observed = max(_claim_level_rank(level) for level in observed_levels)
    return max_observed <= _claim_level_rank(case.expected_max_claim_level)


def _report_completeness(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    if not case.expected_report_sections:
        return None
    report = payload.get("investigation_report")
    if not isinstance(report, dict):
        return False
    sections = report.get("sections")
    if not isinstance(sections, dict):
        return False
    for section_id in case.expected_report_sections:
        section = sections.get(section_id)
        if not isinstance(section, dict):
            return False
        if str(section.get("status") or "") != "supported":
            return False
    return True


__all__ = [
    "_ANSWER_STOPWORDS",
    "_ANSWER_TERM_RE",
    "_behavior_tag_coverage",
    "_behavior_tag_precision",
    "_claim_level_rank",
    "_counter_indicator_quality",
    "_observed_behavior_ids",
    "_observed_counter_indicator_texts",
    "_overclaim_guard_match",
    "_report_claim_levels",
    "_report_completeness",
]
