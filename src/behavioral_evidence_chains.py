"""Evidence-chain and citation helpers for behavioural-analysis findings."""
# pylint: disable=too-many-branches,too-many-locals,too-many-statements

from __future__ import annotations

from collections import Counter
from typing import Any

from .behavioral_evidence_chain_citations import (
    _as_dict,
    _authored_citations,
    _quoted_citations,
    _summary_citations,
)

BEHAVIORAL_EVIDENCE_CHAINS_VERSION = "1"


def _candidate_index(candidates: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return body candidates indexed by UID."""
    return {str(candidate.get("uid") or ""): candidate for candidate in candidates if str(candidate.get("uid") or "")}


def _table_rows(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten finding evidence into exportable table rows."""
    rows: list[dict[str, Any]] = []
    for finding in findings:
        for key in ("supporting_evidence", "contradictory_evidence"):
            role_rows = finding.get(key)
            if not isinstance(role_rows, list):
                continue
            for citation in role_rows:
                if not isinstance(citation, dict):
                    continue
                rows.append(_table_row(finding, citation))
    return rows


def _table_row(finding: dict[str, Any], citation: dict[str, Any]) -> dict[str, Any]:
    passage = _as_dict(citation.get("passage"))
    bounds = _as_dict(passage.get("bounds"))
    actors = _as_dict(citation.get("actors"))
    attribution = _as_dict(citation.get("text_attribution"))
    provenance = _as_dict(citation.get("provenance"))
    return {
        "finding_id": _text(finding, "finding_id"),
        "finding_scope": _text(finding, "finding_scope"),
        "finding_label": _text(finding, "finding_label"),
        "evidence_role": _text(citation, "evidence_role"),
        "message_or_document_id": _text(citation, "message_or_document_id"),
        "timestamp": _text(citation, "timestamp"),
        "source_type": _text(citation, "source_type"),
        "actor_ids": list(actors.get("actor_ids") or []),
        "actor_emails": list(actors.get("actor_emails") or []),
        "text_origin": _text(attribution, "text_origin"),
        "authored_quoted_inferred_status": _text(attribution, "authored_quoted_inferred_status"),
        "speaker_status": _text(attribution, "speaker_status"),
        "evidence_handle": _text(provenance, "evidence_handle"),
        "provenance_kind": _text(provenance, "provenance_kind"),
        "inference_basis": _text(provenance, "inference_basis"),
        "evidence_chain_role": _text(provenance, "evidence_chain_role"),
        "excerpt": _text(passage, "excerpt"),
        "segment_ordinal": bounds.get("segment_ordinal"),
        "start": bounds.get("start"),
        "end": bounds.get("end"),
    }


def _text(payload: dict[str, Any], key: str) -> str:
    return str(payload.get(key) or "")


def build_behavioral_evidence_chains(
    *,
    candidates: list[dict[str, Any]],
    case_patterns: dict[str, Any] | None,
    retaliation_analysis: dict[str, Any] | None,
    comparative_treatment: dict[str, Any] | None,
    communication_graph: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a stable finding-to-evidence index plus flat exportable evidence rows."""
    findings: list[dict[str, Any]] = []
    candidate_map = _candidate_index(candidates)

    _append_message_findings(findings, candidates)
    _append_case_pattern_findings(findings, case_patterns, candidate_map)

    _append_retaliation_findings(findings, retaliation_analysis, candidate_map)
    _append_comparator_findings(findings, comparative_treatment, candidate_map)
    _append_graph_findings(findings, communication_graph, candidate_map)

    rows = _table_rows(findings)
    return (
        {
            "version": BEHAVIORAL_EVIDENCE_CHAINS_VERSION,
            "finding_count": len(findings),
            "findings": findings,
        },
        {
            "version": BEHAVIORAL_EVIDENCE_CHAINS_VERSION,
            "row_count": len(rows),
            "summary": {
                "finding_scope_counts": dict(
                    sorted(Counter(str(finding.get("finding_scope") or "") for finding in findings).items())
                ),
                "evidence_role_counts": dict(sorted(Counter(str(row.get("evidence_role") or "") for row in rows).items())),
            },
            "rows": rows,
        },
    )


def _no_quote_ambiguity() -> dict[str, object]:
    return {"downgraded_due_to_quote_ambiguity": False, "reason": ""}


def _append_message_findings(findings, candidates):
    for candidate in candidates:
        message_findings = candidate.get("message_findings")
        if not isinstance(message_findings, dict):
            continue
        _append_authored_findings(findings, candidate, message_findings)
        _append_quoted_findings(findings, candidate, message_findings)


def _append_authored_findings(findings, candidate, message_findings):
    authored = message_findings.get("authored_text")
    if not isinstance(authored, dict):
        return
    uid = str(candidate.get("uid") or "")
    for index, behavior in enumerate(authored.get("behavior_candidates", []), start=1):
        if not isinstance(behavior, dict):
            continue
        finding_id = str(behavior.get("finding_id") or f"message:{uid}:authored:{behavior.get('behavior_id')}:{index}")
        behavior["finding_id"] = finding_id
        findings.append(
            {
                "finding_id": finding_id,
                "finding_scope": "message_behavior",
                "finding_label": str(behavior.get("label") or behavior.get("behavior_id") or ""),
                "supporting_evidence": _authored_citations(
                    finding_id=finding_id, candidate=candidate, evidence_items=list(behavior.get("evidence") or [])
                ),
                "contradictory_evidence": [],
                "counter_indicators": list(authored.get("counter_indicators") or []),
                "quote_ambiguity": _no_quote_ambiguity(),
            }
        )


def _append_quoted_findings(findings, candidate, message_findings):
    uid = str(candidate.get("uid") or "")
    for block_index, block in enumerate(message_findings.get("quoted_blocks", []) or [], start=1):
        details = block.get("findings") if isinstance(block, dict) else None
        if not isinstance(details, dict):
            continue
        for index, behavior in enumerate(details.get("behavior_candidates", []), start=1):
            if not isinstance(behavior, dict):
                continue
            finding_id = _quoted_finding_id(behavior, uid, block, block_index, index)
            behavior["finding_id"] = finding_id
            citations, quality = _quoted_citations(
                finding_id=finding_id,
                candidate=candidate,
                quoted_block=block,
                evidence_items=list(behavior.get("evidence") or []),
            )
            findings.append(
                {
                    "finding_id": finding_id,
                    "finding_scope": "quoted_message_behavior",
                    "finding_label": str(behavior.get("label") or behavior.get("behavior_id") or ""),
                    "supporting_evidence": citations,
                    "contradictory_evidence": [],
                    "counter_indicators": list(details.get("counter_indicators") or []),
                    "quote_ambiguity": quality,
                }
            )


def _quoted_finding_id(behavior, uid, block, block_index, index):
    ordinal = block.get("segment_ordinal") or block_index
    fallback = f"message:{uid}:quoted:{ordinal}:{behavior.get('behavior_id')}:{index}"
    return str(behavior.get("finding_id") or fallback)


def _append_case_pattern_findings(findings, case_patterns, candidate_map):
    if not isinstance(case_patterns, dict):
        return
    for key in ("behavior_patterns", "taxonomy_patterns", "thread_patterns"):
        for summary in case_patterns.get(key, []) or []:
            if isinstance(summary, dict):
                _append_case_pattern(findings, summary, candidate_map)
    for index, summary in enumerate(case_patterns.get("directional_summaries", []) or [], start=1):
        if isinstance(summary, dict):
            finding_id = str(
                summary.get("finding_id")
                or (
                    f"directional:{summary.get('sender_actor_id') or 'unknown'}:"
                    f"{summary.get('target_actor_id') or 'unknown'}:{index}"
                )
            )
            summary["finding_id"] = finding_id
            findings.append(
                _summary_finding(
                    finding_id,
                    "directional_summary",
                    "Directional summary",
                    candidate_map,
                    list(summary.get("message_uids") or []),
                    "directional_inference",
                    "directional_summary",
                )
            )


def _append_case_pattern(findings, summary, candidate_map):
    finding_id = str(summary.get("finding_id") or summary.get("cluster_id") or "")
    summary["finding_id"] = finding_id
    finding = _summary_finding(
        finding_id,
        "case_pattern",
        str(summary.get("key") or ""),
        candidate_map,
        list(summary.get("message_uids") or []),
        "pattern_inference",
        "case_pattern_summary",
    )
    finding["supporting_evidence"] = _summary_citations(
        finding_id=finding_id,
        candidate_map=candidate_map,
        uids=list(summary.get("message_uids") or []),
        evidence_role="supporting",
        note=str(summary.get("primary_recurrence") or ""),
        provenance_kind="pattern_inference",
        inference_basis="case_pattern_summary",
    )
    findings.append(finding)


def _summary_finding(finding_id, scope, label, candidate_map, uids, provenance_kind, inference_basis):
    return {
        "finding_id": finding_id,
        "finding_scope": scope,
        "finding_label": label,
        "supporting_evidence": _summary_citations(
            finding_id=finding_id,
            candidate_map=candidate_map,
            uids=uids,
            evidence_role="supporting",
            provenance_kind=provenance_kind,
            inference_basis=inference_basis,
        ),
        "contradictory_evidence": [],
        "counter_indicators": [],
        "quote_ambiguity": _no_quote_ambiguity(),
    }


def _append_retaliation_findings(findings, analysis, candidate_map):
    if not isinstance(analysis, dict):
        return
    for index, event in enumerate(analysis.get("trigger_events", []) or [], start=1):
        if not isinstance(event, dict):
            continue
        finding_id = str(
            event.get("finding_id") or f"retaliation:{event.get('trigger_type') or 'trigger'}:{event.get('date') or index}"
        )
        event["finding_id"] = finding_id
        chain = _as_dict(event.get("evidence_chain"))
        citations = [
            *_summary_citations(
                finding_id=finding_id,
                candidate_map=candidate_map,
                uids=list(chain.get("before_uids") or []),
                evidence_role="before_context",
                provenance_kind="trigger_inference",
                inference_basis="retaliation_before_context",
            ),
            *_summary_citations(
                finding_id=finding_id,
                candidate_map=candidate_map,
                uids=list(chain.get("after_uids") or []),
                evidence_role="after_context",
                note=str((event.get("assessment") or {}).get("status") or ""),
                provenance_kind="trigger_inference",
                inference_basis="retaliation_after_context",
            ),
        ]
        findings.append(
            {
                "finding_id": finding_id,
                "finding_scope": "retaliation_analysis",
                "finding_label": str(event.get("trigger_type") or "trigger_event"),
                "supporting_evidence": citations,
                "contradictory_evidence": [],
                "counter_indicators": [],
                "quote_ambiguity": _no_quote_ambiguity(),
            }
        )


def _append_comparator_findings(findings, analysis, candidate_map):
    if not isinstance(analysis, dict):
        return
    for index, summary in enumerate(analysis.get("comparator_summaries", []) or [], start=1):
        if not isinstance(summary, dict):
            continue
        finding_id = str(
            summary.get("finding_id")
            or (
                f"comparator:{summary.get('comparator_actor_id') or summary.get('comparator_email') or 'comparator'}:"
                f"{summary.get('sender_actor_id') or index}"
            )
        )
        summary["finding_id"] = finding_id
        chain = _as_dict(summary.get("evidence_chain"))
        citations = [
            *_summary_citations(
                finding_id=finding_id,
                candidate_map=candidate_map,
                uids=list(chain.get("target_uids") or []),
                evidence_role="target_comparison",
                provenance_kind="comparative_inference",
                inference_basis="target_comparator_comparison",
            ),
            *_summary_citations(
                finding_id=finding_id,
                candidate_map=candidate_map,
                uids=list(chain.get("comparator_uids") or []),
                evidence_role="comparator_comparison",
                provenance_kind="comparative_inference",
                inference_basis="target_comparator_comparison",
            ),
        ]
        findings.append(
            {
                "finding_id": finding_id,
                "finding_scope": "comparative_treatment",
                "finding_label": str(summary.get("status") or "comparative_treatment"),
                "supporting_evidence": citations,
                "contradictory_evidence": [],
                "counter_indicators": [],
                "quote_ambiguity": _no_quote_ambiguity(),
            }
        )


def _append_graph_findings(findings, graph, candidate_map):
    if not isinstance(graph, dict):
        return
    for finding in graph.get("graph_findings", []) or []:
        if not isinstance(finding, dict):
            continue
        finding_id = str(finding.get("finding_id") or "")
        chain = _as_dict(finding.get("evidence_chain"))
        uids = [str(uid) for key in ("message_uids", "included_uids", "excluded_uids") for uid in chain.get(key, []) if uid]
        citations = _summary_citations(
            finding_id=finding_id,
            candidate_map=candidate_map,
            uids=uids,
            evidence_role="supporting",
            provenance_kind="graph_inference",
            inference_basis="communication_graph_signal",
            text_origin="metadata",
        )
        findings.append(
            {
                "finding_id": finding_id,
                "finding_scope": "communication_graph",
                "finding_label": str(finding.get("graph_signal_type") or ""),
                "supporting_evidence": citations,
                "contradictory_evidence": [],
                "counter_indicators": list(finding.get("counter_indicators") or []),
                "quote_ambiguity": _no_quote_ambiguity(),
            }
        )
