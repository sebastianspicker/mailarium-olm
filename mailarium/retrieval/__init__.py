"""Local retrieval services with one canonical search facade."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "SearchEngine",
    "SearchRequest",
    "SearchResponse",
    "SearchResult",
]


def __getattr__(name: str) -> Any:
    """Expose facade contracts lazily to avoid config-to-policy import cycles."""
    if name == "SearchEngine":
        return getattr(import_module(".retriever", __name__), name)
    if name in {"SearchRequest", "SearchResponse", "SearchResult"}:
        return getattr(import_module(".retriever_models", __name__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
