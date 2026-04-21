from __future__ import annotations

from src.language_detector import _tokenize, detect_language


def test_detect_language_delegates_to_extracted_impl(monkeypatch):
    calls: list[str] = []

    def fake_detect(text: str) -> str:
        calls.append(text)
        return "sv"

    monkeypatch.setattr("src.language_detector.detect_language_impl", fake_detect)

    assert detect_language("detta ar ett test") == "sv"
    assert calls == ["detta ar ett test"]


def test_tokenize_compat_wrapper_delegates_to_extracted_impl(monkeypatch):
    calls: list[str] = []

    def fake_tokenize(text: str) -> list[str]:
        calls.append(text)
        return ["alpha", "beta"]

    monkeypatch.setattr("src.language_detector.tokenize_impl", fake_tokenize)

    assert _tokenize("Alpha Beta") == ["alpha", "beta"]
    assert calls == ["Alpha Beta"]
