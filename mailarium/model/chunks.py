"""Records exchanged between chunking and vector retrieval."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EmailChunk:
    """A single chunk ready for embedding and vector storage."""

    uid: str
    chunk_id: str
    text: str
    metadata: dict
    embedding: list[float] | None = None
