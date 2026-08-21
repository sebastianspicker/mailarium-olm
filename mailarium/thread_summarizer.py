"""Extractive summarization for email threads using TF-IDF sentence scoring."""
# pylint: disable=too-many-locals

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")
_GERMAN_STOP_WORDS = frozenset(
    {
        "aber",
        "als",
        "am",
        "an",
        "auch",
        "auf",
        "aus",
        "bei",
        "bin",
        "bis",
        "da",
        "das",
        "dass",
        "dem",
        "den",
        "der",
        "des",
        "die",
        "doch",
        "durch",
        "ein",
        "eine",
        "einer",
        "eines",
        "er",
        "es",
        "für",
        "hat",
        "hier",
        "ich",
        "im",
        "in",
        "ist",
        "ja",
        "mit",
        "nach",
        "nicht",
        "noch",
        "nur",
        "oder",
        "sie",
        "sind",
        "und",
        "vom",
        "von",
        "vor",
        "war",
        "wenn",
        "wir",
        "wird",
        "zu",
        "zum",
        "zur",
    }
)


def _tfidf_stop_words() -> list[str] | str:
    """Combine sklearn English stop words with the built-in German list, with an English fallback."""
    try:
        from sklearn.feature_extraction import text as sklearn_text

        return sorted(set(sklearn_text.ENGLISH_STOP_WORDS) | _GERMAN_STOP_WORDS)
    except ImportError:
        return "english"


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    if not text:
        return []
    # Clean up whitespace
    text = re.sub(r"\s+", " ", text).strip()
    sentences: list[str] = []
    start = 0
    for match in _WHITESPACE_RE.finditer(text):
        if match.start() > 0 and text[match.start() - 1] in ".!?" and match.end() < len(text) and text[match.end()].isupper():
            sentences.append(text[start : match.start()])
            start = match.end()
    sentences.append(text[start:])
    # Filter very short fragments
    return [s.strip() for s in sentences if len(s.strip()) > 10]


def summarize_email(text: str, max_sentences: int = 3) -> str:
    """Summarize a single email using extractive TF-IDF sentence scoring.

    Selects the most important sentences based on TF-IDF weights,
    with position bias (first and last sentences weighted higher).

    Args:
        text: Email body text.
        max_sentences: Maximum sentences in summary.

    Returns:
        Summary string of selected sentences.
    """
    if not text or not text.strip():
        return ""

    sentences = _split_sentences(text)
    if not sentences:
        return text.strip()[:500]

    if len(sentences) <= max_sentences:
        return " ".join(sentences)

    # Score sentences using TF-IDF
    scores = _score_sentences(sentences)

    _apply_email_position_bias(scores)

    # Select top sentences
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    selected = sorted(ranked[:max_sentences])  # Preserve original order

    return " ".join(sentences[i] for i in selected)


def summarize_thread(emails: list[dict], max_sentences: int = 5) -> str:
    """Summarize an email thread using extractive summarization.

    Combines all emails in the thread, scores sentences by TF-IDF
    importance, and selects the most informative ones.

    Args:
        emails: List of email dicts with 'clean_body', 'sender_name'/'sender_email',
                'date', 'subject' keys. Should be sorted chronologically.
        max_sentences: Maximum sentences in summary.

    Returns:
        Summary string.
    """
    if not emails:
        return ""

    if len(emails) == 1:
        body = emails[0].get("clean_body", "") or emails[0].get("body", "")
        return summarize_email(body, max_sentences=max_sentences)

    # Combine all email bodies
    all_sentences = _thread_sentences(emails)

    if not all_sentences:
        return ""

    if len(all_sentences) <= max_sentences:
        return " ".join(all_sentences)

    # Score all sentences
    scores = _score_sentences(all_sentences)

    _apply_thread_position_bias(scores)

    # Diversity: penalize consecutive sentences from same sender
    selected = _diverse_sentence_indices(scores, max_sentences)
    return " ".join(all_sentences[i] for i in selected)


def _apply_email_position_bias(scores: list[float]) -> None:
    """Boost scores by their sentence position in a single email."""
    n = len(scores)
    for i in range(n):
        position_weight = 1.0
        if i == 0:
            position_weight = 1.5
        elif i == n - 1:
            position_weight = 1.3
        elif i == 1:
            position_weight = 1.2
        scores[i] *= position_weight


def _apply_thread_position_bias(scores: list[float]) -> None:
    """Boost scores from the opening and latest portions of a thread."""
    n = len(scores)
    for i in range(n):
        if i < 3:  # First few sentences (thread opener)
            scores[i] *= 1.4
        elif i >= n - 3:  # Last few sentences (latest reply)
            scores[i] *= 1.3


def _thread_sentences(emails: list[dict]) -> list[str]:
    """Flatten cleaned body sentences from every message in thread order."""
    return [sentence for email in emails for sentence in _split_sentences(email.get("clean_body", "") or email.get("body", ""))]


def _diverse_sentence_indices(scores: list[float], limit: int) -> list[int]:
    """Select top-scoring sentences while avoiding adjacent selections when possible."""
    selected: list[int] = []
    used: set[int] = set()
    for index in sorted(range(len(scores)), key=lambda item: scores[item], reverse=True):
        if len(selected) >= limit:
            break
        if index - 1 not in used or index + 1 not in used:
            selected.append(index)
            used.add(index)
    return sorted(selected)


def _score_sentences(sentences: list[str]) -> list[float]:
    """Score sentences using TF-IDF.

    Falls back to simple word count scoring if sklearn is unavailable.
    """
    if not sentences:
        return []

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer

        vectorizer = TfidfVectorizer(stop_words=_tfidf_stop_words(), sublinear_tf=True)
        tfidf_matrix = vectorizer.fit_transform(sentences)
        # Score = sum of TF-IDF weights per sentence
        return [float(tfidf_matrix[i].sum()) for i in range(len(sentences))]
    except ImportError, ValueError:
        # Fallback: score by word count (longer = more informative, roughly)
        return [len(s.split()) / 20.0 for s in sentences]
