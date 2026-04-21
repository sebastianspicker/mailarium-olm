"""Evidence-chain and citation helpers for behavioural-analysis findings."""

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
                passage = _as_dict(citation.get("passage"))
                bounds = _as_dict(passage.get("bounds"))
                actors = _as_dict(citation.get("actors"))
                text_attribution = _as_dict(citation.get("text_attribution"))
                provenance = _as_dict(citation.get("provenance"))
                rows.append(
                    {
                        "finding_id": str(finding.get("finding_id") or ""),
                        "finding_scope": str(finding.get("finding_scope") or ""),
                        "finding_label": str(finding.get("finding_label") or ""),
                        "evidence_role": str(citation.get("evidence_role") or ""),
                        "message_or_document_id": str(citation.get("message_or_document_id") or ""),
                        "timestamp": str(citation.get("timestamp") or ""),
                        "source_type": str(citation.get("source_type") or ""),
                        "actor_ids": list(actors.get("actor_ids") or []),
                        "actor_emails": list(actors.get("actor_emails") or []),
                        "text_origin": str(text_attribution.get("text_origin") or ""),
                        "authored_quoted_inferred_status": str(text_attribution.get("authored_quoted_inferred_status") or ""),
                        "speaker_status": str(text_attribution.get("speaker_status") or ""),
                        "evidence_handle": str(provenance.get("evidence_handle") or ""),
                        "provenance_kind": str(provenance.get("provenance_kind") or ""),
                        "inference_basis": str(provenance.get("inference_basis") or ""),
                        "evidence_chain_role": str(provenance.get("evidence_chain_role") or ""),
                        "excerpt": str(passage.get("excerpt") or ""),
                        "segment_ordinal": bounds.get("segment_ordinal"),
                        "start": bounds.get("start"),
                        "end": bounds.get("end"),
                    }
                )
    return rows


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

    for candidate in candidates:
        uid = str(candidate.get("uid") or "")
        message_findings = candidate.get("message_findings")
        if not isinstance(message_findings, dict):
            continue
        authored = message_findings.get("authored_text")
        if isinstance(authored, dict):
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
                            finding_id=finding_id,
                            candidate=candidate,
                            evidence_items=list(behavior.get("evidence") or []),
                        ),
                        "contradictory_evidence": [],
                        "counter_indicators": list(authored.get("counter_indicators") or []),
                        "quote_ambiguity": {
                            "downgraded_due_to_quote_ambiguity": False,
                            "reason": "",
                        },
                    }
                )
        for block_index, quoted_block in enumerate(message_findings.get("quoted_blocks", []) or [], start=1):
            if not isinstance(quoted_block, dict):
                continue
            findings_block = quoted_block.get("findings")
            if not isinstance(findings_block, dict):
                continue
            for index, behavior in enumerate(findings_block.get("behavior_candidates", []), start=1):
                if not isinstance(behavior, dict):
                    continue
                finding_id = str(
                    behavior.get("finding_id")
                    or (
                        f"message:{uid}:quoted:{quoted_block.get('segment_ordinal') or block_index}:"
                        f"{behavior.get('behavior_id')}:{index}"
                    )
                )
                behavior["finding_id"] = finding_id
                citations, quote_quality = _quoted_citations(
                    finding_id=finding_id,
                    candidate=candidate,
                    quoted_block=quoted_block,
                    evidence_items=list(behavior.get("evidence") or []),
                )
                findings.append(
                    {
                        "finding_id": finding_id,
                        "finding_scope": "quoted_message_behavior",
                        "finding_label": str(behavior.get("label") or behavior.get("behavior_id") or ""),
                        "supporting_evidence": citations,
                        "contradictory_evidence": [],
                        "counter_indicators": list(findings_block.get("counter_indicators") or []),
                        "quote_ambiguity": quote_quality,
                    }
                )

    if isinstance(case_patterns, dict):
        for collection_key in ("behavior_patterns", "taxonomy_patterns", "thread_patterns"):
            for summary in case_patterns.get(collection_key, []) or []:
                if not isinstance(summary, dict):
                    continue
                finding_id = str(summary.get("finding_id") or summary.get("cluster_id") or "")
                summary["finding_id"] = finding_id
                findings.append(
                    {
                        "finding_id": finding_id,
                        "finding_scope": "case_pattern",
                        "finding_label": str(summary.get("key") or ""),
                        "supporting_evidence": _summary_citations(
                            finding_id=finding_id,
                            candidate_map=candidate_map,
                            uids=list(summary.get("message_uids") or []),
                            evidence_role="supporting",
                            note=str(summary.get("primary_recurrence") or ""),
                            provenance_kind="pattern_inference",
                            inference_basis="case_pattern_summary",
                        ),
                        "contradictory_evidence": [],
                        "counter_indicators": [],
                        "quote_ambiguity": {
                            "downgraded_due_to_quote_ambiguity": False,
                            "reason": "",
                        },
                    }
                )
        for index, summary in enumerate(case_patterns.get("directional_summaries", []) or [], start=1):
            if not isinstance(summary, dict):
                continue
            finding_id = str(
                summary.get("finding_id")
                or (
                    f"directional:{summary.get('sender_actor_id') or 'unknown'}:"
                    f"{summary.get('target_actor_id') or 'unknown'}:{index}"
                )
            )
            summary["finding_id"] = finding_id
            findings.append(
                {
                    "finding_id": finding_id,
                    "finding_scope": "directional_summary",
                    "finding_label": "Directional summary",
                    "supporting_evidence": _summary_citations(
                        finding_id=finding_id,
                        candidate_map=candidate_map,
                        uids=list(summary.get("message_uids") or []),
                        evidence_role="supporting",
                        provenance_kind="directional_inference",
                        inference_basis="directional_summary",
                    ),
                    "contradictory_evidence": [],
                    "counter_indicators": [],
                    "quote_ambiguity": {
                        "downgraded_due_to_quote_ambiguity": False,
                        "reason": "",
                    },
                }
            )

    if isinstance(retaliation_analysis, dict):
        for index, event in enumerate(retaliation_analysis.get("trigger_events", []) or [], start=1):
            if not isinstance(event, dict):
                continue
            finding_id = str(
                event.get("finding_id") or f"retaliation:{event.get('trigger_type') or 'trigger'}:{event.get('date') or index}"
            )
            event["finding_id"] = finding_id
            evidence_chain = _as_dict(event.get("evidence_chain"))
            findings.append(
                {
                    "finding_id": finding_id,
                    "finding_scope": "retaliation_analysis",
                    "finding_label": str(event.get("trigger_type") or "trigger_event"),
                    "supporting_evidence": [
                        *_summary_citations(
                            finding_id=finding_id,
                            candidate_map=candidate_map,
                            uids=list(evidence_chain.get("before_uids") or []),
                            evidence_role="before_context",
                            provenance_kind="trigger_inference",
                            inference_basis="retaliation_before_context",
                        ),
                        *_summary_citations(
                            finding_id=finding_id,
                            candidate_map=candidate_map,
                            uids=list(evidence_chain.get("after_uids") or []),
                            evidence_role="after_context",
                            note=str((event.get("assessment") or {}).get("status") or ""),
                            provenance_kind="trigger_inference",
                            inference_basis="retaliation_after_context",
                        ),
                    ],
                    "contradictory_evidence": [],
                    "counter_indicators": [],
                    "quote_ambiguity": {
                        "downgraded_due_to_quote_ambiguity": False,
                        "reason": "",
                    },
                }
            )

    if isinstance(comparative_treatment, dict):
        for index, summary in enumerate(comparative_treatment.get("comparator_summaries", []) or [], start=1):
            if not isinstance(summary, dict):
                continue
            finding_id = str(
                summary.get("finding_id")
                or (
                    "comparator:"
                    f"{summary.get('comparator_actor_id') or summary.get('comparator_email') or 'comparator'}:"
                    f"{summary.get('sender_actor_id') or index}"
                )
            )
            summary["finding_id"] = finding_id
            evidence_chain = _as_dict(summary.get("evidence_chain"))
            findings.append(
                {
                    "finding_id": finding_id,
                    "finding_scope": "comparative_treatment",
                    "finding_label": str(summary.get("status") or "comparative_treatment"),
                    "supporting_evidence": [
                        *_summary_citations(
                            finding_id=finding_id,
                            candidate_map=candidate_map,
                            uids=list(evidence_chain.get("target_uids") or []),
                            evidence_role="target_comparison",
                            provenance_kind="comparative_inference",
                            inference_basis="target_comparator_comparison",
                        ),
                        *_summary_citations(
                            finding_id=finding_id,
                            candidate_map=candidate_map,
                            uids=list(evidence_chain.get("comparator_uids") or []),
                            evidence_role="comparator_comparison",
                            provenance_kind="comparative_inference",
                            inference_basis="target_comparator_comparison",
                        ),
                    ],
                    "contradictory_evidence": [],
                    "counter_indicators": [],
                    "quote_ambiguity": {
                        "downgraded_due_to_quote_ambiguity": False,
                        "reason": "",
                    },
                }
            )

    if isinstance(communication_graph, dict):
        for finding in communication_graph.get("graph_findings", []) or []:
            if not isinstance(finding, dict):
                continue
            finding_id = str(finding.get("finding_id") or "")
            evidence_chain = _as_dict(finding.get("evidence_chain"))
            uids: list[str] = []
            for key in ("message_uids", "included_uids", "excluded_uids"):
                uids.extend([str(uid) for uid in evidence_chain.get(key, []) if uid])
            findings.append(
                {
                    "finding_id": finding_id,
                    "finding_scope": "communication_graph",
                    "finding_label": str(finding.get("graph_signal_type") or ""),
                    "supporting_evidence": _summary_citations(
                        finding_id=finding_id,
                        candidate_map=candidate_map,
                        uids=uids,
                        evidence_role="supporting",
                        provenance_kind="graph_inference",
                        inference_basis="communication_graph_signal",
                        text_origin="metadata",
                    ),
                    "contradictory_evidence": [],
                    "counter_indicators": list(finding.get("counter_indicators") or []),
                    "quote_ambiguity": {
                        "downgraded_due_to_quote_ambiguity": False,
                        "reason": "",
                    },
                }
            )

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
