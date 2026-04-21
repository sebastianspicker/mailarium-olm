from __future__ import annotations

from src.behavioral_evidence_chains import build_behavioral_evidence_chains


def test_build_behavioral_evidence_chains_assigns_ids_and_downgrades_inferred_quotes():
    candidates = [
        {
            "uid": "u1",
            "date": "2026-02-10T10:00:00",
            "subject": "Process update",
            "sender_email": "manager@example.com",
            "sender_actor_id": "actor-manager",
            "snippet": "For the record, you failed to provide the figures.",
            "provenance": {
                "evidence_handle": "email:u1:0:20",
                "snippet_start": 0,
                "snippet_end": 20,
            },
            "message_findings": {
                "authored_text": {
                    "behavior_candidates": [
                        {
                            "behavior_id": "escalation",
                            "label": "Escalation",
                            "evidence": [
                                {
                                    "source_scope": "authored_text",
                                    "excerpt": "For the record",
                                    "matched_text": "For the record",
                                    "start": 0,
                                    "end": 14,
                                }
                            ],
                        }
                    ],
                    "counter_indicators": [],
                },
                "quoted_blocks": [
                    {
                        "segment_ordinal": 2,
                        "segment_type": "quoted_reply",
                        "speaker_email": "alex@example.com",
                        "speaker_source": "quoted_block_email",
                        "quote_attribution_status": "inferred_single_candidate",
                        "quote_attribution_reason": "Only one non-authored identity is visible in the quoted block.",
                        "candidate_emails": ["alex@example.com"],
                        "downgraded_due_to_quote_ambiguity": True,
                        "speaker_confidence": 0.6,
                        "text": "You failed to provide the figures.",
                        "findings": {
                            "behavior_candidates": [
                                {
                                    "behavior_id": "public_correction",
                                    "label": "Public Correction",
                                    "evidence": [
                                        {
                                            "source_scope": "quoted_text",
                                            "excerpt": "failed to provide",
                                            "matched_text": "failed to provide",
                                            "start": 4,
                                            "end": 21,
                                        }
                                    ],
                                }
                            ],
                            "counter_indicators": [],
                        },
                    }
                ],
            },
        }
    ]

    finding_index, evidence_table = build_behavioral_evidence_chains(
        candidates=candidates,
        case_patterns=None,
        retaliation_analysis=None,
        comparative_treatment=None,
        communication_graph=None,
    )

    assert finding_index["version"] == "1"
    assert finding_index["finding_count"] == 2
    authored = next(finding for finding in finding_index["findings"] if finding["finding_scope"] == "message_behavior")
    quoted = next(finding for finding in finding_index["findings"] if finding["finding_scope"] == "quoted_message_behavior")
    assert authored["finding_id"] == "message:u1:authored:escalation:1"
    assert authored["supporting_evidence"][0]["text_attribution"]["authored_quoted_inferred_status"] == "authored"
    assert authored["supporting_evidence"][0]["provenance"]["provenance_kind"] == "direct_text"
    assert authored["supporting_evidence"][0]["provenance"]["inference_basis"] == "message_local_text"
    assert quoted["finding_id"] == "message:u1:quoted:2:public_correction:1"
    assert quoted["quote_ambiguity"]["downgraded_due_to_quote_ambiguity"] is True
    assert quoted["quote_ambiguity"]["quote_attribution_status"] == "inferred_single_candidate"
    assert quoted["supporting_evidence"][0]["text_attribution"]["speaker_status"] == "inferred"
    assert quoted["supporting_evidence"][0]["text_attribution"]["authored_quoted_inferred_status"] == "inferred"
    assert quoted["supporting_evidence"][0]["provenance"]["provenance_kind"] == "quoted_text"
    assert quoted["supporting_evidence"][0]["provenance"]["inference_basis"] == "inferred_single_candidate"
    assert evidence_table["row_count"] == 2
    assert evidence_table["rows"][1]["authored_quoted_inferred_status"] == "inferred"
    assert evidence_table["rows"][1]["provenance_kind"] == "quoted_text"


def test_build_behavioral_evidence_chains_marks_graph_and_comparator_as_inferred_support() -> None:
    candidates = [
        {
            "uid": "u1",
            "date": "2026-02-10T10:00:00",
            "subject": "Status",
            "sender_email": "manager@example.com",
            "sender_actor_id": "actor-manager",
            "snippet": "Status update for Alex Example.",
            "provenance": {
                "evidence_handle": "email:u1:0:20",
                "snippet_start": 0,
                "snippet_end": 20,
            },
        },
        {
            "uid": "u2",
            "date": "2026-02-11T10:00:00",
            "subject": "Comparator status",
            "sender_email": "manager@example.com",
            "sender_actor_id": "actor-manager",
            "snippet": "Comparator update for Pat Peer.",
            "provenance": {
                "evidence_handle": "email:u2:0:24",
                "snippet_start": 0,
                "snippet_end": 24,
            },
        },
    ]

    finding_index, evidence_table = build_behavioral_evidence_chains(
        candidates=candidates,
        case_patterns=None,
        retaliation_analysis={
            "trigger_events": [
                {
                    "trigger_type": "complaint",
                    "date": "2026-02-10",
                    "assessment": {"status": "mixed_shift"},
                    "evidence_chain": {
                        "before_uids": ["u1"],
                        "after_uids": ["u2"],
                    },
                }
            ]
        },
        comparative_treatment={
            "comparator_summaries": [
                {
                    "comparator_actor_id": "actor-peer",
                    "sender_actor_id": "actor-manager",
                    "status": "comparator_available",
                    "evidence_chain": {
                        "target_uids": ["u1"],
                        "comparator_uids": ["u2"],
                    },
                }
            ]
        },
        communication_graph={
            "graph_findings": [
                {
                    "finding_id": "graph-1",
                    "graph_signal_type": "visibility_asymmetry",
                    "evidence_chain": {
                        "included_uids": ["u1"],
                        "excluded_uids": ["u2"],
                    },
                    "counter_indicators": [],
                }
            ]
        },
    )

    retaliation = next(f for f in finding_index["findings"] if f["finding_scope"] == "retaliation_analysis")
    comparator = next(f for f in finding_index["findings"] if f["finding_scope"] == "comparative_treatment")
    graph = next(f for f in finding_index["findings"] if f["finding_scope"] == "communication_graph")

    assert retaliation["supporting_evidence"][0]["provenance"]["provenance_kind"] == "trigger_inference"
    assert comparator["supporting_evidence"][0]["provenance"]["provenance_kind"] == "comparative_inference"
    assert graph["supporting_evidence"][0]["provenance"]["provenance_kind"] == "graph_inference"
    assert graph["supporting_evidence"][0]["text_attribution"]["text_origin"] == "metadata"

    graph_row = next(row for row in evidence_table["rows"] if row["finding_scope"] == "communication_graph")
    assert graph_row["provenance_kind"] == "graph_inference"
    assert graph_row["inference_basis"] == "communication_graph_signal"
    assert graph_row["evidence_chain_role"] == "supporting"
