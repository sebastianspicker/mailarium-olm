"""Rule-based sentiment analysis for email text.

Zero dependencies - uses keyword matching and simple heuristics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_POSITIVE_WORDS = {
    "thank",
    "thanks",
    "grateful",
    "appreciate",
    "great",
    "excellent",
    "wonderful",
    "perfect",
    "approved",
    "congratulations",
    "happy",
    "pleased",
    "welcome",
    "agree",
    "good",
    "fantastic",
    "amazing",
    "brilliant",
    "delighted",
    "love",
    "danke",
    "vielen",
    "positiv",
    "genehmigt",
    "erfreut",
    "zufrieden",
    "gut",
    "prima",
    "hilfreich",
}

_NEGATIVE_WORDS = {
    "unfortunately",
    "sorry",
    "problem",
    "issue",
    "urgent",
    "critical",
    "error",
    "fail",
    "failed",
    "failure",
    "complaint",
    "disappointed",
    "concerned",
    "worried",
    "delay",
    "rejected",
    "denied",
    "wrong",
    "broken",
    "unable",
    "leider",
    "problematisch",
    "kritisch",
    "fehler",
    "fehlgeschlagen",
    "beschwerde",
    "abgelehnt",
    "verweigert",
    "sorge",
    "verzögerung",
}

_NEGATION_WORDS = {
    "not",
    "no",
    "never",
    "neither",
    "nor",
    "don't",
    "doesn't",
    "didn't",
    "won't",
    "can't",
    "cannot",
    "nicht",
    "kein",
    "keine",
    "keinen",
    "keinem",
    "keiner",
    "nie",
}


@dataclass
class SentimentResult:
    """Result of sentiment analysis."""

    sentiment: str  # "positive", "negative", or "neutral"
    score: float  # -1.0 to 1.0
    positive_count: int
    negative_count: int


def _tokenize(text: str) -> list[str]:
    """Simple lowercase word tokenizer."""
    return re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)?", text.lower(), flags=re.UNICODE)


def analyze(text: str) -> SentimentResult:
    """Analyze the sentiment of the given text.

    Uses keyword matching with basic negation handling.
    Score = (positive - negative) / total_sentiment_words,
    bucketed into positive/negative/neutral.

    Args:
        text: Input text to analyze.

    Returns:
        SentimentResult with sentiment label, score, and word counts.
    """
    tokens = _tokenize(text)
    if not tokens:
        return SentimentResult(sentiment="neutral", score=0.0, positive_count=0, negative_count=0)

    positive_count, negative_count = _sentiment_counts(tokens)

    total = positive_count + negative_count
    score = 0.0 if total == 0 else (positive_count - negative_count) / total

    # Bucket into sentiment labels
    if score > 0.1:
        sentiment = "positive"
    elif score < -0.1:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    return SentimentResult(
        sentiment=sentiment,
        score=round(score, 4),
        positive_count=positive_count,
        negative_count=negative_count,
    )


def _sentiment_counts(tokens: list[str]) -> tuple[int, int]:
    """Count positive and negative sentiment tokens while applying recent negation."""
    positive_count = 0
    negative_count = 0
    for index, token in enumerate(tokens):
        polarity = _token_sentiment_polarity(token)
        if polarity == 0:
            continue
        if _has_recent_negation(tokens, index):
            polarity *= -1
        if polarity > 0:
            positive_count += 1
        else:
            negative_count += 1
    return positive_count, negative_count


def _token_sentiment_polarity(token: str) -> int:
    if token in _POSITIVE_WORDS:
        return 1
    if token in _NEGATIVE_WORDS:
        return -1
    return 0


def _has_recent_negation(tokens: list[str], index: int) -> bool:
    return any(token in _NEGATION_WORDS for token in tokens[max(0, index - 2) : index])
