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
        finding_id = str(finding.get("finding_id") or "")
        finding_label = str(finding.get("finding_label") or "")
        evidence_strength = str((finding.get("evidence_strength") or {}).get("label") or "")
        alternative_explanations = [str(item) for item in finding.get("alternative_explanations", []) if str(item).strip()]
        counter_indicators = [str(item) for item in finding.get("counter_indicators", []) if str(item).strip()]
        for citation in finding.get("supporting_evidence", []):
            if not isinstance(citation, dict):
                continue
            uid = str(citation.get("message_or_document_id") or "")
            if not uid:
                continue
            bucket = by_uid.setdefault(
                uid,
                {
                    "finding_ids": [],
                    "finding_labels": [],
                    "evidence_strength_labels": [],
                    "alternative_explanations": [],
                    "counter_indicators": [],
                },
            )
            if finding_id and finding_id not in bucket["finding_ids"]:
                bucket["finding_ids"].append(finding_id)
            if finding_label and finding_label not in bucket["finding_labels"]:
                bucket["finding_labels"].append(finding_label)
            if evidence_strength and evidence_strength not in bucket["evidence_strength_labels"]:
                bucket["evidence_strength_labels"].append(evidence_strength)
            for item in alternative_explanations:
                if item not in bucket["alternative_explanations"]:
                    bucket["alternative_explanations"].append(item)
            for item in counter_indicators:
                if item not in bucket["counter_indicators"]:
                    bucket["counter_indicators"].append(item)
    return by_uid


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
        language = (candidate.get("language_rhetoric") or {}).get("authored_text") or {}
        message_findings = (candidate.get("message_findings") or {}).get("authored_text") or {}
        behavior_candidates = [
            {
                "behavior_id": str(item.get("behavior_id") or ""),
                "label": str(item.get("label") or ""),
                "confidence": str(item.get("confidence") or ""),
            }
            for item in message_findings.get("behavior_candidates", [])
            if isinstance(item, dict)
        ]
        finding_summary = findings.get(
            uid,
            {
                "finding_ids": [],
                "finding_labels": [],
                "evidence_strength_labels": [],
                "alternative_explanations": [],
                "counter_indicators": [],
            },
        )
        row_counter_indicators = [str(item) for item in message_findings.get("counter_indicators", []) if str(item).strip()]
        for item in finding_summary["counter_indicators"]:
            if item not in row_counter_indicators:
                row_counter_indicators.append(item)
        communication_classification = dict(message_findings.get("communication_classification") or {})
        rows.append(
            {
                "uid": uid,
                "date": str(candidate.get("date") or ""),
                "sender": {
                    "name": str(candidate.get("sender_name") or ""),
                    "email": str(candidate.get("sender_email") or ""),
                },
                "recipients_summary": candidate.get("recipients_summary") or {"status": "not_available_in_case_payload"},
                "subject": str(candidate.get("subject") or ""),
                "message_level_summary": str(candidate.get("snippet") or ""),
                "finding_ids": list(finding_summary["finding_ids"]),
                "finding_labels": list(finding_summary["finding_labels"]),
                "language_signals": [
                    {
                        "signal_id": str(signal.get("signal_id") or ""),
                        "label": str(signal.get("label") or ""),
                        "confidence": str(signal.get("confidence") or ""),
                    }
                    for signal in language.get("signals", [])
                    if isinstance(signal, dict)
                ],
                "behavior_candidates": behavior_candidates,
                "tone_summary": str(message_findings.get("tone_summary") or ""),
                "relevant_wording": [
                    {
                        "text": str(item.get("text") or ""),
                        "source_scope": str(item.get("source_scope") or ""),
                        "basis_id": str(item.get("basis_id") or ""),
                    }
                    for item in message_findings.get("relevant_wording", [])
                    if isinstance(item, dict)
                ],
                "omissions_or_process_signals": [
                    {
                        "signal": str(item.get("signal") or ""),
                        "summary": str(item.get("summary") or ""),
                    }
                    for item in message_findings.get("omissions_or_process_signals", [])
                    if isinstance(item, dict)
                ],
                "included_actors": [str(item) for item in message_findings.get("included_actors", []) if str(item).strip()],
                "excluded_actors": [str(item) for item in message_findings.get("excluded_actors", []) if str(item).strip()],
                "communication_classification": {
                    "primary_class": str(communication_classification.get("primary_class") or "neutral"),
                    "applied_classes": [
                        str(item) for item in communication_classification.get("applied_classes", []) if str(item).strip()
                    ]
                    or ["neutral"],
                    "confidence": str(communication_classification.get("confidence") or "low"),
                    "rationale": str(communication_classification.get("rationale") or ""),
                },
                "evidence_strength": message_row_strength(
                    language_signal_count=int(language.get("signal_count") or 0),
                    behavior_candidate_count=len(behavior_candidates),
                    finding_strengths=list(finding_summary["evidence_strength_labels"]),
                ),
                "counter_indicators": row_counter_indicators,
                "alternative_explanations": list(finding_summary["alternative_explanations"]),
                "supporting_citation_ids": citations.get(uid, []),
            }
        )
    rows.sort(key=lambda row: (str(row.get("date") or ""), str(row.get("uid") or "")))
    return {
        "included": True,
        "review_table_version": "2",
        "row_count": len(rows),
        "rows": rows,
    }
