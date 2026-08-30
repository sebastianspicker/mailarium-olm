"""Owned-resource lifecycle helpers for the local search engine."""

from __future__ import annotations

from typing import Any

_OWNED_RESOURCE_ATTRIBUTES = (
    "collection",
    "image_collection",
    "_email_db",
    "_embedder",
    "_reranker",
    "_late_interaction_backend",
    "_image_embedder",
    "_bm25_index",
    "_sparse_index",
)


def close_owned_resources(owner: Any) -> None:
    """Close every distinct owned resource once and clear lazy references."""
    closed: set[int] = set()
    for attribute in _OWNED_RESOURCE_ATTRIBUTES:
        resource = getattr(owner, attribute, None)
        if resource is not None and id(resource) not in closed:
            closed.add(id(resource))
            close = getattr(resource, "close", None)
            if callable(close):
                close()
        if attribute.startswith("_"):
            setattr(owner, attribute, None)
