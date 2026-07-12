# mypy: disable-error-code=name-defined
# mypy: disable-error-code=name-defined
# pylint: disable=too-many-branches,too-many-locals

# pylint: disable=E0602  # cross-module names injected by compatibility facade
"""Split QA evaluation scoring helpers (qa_eval_scoring_behavior_metrics)."""

from __future__ import annotations

from typing import Any

from .qa_eval_cases import QuestionCase
from .qa_eval_scoring_core import _normalize_eval_text, _ratio


def _observed_behavior_ids(payload: dict[str, Any]) -> list[str]:
    """Extract unique behavior IDs from a QA evaluation payload.

    Scans through candidates' message findings (both authored_text and quoted_blocks)
    to collect all behavior_id values that appear in behavior_candidates lists.

    Args:
        payload: The QA evaluation payload containing candidates with message_findings.

    Returns:
        List of unique behavior ID strings found in the payload.
    """
    ids = (str(item.get("behavior_id") or "") for item in _behavior_candidates(payload))
    return list(dict.fromkeys(behavior_id for behavior_id in ids if behavior_id))


def _behavior_candidates(payload: dict[str, Any]):
    for findings in _message_findings(payload):
        yield from _authored_behavior_candidates(findings)
        yield from _quoted_behavior_candidates(findings)


def _authored_behavior_candidates(findings: dict[str, Any]):
    authored = findings.get("authored_text")
    if isinstance(authored, dict):
        yield from (item for item in authored.get("behavior_candidates", []) or [] if isinstance(item, dict))


def _quoted_behavior_candidates(findings: dict[str, Any]):
    for block in findings.get("quoted_blocks", []) or []:
        analysis = block.get("analysis") if isinstance(block, dict) else None
        if isinstance(analysis, dict):
            yield from (item for item in analysis.get("behavior_candidates", []) or [] if isinstance(item, dict))


def _message_findings(payload: dict[str, Any]):
    for candidate in payload.get("candidates", []) or []:
        findings = candidate.get("message_findings") if isinstance(candidate, dict) else None
        if isinstance(findings, dict):
            yield findings


def _behavior_tag_coverage(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    """Calculate the coverage ratio of expected behavior tags found in the payload.

    Measures what fraction of the case's expected_behavior_ids appear in the
    observed behavior IDs from the payload.

    Args:
        case: The question case containing expected_behavior_ids.
        payload: The QA evaluation payload to check for behavior IDs.

    Returns:
        Ratio of matched expected behavior IDs to total expected (0.0-1.0),
        or None if no expected behavior IDs are defined.
    """
    if not case.expected_behavior_ids:
        return None
    observed = _observed_behavior_ids(payload)
    matched = [behavior_id for behavior_id in case.expected_behavior_ids if behavior_id in observed]
    return _ratio(len(matched), len(case.expected_behavior_ids))


def _behavior_tag_precision(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    """Calculate the precision ratio of observed behavior tags matching expected ones.

    Measures what fraction of the observed behavior IDs from the payload are
    actually in the case's expected_behavior_ids (i.e., no false positives).

    Args:
        case: The question case containing expected_behavior_ids.
        payload: The QA evaluation payload to check for behavior IDs.

    Returns:
        Ratio of observed behavior IDs that match expected to total observed (0.0-1.0),
        or None if no expected behavior IDs are defined.
        Returns 0.0 if no behavior IDs are observed.
    """
    if not case.expected_behavior_ids:
        return None
    observed = _observed_behavior_ids(payload)
    if not observed:
        return 0.0
    matched = [behavior_id for behavior_id in observed if behavior_id in case.expected_behavior_ids]
    return _ratio(len(matched), len(observed))


def _observed_counter_indicator_texts(payload: dict[str, Any]) -> list[str]:
    """Extract unique normalized counter indicator texts from a QA evaluation payload.

    Scans through candidates' message findings (authored_text and quoted_blocks),
    finding_evidence_index, and investigation_report to collect all counter_indicator
    and related text values.

    Args:
        payload: The QA evaluation payload containing counter indicators.

    Returns:
        List of unique normalized counter indicator text strings found in the payload.
    """
    normalized = (_normalize_eval_text(value) for value in _counter_indicator_values(payload))
    return list(dict.fromkeys(value for value in normalized if value))


def _counter_indicator_values(payload: dict[str, Any]):
    for findings in _message_findings(payload):
        authored = findings.get("authored_text")
        if isinstance(authored, dict):
            yield from (str(item) for item in authored.get("counter_indicators", []) or [])
        for block in findings.get("quoted_blocks", []) or []:
            analysis = block.get("analysis") if isinstance(block, dict) else None
            if isinstance(analysis, dict):
                yield from (str(item) for item in analysis.get("counter_indicators", []) or [])
    yield from _finding_counter_indicators(payload)
    yield from _report_counter_indicators(payload)


def _finding_counter_indicators(payload: dict[str, Any]):
    index = payload.get("finding_evidence_index")
    findings = index.get("findings", []) if isinstance(index, dict) else []
    for finding in findings or []:
        if isinstance(finding, dict):
            for key in ("counter_indicators", "alternative_explanations"):
                yield from (str(item) for item in finding.get(key, []) or [])


def _report_counter_indicators(payload: dict[str, Any]):
    report = payload.get("investigation_report")
    sections = report.get("sections") if isinstance(report, dict) else None
    if not isinstance(sections, dict):
        return
    yield from _overall_assessment_indicators(sections)
    yield from _missing_information_indicators(sections)


def _overall_assessment_indicators(sections: dict[str, Any]):
    overall = sections.get("overall_assessment")
    entries = overall.get("entries", []) if isinstance(overall, dict) else []
    for entry in entries or []:
        if isinstance(entry, dict):
            for key in ("alternative_explanations", "ambiguity_disclosures"):
                yield from (str(item) for item in entry.get(key, []) or [])


def _missing_information_indicators(sections: dict[str, Any]):
    missing = sections.get("missing_information")
    entries = missing.get("entries", []) if isinstance(missing, dict) else []
    for entry in entries or []:
        if isinstance(entry, dict):
            yield str(entry.get("statement") or "")


def _counter_indicator_quality(case: QuestionCase, payload: dict[str, Any]) -> float | None:
    """Calculate the quality ratio of expected counter indicator markers found in the payload.

    Measures what fraction of the case's expected_counter_indicator_markers
    appear in the observed counter indicator texts from the payload.

    Args:
        case: The question case containing expected_counter_indicator_markers.
        payload: The QA evaluation payload to check for counter indicators.

    Returns:
        Ratio of matched expected counter indicator markers to total expected (0.0-1.0),
        or None if no expected counter indicator markers are defined.
    """
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
    """Convert a claim level string to a numeric rank for comparison.

    Args:
        level: The claim level string (e.g., 'insufficient_evidence', 'pattern_concern',
               'observed_fact', 'stronger_interpretation'), or None.

    Returns:
        Numeric rank: 1=insufficient_evidence, 2=pattern_concern, 3=observed_fact,
        4=stronger_interpretation, 0 for unknown/None.
    """
    return {
        "insufficient_evidence": 1,
        "pattern_concern": 2,
        "observed_fact": 3,
        "stronger_interpretation": 4,
    }.get(str(level or ""), 0)


def _report_claim_levels(payload: dict[str, Any]) -> list[str]:
    """Extract all claim level strings from an investigation report in the payload.

    Scans through all sections and entries in the investigation_report to collect
    all claim_level values.

    Args:
        payload: The QA evaluation payload containing an investigation_report.

    Returns:
        List of claim level strings found in the report, or empty list if no
        investigation_report or sections are present.
    """
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
    """Check if the maximum observed claim level does not exceed the expected maximum.

    Compares the highest claim level found in the investigation report against
    the case's expected_max_claim_level to ensure no overclaiming.

    Args:
        case: The question case containing expected_max_claim_level.
        payload: The QA evaluation payload containing an investigation_report.

    Returns:
        True if the maximum observed claim level is <= expected maximum,
        False if it exceeds, or None if no expected_max_claim_level is defined.
    """
    if not case.expected_max_claim_level:
        return None
    observed_levels = _report_claim_levels(payload)
    if not observed_levels:
        return False
    max_observed = max(_claim_level_rank(level) for level in observed_levels)
    return max_observed <= _claim_level_rank(case.expected_max_claim_level)


def _report_completeness(case: QuestionCase, payload: dict[str, Any]) -> bool | None:
    """Check if all expected report sections are present and supported in the payload.

    Verifies that each section_id in the case's expected_report_sections exists
    in the investigation_report and has a status of 'supported'.

    Args:
        case: The question case containing expected_report_sections.
        payload: The QA evaluation payload containing an investigation_report.

    Returns:
        True if all expected sections are present and supported,
        False if any are missing or not supported,
        or None if no expected_report_sections are defined.
    """
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
