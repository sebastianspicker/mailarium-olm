from __future__ import annotations

from src.behavioral_strength import apply_behavioral_strength


def test_apply_behavioral_strength_scores_findings_and_enriches_rows():
    finding_index = {
        "version": "1",
        "finding_count": 2,
        "findings": [
            {
                "finding_id": "f-strong",
                "finding_scope": "message_behavior",
                "finding_label": "Escalation",
                "supporting_evidence": [
                    {
                        "message_or_document_id": "u1",
                        "actors": {"actor_ids": ["actor-manager"], "actor_emails": ["manager@example.com"]},
                        "text_attribution": {"text_origin": "authored", "authored_quoted_inferred_status": "authored"},
                        "provenance": {"evidence_handle": "email:u1:1"},
                    },
                    {
                        "message_or_document_id": "u2",
                        "actors": {"actor_ids": ["actor-manager"], "actor_emails": ["manager@example.com"]},
                        "text_attribution": {"text_origin": "quoted", "authored_quoted_inferred_status": "quoted"},
                        "provenance": {"evidence_handle": "email:u2:1"},
                    },
                ],
                "contradictory_evidence": [],
                "counter_indicators": [],
                "quote_ambiguity": {"downgraded_due_to_quote_ambiguity": False, "reason": ""},
            },
            {
                "finding_id": "f-weak",
                "finding_scope": "communication_graph",
                "finding_label": "Visibility asymmetry",
                "supporting_evidence": [
                    {
                        "message_or_document_id": "u3",
                        "actors": {"actor_ids": [], "actor_emails": ["manager@example.com"]},
                        "text_attribution": {"text_origin": "metadata", "authored_quoted_inferred_status": "authored"},
                        "provenance": {"evidence_handle": "email:u3:1"},
                    }
                ],
                "contradictory_evidence": [],
                "counter_indicators": [
                    "Recipient omission may still have a neutral operational explanation without broader case context.",
                    "Different recipient sets may reflect different process stages rather than hostile exclusion.",
                ],
                "quote_ambiguity": {"downgraded_due_to_quote_ambiguity": True, "reason": "quoted speaker uncertain"},
            },
        ],
    }
    evidence_table = {
        "version": "1",
        "row_count": 2,
        "summary": {},
        "rows": [
            {"finding_id": "f-strong", "evidence_role": "supporting"},
            {"finding_id": "f-weak", "evidence_role": "supporting"},
        ],
    }

    enriched_index, enriched_table, rubric = apply_behavioral_strength(finding_index, evidence_table)

    assert rubric["version"] == "1"
    assert enriched_index["summary"]["evidence_strength_counts"]["strong_indicator"] == 1
    assert enriched_index["summary"]["evidence_strength_counts"]["insufficient_evidence"] == 1
    strong = next(finding for finding in enriched_index["findings"] if finding["finding_id"] == "f-strong")
    weak = next(finding for finding in enriched_index["findings"] if finding["finding_id"] == "f-weak")
    assert strong["evidence_strength"]["label"] == "strong_indicator"
    assert strong["confidence_split"]["evidence_confidence"]["label"] == "high"
    assert weak["evidence_strength"]["label"] == "insufficient_evidence"
    assert weak["confidence_split"]["interpretation_confidence"]["label"] == "low"
    assert weak["alternative_explanations"]
    assert enriched_table["rows"][0]["evidence_strength"] == "strong_indicator"
    assert enriched_table["rows"][1]["interpretation_confidence"] == "low"
