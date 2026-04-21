from __future__ import annotations

from src.language_rhetoric import analyze_message_rhetoric


def test_analyze_message_rhetoric_detects_multiple_authored_signals():
    analysis = analyze_message_rhetoric(
        ("For the record, you failed to provide the figures. As already stated, please just send them today."),
        text_scope="authored_text",
    )

    signal_ids = [signal["signal_id"] for signal in analysis["signals"]]
    assert analysis["text_scope"] == "authored_text"
    assert "institutional_pressure_framing" in signal_ids
    assert "implicit_accusation" in signal_ids
    assert "dismissiveness" in signal_ids
    assert all(signal["evidence"] for signal in analysis["signals"])


def test_analyze_message_rhetoric_keeps_ambiguity_signals_low_confidence():
    analysis = analyze_message_rhetoric(
        "It appears questions remain about the timeline.",
        text_scope="quoted_text",
    )

    assert analysis["signals"] == [
        {
            "signal_id": "strategic_ambiguity",
            "label": "Strategic Ambiguity",
            "confidence": "low",
            "rationale": "Uses vague concern-framing without clearly stating the underlying claim or basis.",
            "evidence": [
                {
                    "source_text_scope": "quoted_text",
                    "excerpt": "It appears questions remain about the timeline.",
                    "matched_text": "It appears",
                    "start": 0,
                    "end": 10,
                }
            ],
        }
    ]


def test_analyze_message_rhetoric_detects_gaslighting_like_pattern_as_low_confidence():
    analysis = analyze_message_rhetoric(
        "As already explained, you are mistaken about what happened.",
        text_scope="authored_text",
    )

    signal_ids = [signal["signal_id"] for signal in analysis["signals"]]
    contradiction_signal = next(
        signal for signal in analysis["signals"] if signal["signal_id"] == "gaslighting_like_contradiction"
    )

    assert "dismissiveness" in signal_ids
    assert "gaslighting_like_contradiction" in signal_ids
    assert contradiction_signal["confidence"] == "low"


def test_analyze_message_rhetoric_detects_subtle_workplace_signals_in_english() -> None:
    analysis = analyze_message_rhetoric(
        ("With all due respect, kindly note that this will be documented. As your manager, I trust this clarifies matters."),
        text_scope="authored_text",
    )

    signal_ids = [signal["signal_id"] for signal in analysis["signals"]]

    assert "selective_politeness" in signal_ids
    assert "procedural_intimidation" in signal_ids
    assert "status_marking" in signal_ids
    assert "passive_aggressive_deflection" in signal_ids


def test_analyze_message_rhetoric_detects_german_workplace_signals() -> None:
    analysis = analyze_message_rhetoric(
        (
            "Wie bereits mitgeteilt, Sie haben das missverstanden. "
            "Bitte nehmen Sie zur Kenntnis, dass dies dokumentiert wird. "
            "In meiner Funktion als Leitung erwarte ich das."
        ),
        text_scope="quoted_text",
    )

    signal_ids = [signal["signal_id"] for signal in analysis["signals"]]

    assert "dismissiveness" in signal_ids
    assert "selective_politeness" in signal_ids
    assert "procedural_intimidation" in signal_ids
    assert "status_marking" in signal_ids
    assert "gaslighting_like_contradiction" in signal_ids
