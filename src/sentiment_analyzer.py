"""Rule-based sentiment analysis for email text.

Zero dependencies — uses keyword matching and simple heuristics.
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

    positive_count = 0
    negative_count = 0

    for i, token in enumerate(tokens):
        # Check for negation in the previous 2 words
        is_negated = False
        for j in range(max(0, i - 2), i):
            if tokens[j] in _NEGATION_WORDS:
                is_negated = True
                break

        if token in _POSITIVE_WORDS:
            if is_negated:
                negative_count += 1
            else:
                positive_count += 1
        elif token in _NEGATIVE_WORDS:
            if is_negated:
                positive_count += 1
            else:
                negative_count += 1

    total = positive_count + negative_count
    if total == 0:
        score = 0.0
    else:
        score = (positive_count - negative_count) / total

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
