"""Lightweight language detection using stopword frequency.

Zero dependencies - uses hardcoded stopword sets for the top 10 languages.
Achieves ~85% accuracy on texts of 50+ words.
"""

from __future__ import annotations

from .language_detector_core import (
    detect_language_impl,
    score_languages_impl,
    tokenize_impl,
)
from .language_detector_data import STOPWORDS as _STOPWORDS
from .language_detector_data import TOKEN_RE as _TOKEN_RE


def _tokenize(text: str) -> list[str]:
    """Compatibility wrapper for the extracted tokenizer helper."""
    return tokenize_impl(text)


def detect_language(text: str) -> str:
    """Detect the language of the given text.

    Args:
        text: Input text (works best with 50+ words).

    Returns:
        ISO 639-1 language code (e.g., "en", "de", "fr").
        Returns "unknown" if confidence is too low.
    """
    return detect_language_impl(text)


__all__ = [
    "_STOPWORDS",
    "_TOKEN_RE",
    "_tokenize",
    "detect_language",
    "detect_language_impl",
    "score_languages_impl",
    "tokenize_impl",
]
