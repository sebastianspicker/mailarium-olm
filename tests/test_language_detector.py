"""Tests for language detection."""

from src.language_detector import detect_language, detect_language_details


def test_english():
    text = (
        "The quick brown fox jumps over the lazy dog. "
        "This is a test of the emergency broadcast system. "
        "We have been informed that this will not be a regular occurrence."
    )
    assert detect_language(text) == "en"


def test_german():
    text = (
        "Der schnelle braune Fuchs springt über den faulen Hund. "
        "Dies ist ein Test des Notfallübertragungssystems. "
        "Wir sind informiert worden, dass dies nicht regelmäßig vorkommen wird."
    )
    assert detect_language(text) == "de"


def test_french():
    text = (
        "Le renard brun rapide saute par-dessus le chien paresseux. "
        "Nous avons été informés que ce ne sera pas une occurrence régulière. "
        "Il est important de noter que les résultats sont très positifs pour nous."
    )
    assert detect_language(text) == "fr"


def test_spanish():
    text = (
        "El rápido zorro marrón salta sobre el perro perezoso. "
        "Hemos sido informados de que esto no será una ocurrencia regular. "
        "Es muy importante para todos los que están involucrados en el proyecto."
    )
    assert detect_language(text) == "es"


def test_short_text_returns_unknown():
    assert detect_language("hi") == "unknown"
    assert detect_language("ok") == "unknown"
    assert detect_language("") == "unknown"


def test_short_german_text_can_return_low_confidence_german() -> None:
    details = detect_language_details("zur Prüfung")

    assert details["language"] == "de"
    assert details["confidence"] == "low"
    assert details["reason"] == "short_text_stopword_vote"
    assert detect_language("zur Prüfung") == "de"


def test_short_text_without_signal_reports_reason_metadata() -> None:
    details = detect_language_details("ok")

    assert details["language"] == "unknown"
    assert details["confidence"] == "none"
    assert details["reason"] == "short_text_insufficient_signal"
    assert details["token_count"] == 1


def test_forwarded_german_subject_uses_marker_bias() -> None:
    details = detect_language_details("WG: Bitte um Rückmeldung zum Protokoll")

    assert details["language"] == "de"
    assert details["confidence"] in {"low", "medium", "high"}
    assert details["reason"] in {"short_text_german_marker", "stopword_overlap_with_markers", "german_marker_bias"}


def test_adjusted_scores_can_override_raw_stopword_hit_leader() -> None:
    details = detect_language_details("please send the report bitte rückmeldung zur besprechung")

    assert details["language"] == "de"
    assert details["reason"] == "stopword_overlap_with_markers"


def test_gibberish_returns_unknown():
    text = "xyzzy plugh frotz gnusto rezrov"
    assert detect_language(text) == "unknown"


def test_mixed_language_returns_dominant():
    # Predominantly English with a few German words
    text = (
        "The project was approved by the committee. "
        "We will proceed with the implementation as planned. "
        "This has been a very productive meeting for everyone involved."
    )
    assert detect_language(text) == "en"


def test_dutch():
    text = (
        "De snelle bruine vos springt over de luie hond. "
        "Dit is een test van het noodzendsysteem. "
        "Het is belangrijk om te weten dat dit niet regelmatig zal voorkomen."
    )
    assert detect_language(text) == "nl"
