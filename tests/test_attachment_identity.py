from __future__ import annotations

from src.attachment_identity import normalize_attachment_search_text


def test_normalize_attachment_search_text_handles_umlauts_and_sharp_s() -> None:
    normalized = normalize_attachment_search_text("Maßnahme für Wiedereingliederung")

    assert "massnahme" in normalized
    assert "fuer" in normalized
    assert "wiedereingliederung" in normalized


def test_normalize_attachment_search_text_dehyphenates_line_break_words() -> None:
    normalized = normalize_attachment_search_text("Stufen-\nvorweggewährung und Teilha-\nbe")

    assert "stufenvorweggewaehrung" in normalized
    assert "teilhabe" in normalized
