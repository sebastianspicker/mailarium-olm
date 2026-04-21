# ruff: noqa: F401
import json
import sqlite3

import pytest
from pydantic import ValidationError

from src.config import get_settings


def _make_result(chunk_id="x", text="hello", distance=0.25, uid="uid-1", conversation_id="conv-1", date="2025-06-01"):
    from src.retriever import SearchResult

    return SearchResult(
        chunk_id=chunk_id,
        text=text,
        metadata={
            "uid": uid,
            "subject": "Hi",
            "sender_email": "a@example.com",
            "conversation_id": conversation_id,
            "date": date,
        },
        distance=distance,
    )


class _BasicRetriever:
    """Minimal dummy retriever sufficient for most tool tests."""

    def search_filtered(self, query, top_k=10, **kwargs):
        return [_make_result()]

    def serialize_results(self, query, results):
        return {
            "query": query,
            "count": len(results),
            "results": [r.to_dict() for r in results],
        }

    def format_results_for_llm(self, results):
        return "formatted results"


def _patch_search_deps(monkeypatch, retriever):
    import src.tools.search as search_mod

    class DummyDeps:
        @staticmethod
        def get_retriever():
            return retriever

        @staticmethod
        def get_email_db():
            return None

        @staticmethod
        async def offload(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        DB_UNAVAILABLE = json.dumps({"error": "SQLite database not available."})

        @staticmethod
        def sanitize(text: str) -> str:
            return text

        @staticmethod
        def tool_annotations(title: str):
            return {"title": title}

        @staticmethod
        def write_tool_annotations(title: str):
            return {"title": title}

        @staticmethod
        def idempotent_write_annotations(title: str):
            return {"title": title}

    monkeypatch.setattr(search_mod, "_deps", DummyDeps)
