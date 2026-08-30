"""Near-duplicate email detection using character n-gram Jaccard similarity."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase

logger = logging.getLogger(__name__)

_DEFAULT_THRESHOLD = 0.85
_NGRAM_SIZE = 3


def _char_ngrams(text: str, n: int = _NGRAM_SIZE) -> set[str]:
    """Extract character n-grams from text."""
    cleaned = re.sub(r"\s+", " ", text.lower().strip())
    if len(cleaned) < n:
        return {cleaned} if cleaned else set()
    return {cleaned[i : i + n] for i in range(len(cleaned) - n + 1)}


def _jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Compute Jaccard similarity between two sets."""
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def _build_ngram_cache(emails: list[tuple[str, str]]) -> list[tuple[str, str, set[str]]]:
    """Build the comparable-body cache for one subject group."""
    return [(uid, body, _char_ngrams(body)) for uid, body in emails if body and len(body.strip()) > 20]


def _matching_pair(
    email_a: tuple[str, str, set[str]],
    email_b: tuple[str, str, set[str]],
    base_subject: str,
    threshold: float,
) -> dict[str, Any] | None:
    """Build a duplicate record when a pair meets the similarity cutoff."""
    uid_a, _, ngrams_a = email_a
    uid_b, _, ngrams_b = email_b
    similarity = _jaccard_similarity(ngrams_a, ngrams_b)
    if similarity < threshold:
        return None
    return {
        "uid_a": uid_a,
        "uid_b": uid_b,
        "similarity": round(similarity, 4),
        "subject": base_subject,
    }


def _find_matching_pairs(
    ngram_cache: list[tuple[str, str, set[str]]],
    base_subject: str,
    threshold: float,
    limit: int,
) -> list[dict[str, Any]]:
    """Return matching pairs from one subject group, in input pair order."""
    duplicates: list[dict[str, Any]] = []

    for i, email_a in enumerate(ngram_cache):
        for email_b in ngram_cache[i + 1 :]:
            duplicate = _matching_pair(email_a, email_b, base_subject, threshold)
            if duplicate is None:
                continue
            duplicates.append(duplicate)
            if len(duplicates) >= limit:
                return duplicates

    return duplicates


class DuplicateDetector:
    """Detect near-duplicate emails using character n-gram Jaccard similarity.

    Groups emails by base subject (stripped of Re:/Fwd: prefixes), then
    compares body text within groups to find duplicates.
    """

    def __init__(self, db: ArchiveDatabase, threshold: float = _DEFAULT_THRESHOLD):
        """Bind the email store and similarity cutoff used for duplicate candidates."""
        self.db = db
        self.threshold = threshold

    def find_duplicates(self, limit: int = 50) -> list[dict[str, Any]]:
        """Find near-duplicate email pairs.

        Args:
            limit: Maximum number of duplicate pairs to return.

        Returns:
            List of dicts: {uid_a, uid_b, similarity, subject}.
        """
        duplicates: list[dict[str, Any]] = []
        groups = self.db.emails_by_base_subject(min_group_size=2)

        for base_subject, emails in groups:
            if len(duplicates) >= limit:
                break

            ngram_cache = _build_ngram_cache(emails)
            duplicates.extend(
                _find_matching_pairs(
                    ngram_cache,
                    base_subject,
                    self.threshold,
                    limit - len(duplicates),
                )
            )

        return duplicates[:limit]
