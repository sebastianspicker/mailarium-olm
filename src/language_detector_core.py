"""Core helpers for the lightweight language detector."""

from __future__ import annotations

from collections import Counter

from .language_detector_data import STOPWORDS, TOKEN_RE


def tokenize_impl(text: str) -> list[str]:
    """Simple word tokenizer: lowercase, split on non-alpha."""
    return TOKEN_RE.findall(text.lower())


def score_languages_impl(tokens: list[str]) -> dict[str, float]:
    """Return normalized stopword-overlap scores for each supported language."""
    token_counts = Counter(tokens)
    total_tokens = len(tokens)

    return {
        lang: (
            sum(token_counts[word] for word in stopwords if word in token_counts) / total_tokens
            if total_tokens
            else 0.0
        )
        for lang, stopwords in STOPWORDS.items()
    }


def detect_language_impl(text: str) -> str:
    """Detect the language of the given text."""
    tokens = tokenize_impl(text)
    if len(tokens) < 5:
        return "unknown"

    scores = score_languages_impl(tokens)
    best_lang = "unknown"
    best_score = 0.0

    for lang, score in scores.items():
        if score > best_score:
            best_lang = lang
            best_score = score

    if best_score < 0.02:
        return "unknown"

    return best_lang

