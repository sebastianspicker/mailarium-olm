from __future__ import annotations

from src.language_rhetoric import analyze_message_rhetoric


def test_analyze_message_rhetoric_detects_expanded_german_bureaucratic_pressure_signals() -> None:
    analysis = analyze_message_rhetoric(
        (
            "Wie schon mehrfach mitgeteilt, ist Ihre Darstellung unzutreffend. "
            "Wir bitten Sie höflich um Kenntnisnahme, dass der Vorgang entsprechend vermerkt wird. "
            "Als zuständige Stelle gehe ich davon aus, dass sich weitere Rückfragen erübrigen."
        ),
        text_scope="authored_text",
    )

    signal_ids = [signal["signal_id"] for signal in analysis["signals"]]

    assert "dismissiveness" in signal_ids
    assert "competence_framing" in signal_ids
    assert "selective_politeness" in signal_ids
    assert "procedural_intimidation" in signal_ids
    assert "status_marking" in signal_ids
    assert "passive_aggressive_deflection" in signal_ids
    assert "gaslighting_like_contradiction" in signal_ids


def test_analyze_message_rhetoric_detects_expanded_german_patronizing_and_ambiguity_signals() -> None:
    analysis = analyze_message_rhetoric(
        (
            "Zu Ihrer Orientierung führe ich das gern noch einmal aus. "
            "Nach hiesigem Kenntnisstand entsteht der Eindruck, dass hier noch Fragen offen sind."
        ),
        text_scope="quoted_text",
    )

    signal_ids = [signal["signal_id"] for signal in analysis["signals"]]

    assert "patronizing_wording" in signal_ids
    assert "strategic_ambiguity" in signal_ids


def test_analyze_message_rhetoric_does_not_overfit_neutral_formal_german_office_language() -> None:
    analysis = analyze_message_rhetoric(
        (
            "Bitte nehmen Sie zur Kenntnis, dass die Unterlagen im Portal bereitstehen. "
            "Für Rückfragen stehe ich gern zur Verfügung."
        ),
        text_scope="authored_text",
    )

    signal_ids = [signal["signal_id"] for signal in analysis["signals"]]

    assert "selective_politeness" in signal_ids
    assert "procedural_intimidation" not in signal_ids
    assert "passive_aggressive_deflection" not in signal_ids
    assert "status_marking" not in signal_ids
    assert "gaslighting_like_contradiction" not in signal_ids
