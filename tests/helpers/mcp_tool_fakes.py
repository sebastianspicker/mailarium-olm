"""Provides retriever results and dependency injection doubles for MCP search-tool tests."""

import json


def _make_result(chunk_id="x", text="hello", distance=0.25, uid="uid-1", conversation_id="conv-1", date="2025-06-01"):  # pylint: disable=too-many-arguments,too-many-positional-arguments
    """Build deterministic result data without external services."""
    from mailarium.retriever import SearchResult

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
        """Return one stable result so tool tests can focus on payload shaping."""
        return [_make_result()]

    def serialize_results(self, query, results):
        """Serialize fake results with the same query/count envelope as the retriever."""
        return {
            "query": query,
            "count": len(results),
            "results": [r.to_dict() for r in results],
        }

    def format_results_for_llm(self, results):
        """Return stable formatted text without invoking model-specific formatting."""
        return "formatted results"


def _patch_search_deps(monkeypatch, retriever):
    """Inject a supplied retriever and offline-safe ToolDeps methods into the search module."""
    import mailarium.tools.search as search_mod

    monkeypatch.setattr(search_mod, "_deps", _tool_deps(retriever=retriever))


def _tool_deps(*, retriever, email_db=None, live_backend=None):
    """Create the minimal ToolDeps contract for deterministic tool tests."""

    class TestDeps:
        DB_UNAVAILABLE = json.dumps({"error": "SQLite database not available."})

        @staticmethod
        def get_retriever():
            return retriever

        @staticmethod
        def get_email_db():
            return email_db

        @staticmethod
        async def offload(fn, *args, **kwargs):
            return fn(*args, **kwargs)

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

    if live_backend is not None:
        TestDeps.live_backend = live_backend
    return TestDeps


def _patch_capturing_search_deps(monkeypatch):
    """Install a search double and return the exact forwarded-call capture."""
    captured = {}

    class CapturingRetriever(_BasicRetriever):
        def search_filtered(self, query=None, top_k=10, **kwargs):
            captured.update({"query": query, "top_k": top_k, **kwargs})
            return []

    _patch_search_deps(monkeypatch, CapturingRetriever())
    return captured


def _patch_ingest_success(monkeypatch, *, stats=None):
    """Make ingest return a stable successful-statistics payload."""
    result = {
        "emails_parsed": 1,
        "chunks_created": 1,
        "chunks_added": 1,
        "chunks_skipped": 0,
        "batches_written": 1,
        "total_in_db": 1,
        "dry_run": False,
        "elapsed_seconds": 0.1,
    }
    if stats is not None:
        result.update(stats)
    monkeypatch.setattr("mailarium.ingest.ingest", lambda **kwargs: result)
    return result


def _successful_ingest_runtime_fixture(monkeypatch, tmp_path):
    """Create an ingestable OLM fixture and stable active archive paths."""
    _patch_ingest_success(monkeypatch)
    olm_path = tmp_path / "test.olm"
    olm_path.write_text("olm", encoding="utf-8")
    return (
        olm_path,
        str(tmp_path / "active-vector-index"),
        str(tmp_path / "active.db"),
    )


def _lane_retriever(results_by_query):
    """Return a retriever whose lane calls expose deterministic search diagnostics."""

    class LaneRetriever:
        email_db = None

        def __init__(self):
            self.last_search_debug = {"used_query_expansion": False}

        def search_filtered(self, **kwargs):
            self.last_search_debug = {"executed_query": kwargs["query"], "used_query_expansion": False}
            return results_by_query[kwargs["query"]]

    return LaneRetriever()


def _assert_source_shell_message_semantics():
    """Assert the common source-shell evidence classification contract."""
    from mailarium.formatting import weak_message_semantics

    weak_message = weak_message_semantics(
        {
            "body_kind": "content",
            "body_empty_reason": "source_shell_only",
            "recovery_strategy": "source_shell_summary",
            "recovery_confidence": 0.2,
        }
    )
    assert weak_message is not None
    assert weak_message["code"] == "source_shell_only"
    assert weak_message["label"] == "Source-shell message"
    assert "visible authored text" in weak_message["explanation"]
