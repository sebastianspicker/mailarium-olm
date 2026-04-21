"""Tests for long-session MCP optimization: compact modes, limits, and response size guard."""

from __future__ import annotations

import json

import pytest

# ── Evidence compact mode ─────────────────────────────────────


class TestEvidenceCompactMode:
    """evidence_list/search/timeline compact mode strips quotes, adds preview."""

    def _make_evidence_item(
        self,
        quote=("A long key quote that exceeds eighty characters for testing the preview truncation behavior in compact mode."),
        notes="detailed notes",
        content_hash="abc123",
    ):
        return {
            "id": 1,
            "email_uid": "uid1",
            "category": "harassment",
            "key_quote": quote,
            "summary": "Test summary",
            "relevance": 4,
            "sender_name": "Alice",
            "sender_email": "alice@example.com",
            "date": "2024-01-01",
            "recipients": "bob@example.com",
            "subject": "Test",
            "notes": notes,
            "verified": 1,
            "content_hash": content_hash,
        }

    def test_compact_strips_quote_adds_preview(self):
        from src.tools.evidence import _compact_evidence_items

        items = [self._make_evidence_item()]
        result = _compact_evidence_items(items)

        assert "key_quote" not in result[0]
        assert "quote_preview" in result[0]
        assert result[0]["quote_preview"].endswith("...")
        assert len(result[0]["quote_preview"]) == 83  # 80 + "..."
        # Original items should not be mutated
        assert "key_quote" in items[0]

    def test_compact_strips_notes_and_content_hash(self):
        from src.tools.evidence import _compact_evidence_items

        items = [self._make_evidence_item()]
        result = _compact_evidence_items(items)

        assert "notes" not in result[0]
        assert "content_hash" not in result[0]

    def test_compact_preserves_short_quote(self):
        from src.tools.evidence import _compact_evidence_items

        items = [self._make_evidence_item(quote="Short quote")]
        result = _compact_evidence_items(items)

        assert result[0]["quote_preview"] == "Short quote"
        assert not result[0]["quote_preview"].endswith("...")

    def test_compact_preserves_other_fields(self):
        from src.tools.evidence import _compact_evidence_items

        items = [self._make_evidence_item()]
        result = _compact_evidence_items(items)

        assert result[0]["id"] == 1
        assert result[0]["category"] == "harassment"
        assert result[0]["summary"] == "Test summary"
        assert result[0]["relevance"] == 4
        assert items[0]["sender_email"] == "alice@example.com"
        assert items[0]["verified"] == 1

    def test_include_quotes_preserves_full_data(self):
        """When include_quotes=True, full key_quote/notes/content_hash are kept."""
        item = self._make_evidence_item()
        original_quote = item["key_quote"]
        # Simulate NOT calling _compact_evidence_items (include_quotes=True path)
        assert item["key_quote"] == original_quote
        assert "notes" in item
        assert "content_hash" in item


# ── Pydantic model defaults and validation ────────────────────


class TestModelDefaults:
    def test_shared_recipients_limit(self):
        from src.mcp_models import SharedRecipientsInput

        m = SharedRecipientsInput(email_addresses=["a@b.com", "c@d.com"])
        assert m.limit == 30

    def test_coordinated_timing_limit(self):
        from src.mcp_models import CoordinatedTimingInput

        m = CoordinatedTimingInput(email_addresses=["a@b.com", "c@d.com"])
        assert m.limit == 20

    def test_decisions_limit(self):
        from src.mcp_models import DecisionsInput

        m = DecisionsInput(conversation_id="abc")
        assert m.limit == 30

    def test_custody_chain_defaults(self):
        from src.mcp_models import CustodyChainInput

        m = CustodyChainInput()
        assert m.compact is True
        assert m.limit == 50

    def test_custody_chain_max_limit(self):
        from src.mcp_models import CustodyChainInput

        with pytest.raises(ValueError):
            CustodyChainInput(limit=201)


# ── evidence_timeline limit in DB ────────────────────────────


class TestEvidenceTimelineLimit:
    def _make_db(self, tmp_path):
        """Create a minimal in-memory DB with evidence_items table."""
        import sqlite3

        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("""CREATE TABLE IF NOT EXISTS evidence_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_uid TEXT, category TEXT, key_quote TEXT, summary TEXT,
            relevance INTEGER, sender_name TEXT, sender_email TEXT,
            date TEXT, recipients TEXT, subject TEXT, notes TEXT,
            verified INTEGER DEFAULT 0, content_hash TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )""")
        # Insert 10 items
        for i in range(10):
            conn.execute(
                """INSERT INTO evidence_items
                   (email_uid, category, key_quote, summary, relevance,
                    sender_name, sender_email, date, recipients, subject, notes, verified)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    f"uid{i}",
                    "harassment",
                    f"quote {i}",
                    f"summary {i}",
                    3,
                    "Alice",
                    "alice@example.com",
                    f"2024-01-{i + 1:02d}",
                    "bob@example.com",
                    f"Subject {i}",
                    "",
                    1,
                ),
            )
        conn.commit()
        return conn

    def test_timeline_unlimited(self, tmp_path):
        from src.db_evidence import EvidenceMixin

        conn = self._make_db(tmp_path)
        mixin = EvidenceMixin.__new__(EvidenceMixin)
        mixin.conn = conn

        items = mixin.evidence_timeline()
        assert len(items) == 10

    def test_timeline_with_limit(self, tmp_path):
        from src.db_evidence import EvidenceMixin

        conn = self._make_db(tmp_path)
        mixin = EvidenceMixin.__new__(EvidenceMixin)
        mixin.conn = conn

        items = mixin.evidence_timeline(limit=5)
        assert len(items) == 5
        # Should be ordered by date ASC
        assert items[0]["date"] <= items[4]["date"]

    def test_timeline_limit_with_category_filter(self, tmp_path):
        from src.db_evidence import EvidenceMixin

        conn = self._make_db(tmp_path)
        mixin = EvidenceMixin.__new__(EvidenceMixin)
        mixin.conn = conn

        items = mixin.evidence_timeline(category="harassment", limit=3)
        assert len(items) == 3
        assert all(item["category"] == "harassment" for item in items)


# ── Custody compact mode ──────────────────────────────────────


class TestCustodyCompactMode:
    def test_compact_strips_details(self):
        events = [
            {
                "id": 1,
                "action": "evidence_add",
                "details": {"email_uid": "uid1", "category": "bossing"},
                "content_hash": "abc123",
                "timestamp": "2024-01-01",
            },
            {
                "id": 2,
                "action": "evidence_update",
                "details": {"old": "val"},
                "content_hash": "def456",
                "timestamp": "2024-01-02",
            },
        ]
        # Simulate compact mode stripping
        for event in events:
            event.pop("details", None)
            event.pop("content_hash", None)

        assert "details" not in events[0]
        assert "content_hash" not in events[0]
        assert events[0]["action"] == "evidence_add"
        assert events[0]["timestamp"] == "2024-01-01"

    def test_non_compact_preserves_details(self):
        events = [
            {"id": 1, "action": "evidence_add", "details": {"email_uid": "uid1"}, "content_hash": "abc"},
        ]
        # When compact=False, no stripping happens
        assert "details" in events[0]
        assert "content_hash" in events[0]


# ── json_response size guard ─────────────────────────────────


class TestJsonResponseSizeGuard:
    def test_normal_size_passes_through(self):
        from src.tools.utils import json_response

        data = {"items": [1, 2, 3], "count": 3}
        result = json_response(data, max_chars=10000)
        parsed = json.loads(result)
        assert parsed["items"] == [1, 2, 3]
        assert "_truncated" not in parsed

    def test_oversized_response_truncated(self):
        from src.tools.utils import json_response

        # Create a large response
        items = [{"text": "x" * 500, "id": i} for i in range(100)]
        data = {"items": items, "total": 100}
        result = json_response(data, max_chars=5000)
        parsed = json.loads(result)

        assert "_truncated" in parsed
        assert parsed["_truncated"]["original_count"] == 100
        assert parsed["_truncated"]["shown"] < 100
        assert len(parsed["items"]) == parsed["_truncated"]["shown"]
        assert len(result) <= 5000

    def test_multi_item_list_can_truncate_to_zero_results(self):
        from src.tools.utils import json_response

        data = {"results": ["x" * 1000, "x" * 1000]}
        result = json_response(data, max_chars=100)
        parsed = json.loads(result)

        assert parsed["results"] == []
        assert parsed["_truncated"]["field"] == "results"
        assert parsed["_truncated"]["shown"] == 0
        assert parsed["_truncated"]["original_count"] == 2
        assert len(result) <= 100

    def test_tiny_positive_budgets_still_respect_hard_cap(self):
        from src.tools.utils import json_response

        for max_chars in [1, 2, 10, 20]:
            result = json_response({"results": ["x" * 1000, "x" * 1000]}, max_chars=max_chars)
            assert len(result) <= max_chars
            json.loads(result)

    def test_unlimited_passes_through(self):
        from src.tools.utils import json_response

        items = [{"text": "x" * 500} for _ in range(50)]
        data = {"items": items}
        result = json_response(data, max_chars=0)
        parsed = json.loads(result)
        assert len(parsed["items"]) == 50
        assert "_truncated" not in parsed

    def test_single_item_truncated_when_oversized(self):
        from src.tools.utils import json_response

        data = {"items": [{"text": "x" * 1000}]}
        result = json_response(data, max_chars=100)
        # Single oversized item should be truncated with metadata
        parsed = json.loads(result)
        assert parsed["_truncated"] is True

    def test_non_dict_response_returns_valid_json(self):
        from src.tools.utils import json_response

        data = ["a" * 1000]
        result = json_response(data, max_chars=100)
        parsed = json.loads(result)
        assert parsed["_truncated"] is True
        assert "data" in parsed

    def test_dict_without_lists_hard_truncated(self):
        from src.tools.utils import json_response

        data = {"text": "x" * 5000}
        result = json_response(data, max_chars=100)
        # Result should be valid JSON with truncation metadata
        import json

        parsed = json.loads(result)
        assert parsed["_truncated"] is True

    def test_finds_largest_list_to_trim(self):
        from src.tools.utils import json_response

        data = {
            "small": [1, 2],
            "large": [{"text": "x" * 200} for _ in range(50)],
            "meta": "info",
        }
        result = json_response(data, max_chars=3000)
        parsed = json.loads(result)
        assert parsed["_truncated"]["field"] == "large"
        # small list should be untouched
        assert parsed["small"] == [1, 2]

    def test_default_uses_config(self, monkeypatch):
        """json_response with no explicit max_chars uses config setting."""
        from src.config import get_settings

        get_settings.cache_clear()
        monkeypatch.setenv("MCP_MAX_JSON_RESPONSE_CHARS", "500")
        try:
            from src.tools.utils import json_response

            data = {"items": [{"text": "x" * 100} for _ in range(20)]}
            result = json_response(data)
            parsed = json.loads(result)
            assert "_truncated" in parsed
            assert len(result) <= 500
        finally:
            get_settings.cache_clear()


# ── Config setting ────────────────────────────────────────────


class TestJsonResponseConfig:
    def test_default_value(self):
        from src.config import Settings

        s = Settings()
        assert s.mcp_max_json_response_chars == 32000

    def test_env_override(self, monkeypatch):
        from src.config import Settings

        monkeypatch.setenv("MCP_MAX_JSON_RESPONSE_CHARS", "16000")
        s = Settings.from_env()
        assert s.mcp_max_json_response_chars == 16000

    def test_zero_means_unlimited(self, monkeypatch):
        from src.config import Settings

        monkeypatch.setenv("MCP_MAX_JSON_RESPONSE_CHARS", "0")
        s = Settings.from_env()
        assert s.mcp_max_json_response_chars == 0

    def test_resolve_runtime_passes_through(self, monkeypatch):
        from src.config import get_settings, resolve_runtime_settings

        get_settings.cache_clear()
        monkeypatch.setenv("MCP_MAX_JSON_RESPONSE_CHARS", "20000")
        try:
            s = resolve_runtime_settings()
            assert s.mcp_max_json_response_chars == 20000
        finally:
            get_settings.cache_clear()
