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
    assert findings["communication_classification"]["primary_class"] == "controlling"
    assert "alex@example.com" in findings["included_actors"]
    assert any(item["text"].lower() == "for the record" for item in findings["relevant_wording"])
    assert findings["tone_summary"]


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
    assert findings["communication_classification"]["primary_class"] == "exclusionary"
    assert findings["excluded_actors"] == ["alex@example.com"]
    assert any(item["signal"] == "target_absent_from_visible_recipients" for item in findings["omissions_or_process_signals"])


def test_analyze_message_behavior_does_not_infer_omission_based_target_linkage_without_target_reference():
    rhetoric = analyze_message_rhetoric(
        "We decided to proceed without delay and will circulate the update later.",
        text_scope="authored_text",
    )

    findings = analyze_message_behavior(
        "We decided to proceed without delay and will circulate the update later.",
        text_scope="authored_text",
        rhetoric=rhetoric,
        recipient_count=2,
        visible_recipient_emails=["manager@example.com", "hr@example.com"],
        case_target_email="alex@example.com",
        case_target_name="Alex Example",
    )

    behavior_ids = [candidate["behavior_id"] for candidate in findings["behavior_candidates"]]

    assert "exclusion" not in behavior_ids
    assert "withholding" not in behavior_ids
    assert findings["excluded_actors"] == []
    assert all(item["signal"] != "target_absent_from_visible_recipients" for item in findings["omissions_or_process_signals"])
    assert findings["communication_classification"]["primary_class"] != "exclusionary"


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


def test_analyze_message_behavior_adds_blame_shifting_for_narrative_framing() -> None:
    rhetoric = analyze_message_rhetoric(
        "Due to your delay, the timeline slipped. It appears questions remain about your handling of the issue.",
        text_scope="authored_text",
    )

    findings = analyze_message_behavior(
        "Due to your delay, the timeline slipped. It appears questions remain about your handling of the issue.",
        text_scope="authored_text",
        rhetoric=rhetoric,
    )

    behavior_ids = [candidate["behavior_id"] for candidate in findings["behavior_candidates"]]

    assert "blame_shifting" in behavior_ids


def test_analyze_message_behavior_detects_german_patronizing_public_correction_and_low_confidence_escalation() -> None:
    rhetoric = analyze_message_rhetoric(
        (
            "Wie schon mehrfach mitgeteilt, ist Ihre Darstellung unzutreffend. "
            "Wir bitten Sie höflich um Kenntnisnahme, dass der Vorgang entsprechend vermerkt wird. "
            "Als zuständige Stelle gehe ich davon aus, dass sich weitere Rückfragen erübrigen."
        ),
        text_scope="authored_text",
    )

    findings = analyze_message_behavior(
        (
            "Wie schon mehrfach mitgeteilt, ist Ihre Darstellung unzutreffend. "
            "Wir bitten Sie höflich um Kenntnisnahme, dass der Vorgang entsprechend vermerkt wird. "
            "Als zuständige Stelle gehe ich davon aus, dass sich weitere Rückfragen erübrigen."
        ),
        text_scope="authored_text",
        rhetoric=rhetoric,
        recipient_count=3,
        visible_recipient_emails=["alex@example.com", "hr@example.com", "leitung@example.com"],
        case_target_email="alex@example.com",
        case_target_name="Alex Example",
    )

    by_id = {candidate["behavior_id"]: candidate for candidate in findings["behavior_candidates"]}

    assert "public_correction" in by_id
    assert "undermining" in by_id
    assert "escalation" in by_id
    assert by_id["escalation"]["confidence"] == "low"


def test_analyze_message_behavior_classifies_neutral_messages() -> None:
    rhetoric = analyze_message_rhetoric(
        "Please confirm receipt of the attached file.",
        text_scope="authored_text",
    )

    findings = analyze_message_behavior(
        "Please confirm receipt of the attached file.",
        text_scope="authored_text",
        rhetoric=rhetoric,
        recipient_count=1,
        visible_recipient_emails=["alex@example.com"],
        case_target_email="alex@example.com",
        case_target_name="Alex Example",
    )

    assert findings["behavior_candidates"] == []
    assert findings["communication_classification"]["primary_class"] == "neutral"
    assert findings["communication_classification"]["applied_classes"] == ["neutral"]
    assert findings["relevant_wording"] == []
