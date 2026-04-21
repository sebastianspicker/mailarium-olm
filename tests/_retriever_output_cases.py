# ruff: noqa: F401,I001
"""Targeted coverage tests for src/retriever.py uncovered lines.

Each test targets a specific branch or code path identified by coverage analysis.
All tests run without GPU, real models, or network access.
"""

import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.retriever import EmailRetriever, SearchResult

# ── Helpers ────────────────────────────────────────────────────────

from .helpers.retriever_cases import _bare_retriever, _make_result


class TestSearchByThread:
    def test_empty_conversation_id_returns_empty(self):
        r = _bare_retriever()
        assert r.search_by_thread("") == []
        assert r.search_by_thread("   ") == []

    def test_raises_on_non_positive_top_k(self):
        r = _bare_retriever()
        with pytest.raises(ValueError, match="positive"):
            r.search_by_thread("conv1", top_k=0)

    def test_empty_get_returns_empty(self):
        r = _bare_retriever()
        r.collection = MagicMock()
        r.collection.get.return_value = {"ids": []}

        assert r.search_by_thread("conv1") == []

    def test_returns_results_sorted_by_date(self):
        r = _bare_retriever()
        r.collection = MagicMock()
        r.collection.get.return_value = {
            "ids": ["c1", "c2"],
            "documents": ["body1", "body2"],
            "metadatas": [
                {"uid": "u1", "date": "2024-01-02", "conversation_id": "conv1"},
                {"uid": "u2", "date": "2024-01-01", "conversation_id": "conv1"},
            ],
        }

        thread = r.search_by_thread("conv1")
        # Should be sorted by date
        assert thread[0].metadata["date"] == "2024-01-01"
        assert thread[1].metadata["date"] == "2024-01-02"

        # Verify collection.get was called with the right filter
        r.collection.get.assert_called_once()
        call_kwargs = r.collection.get.call_args
        assert call_kwargs[1]["where"] == {"conversation_id": {"$eq": "conv1"}}

    def test_deduplicates_results(self):
        r = _bare_retriever()
        r.collection = MagicMock()
        r.collection.get.return_value = {
            "ids": ["c1", "c1b", "c2"],
            "documents": ["body1", "body1b", "body2"],
            "metadatas": [
                {"uid": "u1", "date": "2024-01-01"},
                {"uid": "u1", "date": "2024-01-01"},  # duplicate
                {"uid": "u2", "date": "2024-01-02"},
            ],
        }

        thread = r.search_by_thread("conv1")
        uids = [t.metadata["uid"] for t in thread]
        assert uids == ["u1", "u2"]

    def test_sorts_thread_results_by_parsed_timestamp_not_raw_string(self):
        r = _bare_retriever()
        r.collection = MagicMock()
        r.collection.get.return_value = {
            "ids": ["c1", "c2"],
            "documents": ["body1", "body2"],
            "metadatas": [
                {"uid": "u1", "date": "Wed, 25 Jun 2025 10:52:47 +0200", "conversation_id": "conv1"},
                {"uid": "u2", "date": "2025-06-25T08:00:00+00:00", "conversation_id": "conv1"},
            ],
        }

        thread = r.search_by_thread("conv1")

        assert [item.metadata["uid"] for item in thread] == ["u2", "u1"]


class TestListSendersSqlite:
    def test_uses_sqlite_when_available(self):
        r = _bare_retriever()
        mock_db = MagicMock()
        mock_db.top_senders.return_value = [
            {"sender_name": "Alice", "sender_email": "alice@example.test", "message_count": 10},
        ]
        r._email_db = mock_db
        r._email_db_checked = True

        senders = r.list_senders(limit=5)
        assert senders == [{"name": "Alice", "email": "alice@example.test", "count": 10}]

    def test_falls_back_to_chromadb_when_sqlite_fails(self):
        r = _bare_retriever()
        mock_db = MagicMock()
        mock_db.top_senders.side_effect = RuntimeError("db error")
        r._email_db = mock_db
        r._email_db_checked = True

        # Provide a chromadb fallback collection
        class FakeCollection:
            def get(self, include, limit, offset):
                if offset == 0:
                    return {
                        "metadatas": [
                            {"uid": "u1", "sender_email": "bob@example.test", "sender_name": "Bob"},
                        ]
                    }
                return {"metadatas": []}

        r.collection = FakeCollection()

        senders = r.list_senders(limit=5)
        assert len(senders) == 1
        assert senders[0]["email"] == "bob@example.test"

    def test_rejects_too_large_limit(self):
        r = _bare_retriever()
        with pytest.raises(ValueError, match="10000"):
            r.list_senders(limit=10001)

    def test_empty_collection_returns_empty(self):
        r = _bare_retriever()

        class FakeCollection:
            def get(self, include, limit, offset):
                return {"metadatas": []}

        r.collection = FakeCollection()

        senders = r.list_senders(limit=5)
        assert senders == []


def test_list_folders_returns_folder_counts():
    r = _bare_retriever()
    r.stats = MagicMock(
        return_value={
            "folders": {"Inbox": 10, "Sent": 5},
        }
    )
    folders = r.list_folders()
    assert {"folder": "Inbox", "count": 10} in folders
    assert {"folder": "Sent", "count": 5} in folders


class TestStatsSqlite:
    def test_uses_sqlite_when_available(self):
        r = _bare_retriever()
        r.collection = MagicMock()
        r.collection.count.return_value = 100

        mock_db = MagicMock()
        mock_db.email_count.return_value = 50
        mock_db.date_range.return_value = ("2023-01-01T00:00:00", "2024-12-31T00:00:00")
        mock_db.unique_sender_count.return_value = 15
        mock_db.folder_counts.return_value = {"Inbox": 30, "Sent": 20}
        r._email_db = mock_db
        r._email_db_checked = True

        stats = r.stats()
        assert stats["total_chunks"] == 100
        assert stats["total_emails"] == 50
        assert stats["unique_senders"] == 15
        assert stats["date_range"]["earliest"] == "2023-01-01"
        assert stats["date_range"]["latest"] == "2024-12-31"
        assert stats["folders"]["Inbox"] == 30

    def test_falls_back_when_sqlite_raises(self):
        r = _bare_retriever()
        r.collection = MagicMock()
        r.collection.count.return_value = 0

        mock_db = MagicMock()
        mock_db.email_count.side_effect = RuntimeError("db error")
        r._email_db = mock_db
        r._email_db_checked = True

        stats = r.stats()
        assert stats["total_emails"] == 0

    def test_falls_back_when_sqlite_email_count_zero(self):
        r = _bare_retriever()
        r.collection = MagicMock()
        r.collection.count.return_value = 0

        mock_db = MagicMock()
        mock_db.email_count.return_value = 0
        r._email_db = mock_db
        r._email_db_checked = True

        stats = r.stats()
        assert stats["total_emails"] == 0


def test_stats_empty_collection_without_db():
    r = _bare_retriever()
    r.collection = MagicMock()
    r.collection.count.return_value = 0

    stats = r.stats()
    assert stats == {"total_chunks": 0, "total_emails": 0, "unique_senders": 0, "date_range": {}, "folders": {}}


def test_stats_chromadb_counts_unknown_uid_rows():
    r = _bare_retriever()

    class FakeCollection:
        def count(self):
            return 3

        def get(self, include, limit, offset):
            if offset == 0:
                return {
                    "metadatas": [
                        {"sender_email": "a@example.test", "date": "2023-01-01", "folder": "Inbox"},
                        {"sender_email": "b@example.test", "date": "2023-06-01", "folder": "Sent"},
                        {"sender_email": "a@example.test", "date": "2023-12-01", "folder": "Inbox"},
                    ]
                }
            return {"metadatas": []}

    r.collection = FakeCollection()

    stats = r.stats()
    # No uid or message_id => each row is an unknown_email_row
    assert stats["total_emails"] == 3
    assert stats["unique_senders"] == 2
    assert stats["folders"]["Inbox"] == 2
    assert stats["folders"]["Sent"] == 1


def test_format_results_budget_exhaustion_shows_omitted():
    r = _bare_retriever()
    # Create many results that will exceed a tiny budget
    results = [_make_result(f"c{i}", text="x" * 500, uid=f"u{i}", date=f"2024-01-{i:02d}") for i in range(1, 20)]

    output = r.format_results_for_llm(results, max_body_chars=500, max_response_tokens=100)
    assert "omitted" in output.lower() or "result" in output.lower()


def test_format_results_thread_budget_exhaustion():
    """Budget exhaustion mid-thread should stop and report omissions."""
    r = _bare_retriever()
    results = [
        _make_result("c1", text="x" * 1000, uid="u1", date="2024-01-01", conversation_id="conv1"),
        _make_result("c2", text="x" * 1000, uid="u2", date="2024-01-02", conversation_id="conv1"),
        _make_result("c3", text="x" * 1000, uid="u3", date="2024-01-03", conversation_id="conv1"),
    ]

    output = r.format_results_for_llm(results, max_body_chars=1000, max_response_tokens=50)
    # With a tiny budget, most should be omitted
    assert "omitted" in output.lower() or "tokens" in output.lower()


def test_format_results_unlimited_budget():
    r = _bare_retriever()
    results = [_make_result("c1", text="hello")]
    output = r.format_results_for_llm(results, max_response_tokens=0)
    assert "hello" in output
    assert "omitted" not in output.lower()


class TestSerializeResults:
    def test_basic_serialization(self):
        r = _bare_retriever()
        results = [_make_result("c1", text="body")]
        payload = r.serialize_results("test", results)
        assert payload["query"] == "test"
        assert payload["count"] == 1
        assert payload["total_count"] == 1
        assert payload["returned_count"] == 1
        assert payload["omitted_count"] == 0
        assert payload["results_truncated"] is False
        assert len(payload["results"]) == 1
        assert payload["results"][0]["chunk_id"] == "c1"

    def test_body_truncation(self):
        r = _bare_retriever()
        results = [_make_result("c1", text="x" * 1000)]
        payload = r.serialize_results("test", results, max_body_chars=50)
        assert len(payload["results"][0]["text"]) < 1000

    def test_token_budget_omits_results(self):
        r = _bare_retriever()
        results = [_make_result(f"c{i}", text="x" * 500, uid=f"u{i}") for i in range(50)]
        payload = r.serialize_results("test", results, max_body_chars=500, max_response_tokens=100)
        assert payload["count"] < 50
        assert payload["total_count"] == 50
        assert payload["results_truncated"] is True
        assert payload["omitted_count"] > 0
        assert "omitted" in payload["truncation_note"]

    def test_unlimited_budget_includes_all(self):
        r = _bare_retriever()
        results = [_make_result(f"c{i}", text="hello", uid=f"u{i}") for i in range(5)]
        payload = r.serialize_results("test", results, max_response_tokens=0)
        assert len(payload["results"]) == 5
        assert payload["results_truncated"] is False

    def test_no_truncation_with_zero_body_chars(self):
        r = _bare_retriever()
        text = "x" * 2000
        results = [_make_result("c1", text=text)]
        payload = r.serialize_results("test", results, max_body_chars=0)
        assert payload["results"][0]["text"] == text


def test_reset_index():
    r = _bare_retriever()
    r.collection_name = "test_coll"
    r.chromadb_path = "/tmp/test"
    r.client = MagicMock()
    new_collection = MagicMock()
    r.client.get_or_create_collection = MagicMock(return_value=new_collection)

    with patch("src.retriever.get_collection", return_value=new_collection):
        r.reset_index()
        r.client.delete_collection.assert_called_once_with("test_coll")


def test_email_db_returns_none_when_no_sqlite_path():
    r = EmailRetriever.__new__(EmailRetriever)
    r._email_db_checked = False
    r._email_db = None
    r.settings = MagicMock()
    r.settings.sqlite_path = None

    assert r.email_db is None
    assert r._email_db_checked is True


def test_email_db_returns_none_when_path_doesnt_exist():
    r = EmailRetriever.__new__(EmailRetriever)
    r._email_db_checked = False
    r._email_db = None
    r.settings = MagicMock()
    r.settings.sqlite_path = "/nonexistent/path/db.sqlite"

    assert r.email_db is None
    assert r._email_db_checked is True


def test_email_db_rechecks_when_sqlite_appears_later(tmp_path):
    r = EmailRetriever.__new__(EmailRetriever)
    r._email_db_checked = False
    r._email_db = None
    r.settings = MagicMock()
    r.settings.sqlite_path = str(tmp_path / "email_metadata.db")

    assert r.email_db is None

    db_path = Path(r.settings.sqlite_path)
    db_path.touch()

    with patch("src.email_db.EmailDatabase") as mock_db:
        assert r.email_db is mock_db.return_value

    mock_db.assert_called_once_with(str(db_path))
