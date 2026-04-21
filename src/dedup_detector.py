"""Near-duplicate email detection using character n-gram Jaccard similarity."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .email_db import EmailDatabase

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


class DuplicateDetector:
    """Detect near-duplicate emails using character n-gram Jaccard similarity.

    Groups emails by base subject (stripped of Re:/Fwd: prefixes), then
    compares body text within groups to find duplicates.
    """

    def __init__(self, db: EmailDatabase, threshold: float = _DEFAULT_THRESHOLD):
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

            # Pre-compute n-grams for each email in the group
            ngram_cache: list[tuple[str, str, set[str]]] = []
            for uid, body in emails:
                if body and len(body.strip()) > 20:
                    ngrams = _char_ngrams(body)
                    ngram_cache.append((uid, body, ngrams))

            # Compare all pairs within the group
            for i in range(len(ngram_cache)):
                if len(duplicates) >= limit:
                    break
                for j in range(i + 1, len(ngram_cache)):
                    uid_a, _, ngrams_a = ngram_cache[i]
                    uid_b, _, ngrams_b = ngram_cache[j]
                    sim = _jaccard_similarity(ngrams_a, ngrams_b)
                    if sim >= self.threshold:
                        duplicates.append(
                            {
                                "uid_a": uid_a,
                                "uid_b": uid_b,
                                "similarity": round(sim, 4),
                                "subject": base_subject,
                            }
                        )
                        if len(duplicates) >= limit:
                            break

        return duplicates[:limit]
