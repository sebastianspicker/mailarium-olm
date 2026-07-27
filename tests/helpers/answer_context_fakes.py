"""Dependency double used by answer-context tests with deterministic local data."""

import json


class _AnswerContextDeps:
    """Provide injected retrieval and database collaborators to answer-context tests."""

    DB_UNAVAILABLE = json.dumps({"error": "SQLite database not available."})

    def __init__(self, retriever, db):
        self.retriever = retriever
        self.db = db

    def get_retriever(self):
        """Return the test's configured retriever instance."""
        return self.retriever

    def get_email_db(self):
        """Return the test's configured database double."""
        return self.db

    @staticmethod
    async def offload(fn, *args, **kwargs):
        """Run synchronous test doubles inline without external executors."""
        return fn(*args, **kwargs)

    @staticmethod
    def sanitize(text: str) -> str:
        """Preserve fixture text exactly for payload assertions."""
        return text

    @staticmethod
    def tool_annotations(title: str):
        """Return stable annotations expected by the MCP tool contract."""
        return {"title": title}

    @staticmethod
    def write_tool_annotations(title: str):
        """Return stable write annotations expected by the MCP tool contract."""
        return {"title": title}

    @staticmethod
    def idempotent_write_annotations(title: str):
        """Return stable idempotent-write annotations for test-only tool calls."""
        return {"title": title}
