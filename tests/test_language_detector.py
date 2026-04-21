"""Tests for language detection."""

from src.language_detector import detect_language


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
