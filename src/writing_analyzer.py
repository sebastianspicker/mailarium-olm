"""Writing style and readability analysis for emails."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WritingMetrics:
    """Readability and style metrics for a text."""

    readability_score: float | None = None  # Flesch Reading Ease (0–100)
    grade_level: float | None = None  # Flesch-Kincaid Grade Level
    avg_sentence_length: float = 0.0  # Words per sentence
    avg_word_length: float = 0.0  # Characters per word
    vocabulary_richness: float = 0.0  # Unique words / total words
    question_frequency: float = 0.0  # Fraction of sentences ending with ?
    exclamation_frequency: float = 0.0  # Fraction of sentences ending with !
    formality_score: float = 0.0  # Ratio of long words (>6 chars)
    word_count: int = 0
    sentence_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "readability_score": self.readability_score,
            "grade_level": self.grade_level,
            "avg_sentence_length": round(self.avg_sentence_length, 2),
            "avg_word_length": round(self.avg_word_length, 2),
            "vocabulary_richness": round(self.vocabulary_richness, 4),
            "question_frequency": round(self.question_frequency, 4),
            "exclamation_frequency": round(self.exclamation_frequency, 4),
            "formality_score": round(self.formality_score, 4),
            "word_count": self.word_count,
            "sentence_count": self.sentence_count,
        }


_SENTENCE_SPLIT_RE = re.compile(r"(?<!\.)\.(?!\.)\s+|[!?]+\s+|(?<!\.)\.(?!\.)$|[!?]+$")
_WORD_RE = re.compile(r"\b[a-zA-Z]+\b")


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    if not text:
        return []
    parts = _SENTENCE_SPLIT_RE.split(text.strip())
    return [s.strip() for s in parts if s and s.strip()]


def _get_words(text: str) -> list[str]:
    """Extract words from text."""
    return _WORD_RE.findall(text.lower())


class WritingAnalyzer:
    """Analyze writing style and readability of email texts."""

    def __init__(self):
        self._textstat = None
        self._textstat_checked = False

    def _get_textstat(self):
        """Lazy-load textstat library."""
        if self._textstat_checked:
            return self._textstat
        self._textstat_checked = True
        try:
            import textstat

            self._textstat = textstat
        except ImportError:
            logger.debug("textstat not installed, using basic metrics only")
            self._textstat = None
        return self._textstat

    def analyze_text(self, text: str) -> WritingMetrics:
        """Analyze a single text for readability and style metrics.

        Args:
            text: Text to analyze.

        Returns:
            WritingMetrics with computed values.
        """
        if not text or not text.strip():
            return WritingMetrics()

        words = _get_words(text)
        if not words:
            return WritingMetrics()

        word_count = len(words)
        unique_words = len(set(words))
        sentences = _split_sentences(text)
        sentence_count = max(len(sentences), 1)

        # Average sentence length
        avg_sentence_length = word_count / sentence_count

        # Average word length
        total_chars = sum(len(w) for w in words)
        avg_word_length = total_chars / word_count if word_count else 0.0

        # Vocabulary richness (type-token ratio)
        vocabulary_richness = unique_words / word_count if word_count else 0.0

        # Question and exclamation frequency
        question_count = text.count("?")
        exclamation_count = text.count("!")
        question_frequency = question_count / sentence_count
        exclamation_frequency = exclamation_count / sentence_count

        # Formality: ratio of long words (>6 characters)
        long_words = sum(1 for w in words if len(w) > 6)
        formality_score = long_words / word_count if word_count else 0.0

        # Readability via textstat (if available)
        readability_score = None
        grade_level = None
        ts = self._get_textstat()
        if ts and word_count >= 10:
            try:
                readability_score = round(ts.flesch_reading_ease(text), 1)
                grade_level = round(ts.flesch_kincaid_grade(text), 1)
            except Exception:
                logger.debug("textstat scoring failed", exc_info=True)

        return WritingMetrics(
            readability_score=readability_score,
            grade_level=grade_level,
            avg_sentence_length=avg_sentence_length,
            avg_word_length=avg_word_length,
            vocabulary_richness=vocabulary_richness,
            question_frequency=question_frequency,
            exclamation_frequency=exclamation_frequency,
            formality_score=formality_score,
            word_count=word_count,
            sentence_count=sentence_count,
        )

    def analyze_texts(self, texts: list[str]) -> list[WritingMetrics]:
        """Analyze multiple texts and return their metrics.

        Args:
            texts: List of text strings.

        Returns:
            List of WritingMetrics (filtered to texts with enough content).
        """
        metrics_list = []
        for text in texts:
            if text and len(text.strip()) >= 20:
                m = self.analyze_text(text)
                if m.word_count >= 5:
                    metrics_list.append(m)
        return metrics_list

    def analyze_sender_profile(self, texts: list[str], sender_email: str = "") -> dict[str, Any]:
        """Aggregate writing metrics from a list of email texts.

        Args:
            texts: List of email body texts from a sender.
            sender_email: Sender's email address (for labeling).

        Returns:
            Aggregated writing profile dict.
        """
        metrics_list = self.analyze_texts(texts)

        if not metrics_list:
            return {}

        n = len(metrics_list)
        return {
            "sender_email": sender_email,
            "emails_analyzed": n,
            "avg_readability": _safe_avg([m.readability_score for m in metrics_list if m.readability_score is not None]),
            "avg_grade_level": _safe_avg([m.grade_level for m in metrics_list if m.grade_level is not None]),
            "avg_sentence_length": round(sum(m.avg_sentence_length for m in metrics_list) / n, 2),
            "avg_word_length": round(sum(m.avg_word_length for m in metrics_list) / n, 2),
            "avg_vocabulary_richness": round(sum(m.vocabulary_richness for m in metrics_list) / n, 4),
            "avg_formality": round(sum(m.formality_score for m in metrics_list) / n, 4),
            "total_words": sum(m.word_count for m in metrics_list),
        }


def _safe_avg(values: list[float]) -> float | None:
    """Compute average, returning None for empty lists."""
    if not values:
        return None
    return round(sum(values) / len(values), 2)
