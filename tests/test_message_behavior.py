from __future__ import annotations

from src.language_rhetoric import analyze_message_rhetoric
from src.message_behavior import analyze_message_behavior


def test_analyze_message_behavior_distinguishes_behavior_candidates_from_wording_only():
    rhetoric = analyze_message_rhetoric(
        "For the record, you failed to provide the figures by end of day.",
        text_scope="authored_text",
    )

    findings = analyze_message_behavior(
        "For the record, you failed to provide the figures by end of day.",
        text_scope="authored_text",
        rhetoric=rhetoric,
        recipient_count=3,
        visible_recipient_emails=["alex@example.com", "hr@example.com", "manager@example.com"],
        case_target_email="alex@example.com",
        case_target_name="Alex Example",
    )

    behavior_ids = [candidate["behavior_id"] for candidate in findings["behavior_candidates"]]

    assert "escalation" in behavior_ids
    assert "public_correction" in behavior_ids
    assert "deadline_pressure" in behavior_ids
    assert findings["wording_only_signal_ids"] == []


def test_analyze_message_behavior_adds_omission_aware_exclusion_and_withholding():
    rhetoric = analyze_message_rhetoric(
        "We decided to proceed without delay. Alex Example will be informed later.",
        text_scope="authored_text",
    )

    findings = analyze_message_behavior(
        "We decided to proceed without delay. Alex Example will be informed later.",
        text_scope="authored_text",
        rhetoric=rhetoric,
        recipient_count=2,
        visible_recipient_emails=["manager@example.com", "hr@example.com"],
        case_target_email="alex@example.com",
        case_target_name="Alex Example",
    )

    behavior_ids = [candidate["behavior_id"] for candidate in findings["behavior_candidates"]]

    assert "exclusion" in behavior_ids
    assert "withholding" in behavior_ids
    assert any(candidate["evidence"][0]["source_scope"] == "message_metadata" for candidate in findings["behavior_candidates"])


def test_analyze_message_behavior_preserves_counter_indicator_when_only_wording_exists():
    rhetoric = analyze_message_rhetoric(
        "It appears questions remain about the timeline.",
        text_scope="quoted_text",
    )

    findings = analyze_message_behavior(
        "It appears questions remain about the timeline.",
        text_scope="quoted_text",
        rhetoric=rhetoric,
    )

    assert findings["behavior_candidates"] == []
    assert findings["wording_only_signal_ids"] == ["strategic_ambiguity"]
    assert (
        "Some rhetorical cues remained wording-only because message-level behavioural support was insufficient."
        in findings["counter_indicators"]
    )
