"""Near-duplicate email detection using character n-gram Jaccard similarity."""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Iterable, Iterator
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
    union = len(set_a) + len(set_b) - intersection
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
    if limit <= 0 or threshold > 1:
        return duplicates
    candidate_rows: Iterable[tuple[int, Iterable[int]]]
    if threshold <= 0 or not math.isfinite(threshold):
        candidate_rows = ((i, range(i + 1, len(ngram_cache))) for i in range(len(ngram_cache)))
    else:
        candidate_rows = _overlap_candidate_rows(ngram_cache, threshold)

    for i, candidate_indexes in candidate_rows:
        email_a = ngram_cache[i]
        for j in candidate_indexes:
            email_b = ngram_cache[j]
            duplicate = _matching_pair(email_a, email_b, base_subject, threshold)
            if duplicate is None:
                continue
            duplicates.append(duplicate)
            if len(duplicates) >= limit:
                return duplicates

    return duplicates


def _can_reach_jaccard(size_a: int, size_b: int, overlap: int, threshold: float) -> bool:
    """Return whether pair cardinalities and overlap can meet the cutoff."""
    if size_a == 0 or size_b == 0:
        return size_a == size_b
    union = size_a + size_b - overlap
    return overlap / union >= threshold


def _prefixes(ngram_cache: list[tuple[str, str, set[str]]], threshold: float) -> list[list[str]]:
    """Return each row's rarest `|A| - ceil(t*|A|) + 1` n-grams (exact Jaccard prefix filter)."""
    freq: dict[str, int] = {}
    for _uid, _body, ngrams in ngram_cache:
        for ngram in ngrams:
            freq[ngram] = freq.get(ngram, 0) + 1
    prefixes = []
    for _uid, _body, ngrams in ngram_cache:
        # The epsilon only lengthens the prefix, which stays exact.
        length = len(ngrams) - math.ceil(threshold * len(ngrams) - 1e-9) + 1
        prefixes.append(sorted(ngrams, key=lambda g: (freq[g], g))[:length])
    return prefixes


def _overlap_candidate_rows(
    ngram_cache: list[tuple[str, str, set[str]]], threshold: float
) -> Iterator[tuple[int, Iterable[int]]]:
    """Yield later indexes sharing a rare prefix n-gram and viable in size, one row at a time."""
    prefixes = _prefixes(ngram_cache, threshold)
    postings: dict[str, list[int]] = {}
    for index, prefix in enumerate(prefixes):
        for ngram in prefix:
            postings.setdefault(ngram, []).append(index)
    sizes = [len(item[2]) for item in ngram_cache]
    for index, prefix in enumerate(prefixes):
        size_a = sizes[index]
        if size_a == 0:
            yield index, (other for other in range(index + 1, len(sizes)) if sizes[other] == 0)
            continue
        candidates = {other for ngram in prefix for other in postings[ngram] if other > index}
        yield (
            index,
            sorted(
                other for other in candidates if _can_reach_jaccard(size_a, sizes[other], min(size_a, sizes[other]), threshold)
            ),
        )


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
        groups = self.db.queries.emails_by_base_subject(min_group_size=2)

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
