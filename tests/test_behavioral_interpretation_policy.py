from __future__ import annotations

from src.behavioral_interpretation_policy import (
    cautious_rewrite_for_weakness,
    classify_claim_level,
    guarded_statement_for_finding,
    interpretation_policy_payload,
)


def test_classify_claim_level_caps_retaliation_findings_at_pattern_concern() -> None:
    claim_level, policy_reason = classify_claim_level(
        {
            "finding_scope": "retaliation_analysis",
            "finding_label": "Retaliatory sequence",
            "supporting_evidence": [{"citation_id": "c-1"}],
            "evidence_strength": {"label": "strong_indicator"},
            "confidence_split": {
                "interpretation_confidence": {
                    "label": "high",
                }
            },
        }
    )

    assert claim_level == "pattern_concern"
    assert "concern wording" in policy_reason.lower()


def test_guarded_statement_for_finding_keeps_high_stakes_interpretation_non_verdict_like() -> None:
    statement, claim_level, _, _, _ = guarded_statement_for_finding(
        {
            "finding_scope": "comparative_treatment",
            "finding_label": "Discrimination concern",
            "supporting_evidence": [{"citation_id": "c-2"}],
            "evidence_strength": {"label": "strong_indicator"},
            "confidence_split": {
                "interpretation_confidence": {
                    "label": "high",
                }
            },
        }
    )

    assert claim_level == "pattern_concern"
    assert "raises a concern pattern" in statement.lower()
    assert "legal conclusion" not in statement.lower()
    assert "motive" not in statement.lower()


def test_interpretation_policy_payload_lists_refusal_rules() -> None:
    payload = interpretation_policy_payload()

    assert payload["refuse_to_overclaim"] is True
    assert "unsupported protected-category inference" in payload["prohibited_claims"]
    assert "psychiatric labeling of actors" in payload["prohibited_claims"]
    assert any("Do not assert motive" in rule for rule in payload["refusal_rules"])


def test_cautious_rewrite_for_weakness_lowers_overstatement() -> None:
    rewrite = cautious_rewrite_for_weakness(
        weakness_category="unsupported_motive_claim",
        subject="retaliation concern",
    )

    assert "proven motive" not in rewrite.lower()
    assert "concern wording" in rewrite.lower() or "should not be framed" in rewrite.lower()
