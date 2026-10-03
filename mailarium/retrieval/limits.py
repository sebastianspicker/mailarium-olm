"""Result limits and overfetch factors shared by the retrieval collaborators."""

from __future__ import annotations

MAX_TOP_K = 1000
MAX_FETCH_SIZE = 10_000

# Overfetch multipliers for filtered search - empirically tuned so that
# after post-retrieval filtering, dedup (many chunks map to one email),
# and reranking (which may shuffle low-scorers out), we still have enough
# candidates to fill the requested top_k without extra round-trips.
FILTER_OVERFETCH = 4  # metadata filters (and mailbox tombstones) can discard 50-75% of results
DEDUP_OVERFETCH = 2  # ~2 chunks/email on average after chunking
RERANK_OVERFETCH = 2  # reranking may demote borderline candidates
