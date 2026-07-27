"""Fake MCP registration and dependencies for diagnostics-tool tests."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from unittest.mock import MagicMock

from mailarium.mcp_server import _offload
from mailarium.sanitization import sanitize_untrusted_text

# ── Shared Test Infrastructure ───────────────────────────────


class SqliteConnectionOwner:
    """Own an optional SQLite test connection and close it safely."""

    conn = None

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:  # pylint: disable=broad-exception-caught
            pass


class ToolDependencyAnnotations:
    """Supply the standard offline ToolDeps annotations for test doubles."""

    offload = staticmethod(_offload)
    DB_UNAVAILABLE = json.dumps({"error": "SQLite database not available."})
    sanitize = staticmethod(sanitize_untrusted_text)

    @staticmethod
    def tool_annotations(title):
        return {"title": title}

    @staticmethod
    def write_tool_annotations(title):
        return {"title": title}

    @staticmethod
    def idempotent_write_annotations(title):
        return {"title": title}


class MockRetriever:
    """Minimal retriever stub with embedder attribute for diagnostics."""

    def __init__(self):
        """Implement the init behavior exposed by the MockRetriever test double."""
        self.embedder = MagicMock()
        self.embedder.device = "cpu"
        self.embedder._model = MagicMock()
        self.embedder.has_sparse = False
        self.embedder.runtime_summary.return_value = {
            "backend": "fake",
            "device": "cpu",
            "batch_size": 16,
            "load_mode": "local_only",
            "has_sparse": False,
        }


class MockEmailDB(SqliteConnectionOwner):
    """Test double carrying deterministic MockEmailDB state for focused unit tests."""

    def __init__(self):
        """Implement the init behavior exposed by the MockEmailDB test double."""
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def sparse_vector_count(self):
        """Implement the sparse vector count behavior exposed by the MockEmailDB test double."""
        return 42


class MockDeps(ToolDependencyAnnotations):
    """Test double carrying deterministic MockDeps state for focused unit tests."""

    _retriever = MockRetriever()
    _email_db = MockEmailDB()

    @staticmethod
    def get_retriever():
        """Implement the get retriever behavior exposed by the MockDeps test double."""
        return MockDeps._retriever

    @staticmethod
    def get_email_db():
        """Implement the get email db behavior exposed by the MockDeps test double."""
        return MockDeps._email_db


class FakeMCP:
    """Test double carrying deterministic FakeMCP state for focused unit tests."""

    def __init__(self):
        """Implement the init behavior exposed by the FakeMCP test double."""
        self._tools = {}

    def tool(self, name=None, annotations=None):
        """Implement the tool behavior exposed by the FakeMCP test double."""

        def decorator(fn):
            self._tools[name] = fn
            return fn

        return decorator


def _register():
    """Provide deterministic register behavior for focused test setup."""
    from mailarium.tools import diagnostics

    fake_mcp = FakeMCP()
    diagnostics.register(fake_mcp, MockDeps)
    return fake_mcp


def write_json_artifact(path, payload) -> None:
    """Write a deterministic JSON test artifact."""
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_diagnostics_report(path, summary) -> None:
    """Write one diagnostics QA-evaluation report."""
    write_json_artifact(path, {"summary": summary})


def standard_core_summary(**overrides):
    """Build the common core QA-evaluation summary used by specialized-report tests."""
    summary = {
        "total_cases": 10,
        "bucket_counts": {"fact_lookup": 4},
        "top_1_correctness": {"scorable": 10, "passed": 10, "failed": 0},
        "support_uid_hit_top_3": {"scorable": 10, "passed": 10, "failed": 0},
        "evidence_precision": {"scorable": 10, "average": 0.9},
        "attachment_answer_success": {"scorable": 0, "passed": 0, "failed": 0},
        "attachment_text_evidence_success": {"scorable": 0, "passed": 0, "failed": 0},
        "attachment_ocr_text_evidence_success": {"scorable": 0, "passed": 0, "failed": 0},
        "confidence_calibration_match": {"scorable": 10, "passed": 10, "failed": 0},
        "weak_evidence_explained": {"scorable": 0, "passed": 0, "failed": 0},
        "thread_group_id_match": {"scorable": 0, "passed": 0, "failed": 0},
        "thread_group_source_match": {"scorable": 0, "passed": 0, "failed": 0},
    }
    summary.update(overrides)
    return summary


def diagnostics_database(email_schema, email_rows):
    """Create a closed-by-default diagnostics DB with common segment fixtures."""
    database = SqliteConnectionOwner()
    database.conn = sqlite3.connect(":memory:", check_same_thread=False)
    database.conn.row_factory = sqlite3.Row
    database.conn.execute(f"CREATE TABLE emails ({email_schema})")
    database.conn.execute("CREATE TABLE message_segments (email_uid TEXT)")
    placeholders = ", ".join("?" for _ in email_rows[0])
    database.conn.executemany(f"INSERT INTO emails VALUES ({placeholders})", email_rows)
    database.conn.executemany("INSERT INTO message_segments VALUES (?)", [("u1",), ("u1",), ("u2",)])
    database.sparse_vector_count = lambda: 0
    return database


async def answer_task_readiness(monkeypatch, report_paths, *, prevalence_paths=None):
    """Run diagnostics with the supplied report candidates and return its readiness summary."""
    from mailarium.mcp_models import EmailAdminInput
    from mailarium.tools import diagnostics

    fn = _register()._tools["email_admin"]
    monkeypatch.setattr(diagnostics, "_qa_eval_report_candidates", lambda: report_paths)
    if prevalence_paths is not None:
        monkeypatch.setattr(diagnostics, "_inferred_thread_prevalence_candidates", lambda: prevalence_paths)
    return json.loads(await fn(EmailAdminInput(action="diagnostics")))["answer_task_readiness"]


@contextmanager
def populated_mcp_caches():
    """Temporarily seed MCP caches so mutating admin actions must clear them."""
    from mailarium import mcp_server

    original_retriever = mcp_server._retriever
    original_email_db = mcp_server._email_db
    original_retriever_lock = mcp_server._retriever_lock
    original_email_db_lock = mcp_server._email_db_lock
    try:
        mcp_server._retriever = object()
        mcp_server._email_db = object()
        mcp_server._retriever_lock = threading.Lock()
        mcp_server._email_db_lock = threading.Lock()
        yield mcp_server
    finally:
        mcp_server._retriever = original_retriever
        mcp_server._email_db = original_email_db
        mcp_server._retriever_lock = original_retriever_lock
        mcp_server._email_db_lock = original_email_db_lock
