"""Provides deterministic email, result, and bare-retriever builders for cross-module bug regressions."""

from __future__ import annotations

from mailarium.retriever import EmailRetriever, SearchResult

from .helpers.email_db_builders import _make_email as make_email

__all__ = ["bare_retriever", "make_email", "make_result"]


def make_result(
    chunk_id: str = "c1",
    text: str = "body text",
    uid: str = "u1",
    date: str = "2024-01-01",
    distance: float = 0.1,
    **extra_meta,
) -> SearchResult:
    meta = {"uid": uid, "date": date, **extra_meta}
    return SearchResult(chunk_id=chunk_id, text=text, metadata=meta, distance=distance)


def bare_retriever(**attrs) -> EmailRetriever:
    retriever = EmailRetriever.__new__(EmailRetriever)
    retriever._email_db = None
    retriever._email_db_checked = True
    retriever.settings = None
    for key, value in attrs.items():
        setattr(retriever, key, value)
    return retriever
