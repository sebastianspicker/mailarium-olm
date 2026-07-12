"""Message-appendix helpers for case-analysis payloads."""

from __future__ import annotations

from typing import Any


def citations_by_uid(finding_evidence_index: dict[str, Any]) -> dict[str, list[str]]:
    """Return citation ids grouped by supporting message uid."""
    by_uid: dict[str, list[str]] = {}
    for finding in finding_evidence_index.get("findings", []) if isinstance(finding_evidence_index, dict) else []:
        if not isinstance(finding, dict):
            continue
        for citation in finding.get("supporting_evidence", []):
            if not isinstance(citation, dict):
                continue
            uid = str(citation.get("message_or_document_id") or "")
            citation_id = str(citation.get("citation_id") or "")
            if not uid or not citation_id:
                continue
            by_uid.setdefault(uid, [])
            if citation_id not in by_uid[uid]:
                by_uid[uid].append(citation_id)
    return by_uid


def message_findings_by_uid(finding_evidence_index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return finding-derived message metadata grouped by supporting uid."""
    by_uid: dict[str, dict[str, Any]] = {}
    for finding in finding_evidence_index.get("findings", []) if isinstance(finding_evidence_index, dict) else []:
        if not isinstance(finding, dict):
            continue
        metadata = _finding_metadata(finding)
        for citation in finding.get("supporting_evidence", []):
            if not isinstance(citation, dict):
                continue
            uid = str(citation.get("message_or_document_id") or "")
            if not uid:
                continue
            _merge_finding_metadata(by_uid.setdefault(uid, _empty_finding_summary()), metadata)
    return by_uid


def _empty_finding_summary() -> dict[str, list[str]]:
    return {
        "finding_ids": [],
        "finding_labels": [],
        "evidence_strength_labels": [],
        "alternative_explanations": [],
        "counter_indicators": [],
    }


def _finding_metadata(finding: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "finding_ids": _nonempty_values([finding.get("finding_id")]),
        "finding_labels": _nonempty_values([finding.get("finding_label")]),
        "evidence_strength_labels": _nonempty_values([(finding.get("evidence_strength") or {}).get("label")]),
        "alternative_explanations": _nonempty_values(finding.get("alternative_explanations", [])),
        "counter_indicators": _nonempty_values(finding.get("counter_indicators", [])),
    }


def _nonempty_values(values: Any) -> list[str]:
    return [str(value) for value in values if str(value).strip()]


def _merge_finding_metadata(bucket: dict[str, Any], metadata: dict[str, list[str]]) -> None:
    for key, values in metadata.items():
        bucket[key].extend(value for value in values if value not in bucket[key])


def strength_rank(label: str) -> int:
    """Rank message-level evidence strength labels."""
    return {
        "strong_indicator": 4,
        "moderate_indicator": 3,
        "weak_indicator": 2,
        "insufficient_evidence": 1,
    }.get(label, 0)


def message_row_strength(
    *,
    language_signal_count: int,
    behavior_candidate_count: int,
    finding_strengths: list[str],
) -> str:
    """Return the strongest available per-message evidence-strength label."""
    if finding_strengths:
        return max(finding_strengths, key=strength_rank)
    if behavior_candidate_count or language_signal_count:
        return "moderate_indicator"
    return "insufficient_evidence"


def build_message_appendix(payload: dict[str, Any], *, include_message_appendix: bool) -> dict[str, Any]:
    """Return a message-level appendix derived from case candidates."""
    if not include_message_appendix:
        return {
            "included": False,
            "omission_reason": "operator_disabled_message_appendix",
            "row_count": 0,
            "rows": [],
        }

    finding_evidence_index = payload.get("finding_evidence_index")
    citations = citations_by_uid(finding_evidence_index if isinstance(finding_evidence_index, dict) else {})
    findings = message_findings_by_uid(finding_evidence_index if isinstance(finding_evidence_index, dict) else {})
    rows: list[dict[str, Any]] = []
    for candidate in payload.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        uid = str(candidate.get("uid") or "")
        rows.append(_message_appendix_row(candidate, findings.get(uid, _empty_finding_summary()), citations.get(uid, [])))
    rows.sort(key=lambda row: (str(row.get("date") or ""), str(row.get("uid") or "")))
    return {
        "included": True,
        "review_table_version": "2",
        "row_count": len(rows),
        "rows": rows,
    }


def _message_appendix_row(candidate: dict[str, Any], finding_summary: dict[str, Any], citation_ids: list[str]) -> dict[str, Any]:
    language = (candidate.get("language_rhetoric") or {}).get("authored_text") or {}
    message_findings = (candidate.get("message_findings") or {}).get("authored_text") or {}
    behaviors = [
        _project_fields(item, ("behavior_id", "label", "confidence"))
        for item in message_findings.get("behavior_candidates", [])
        if isinstance(item, dict)
    ]
    counter_indicators = _nonempty_values(message_findings.get("counter_indicators", []))
    _merge_unique(counter_indicators, finding_summary["counter_indicators"])
    return {
        **_message_identity(candidate),
        **_message_finding_fields(finding_summary, citation_ids),
        **_message_analysis_fields(language, message_findings, behaviors),
        "communication_classification": _communication_classification(message_findings),
        "evidence_strength": message_row_strength(
            language_signal_count=int(language.get("signal_count") or 0),
            behavior_candidate_count=len(behaviors),
            finding_strengths=list(finding_summary["evidence_strength_labels"]),
        ),
        "counter_indicators": counter_indicators,
    }


def _message_finding_fields(summary: dict[str, Any], citation_ids: list[str]) -> dict[str, Any]:
    return {
        "finding_ids": list(summary["finding_ids"]),
        "finding_labels": list(summary["finding_labels"]),
        "alternative_explanations": list(summary["alternative_explanations"]),
        "supporting_citation_ids": citation_ids,
    }


def _message_analysis_fields(
    language: dict[str, Any], findings: dict[str, Any], behaviors: list[dict[str, str]]
) -> dict[str, Any]:
    return {
        "language_signals": [
            _project_fields(item, ("signal_id", "label", "confidence"))
            for item in language.get("signals", [])
            if isinstance(item, dict)
        ],
        "behavior_candidates": behaviors,
        "tone_summary": str(findings.get("tone_summary") or ""),
        "relevant_wording": [
            _project_fields(item, ("text", "source_scope", "basis_id"))
            for item in findings.get("relevant_wording", [])
            if isinstance(item, dict)
        ],
        "omissions_or_process_signals": [
            _project_fields(item, ("signal", "summary"))
            for item in findings.get("omissions_or_process_signals", [])
            if isinstance(item, dict)
        ],
        "included_actors": _nonempty_values(findings.get("included_actors", [])),
        "excluded_actors": _nonempty_values(findings.get("excluded_actors", [])),
    }


def _project_fields(item: dict[str, Any], fields: tuple[str, ...]) -> dict[str, str]:
    return {field: str(item.get(field) or "") for field in fields}


def _merge_unique(target: list[str], additions: list[str]) -> None:
    target.extend(item for item in additions if item not in target)


def _message_identity(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "uid": str(candidate.get("uid") or ""),
        "date": str(candidate.get("date") or ""),
        "sender": {"name": str(candidate.get("sender_name") or ""), "email": str(candidate.get("sender_email") or "")},
        "recipients_summary": candidate.get("recipients_summary") or {"status": "not_available_in_case_payload"},
        "subject": str(candidate.get("subject") or ""),
        "message_level_summary": str(candidate.get("snippet") or ""),
    }


def _communication_classification(findings: dict[str, Any]) -> dict[str, Any]:
    classification = dict(findings.get("communication_classification") or {})
    return {
        "primary_class": str(classification.get("primary_class") or "neutral"),
        "applied_classes": _nonempty_values(classification.get("applied_classes", [])) or ["neutral"],
        "confidence": str(classification.get("confidence") or "low"),
        "rationale": str(classification.get("rationale") or ""),
    }
