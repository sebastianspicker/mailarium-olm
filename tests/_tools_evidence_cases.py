"""Shared helpers for the RF12 evidence tool test split."""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock

from src.mcp_server import _offload
from src.sanitization import sanitize_untrusted_text


class MockEmailDB:
    """In-memory email database stub with evidence and custody methods."""

    def __init__(self):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            "CREATE TABLE emails ("
            "uid TEXT PRIMARY KEY, subject TEXT, sender_email TEXT, "
            "sender_name TEXT, date TEXT, body_text TEXT, "
            "conversation_id TEXT, folder TEXT, "
            "detected_language TEXT, sentiment_label TEXT, sentiment_score REAL, "
            "ingestion_run_id TEXT)"
        )
        self.conn.execute(
            "INSERT INTO emails VALUES "
            "('uid-1', 'Budget Review', 'alice@example.com', 'Alice', "
            "'2025-06-01', 'We decided to go with vendor A.', 'conv-1', 'Inbox', "
            "'en', 'positive', 0.85, 'run-1')"
        )
        self.conn.commit()
        self._next_evidence_id = 1
        self._evidence = {}

    def get_email_full(self, uid):
        row = self.conn.execute("SELECT * FROM emails WHERE uid = ?", (uid,)).fetchone()
        return dict(row) if row else None

    def add_evidence(self, email_uid, category, key_quote, summary, relevance, notes=""):
        evidence_id = self._next_evidence_id
        self._next_evidence_id += 1
        item = {
            "id": evidence_id,
            "email_uid": email_uid,
            "category": category,
            "key_quote": key_quote,
            "summary": summary,
            "relevance": relevance,
            "notes": notes,
            "verified": True,
        }
        self._evidence[evidence_id] = item
        return item

    def get_evidence(self, evidence_id):
        return self._evidence.get(evidence_id)

    def update_evidence(self, evidence_id, **fields):
        item = self._evidence.get(evidence_id)
        if not item:
            return False
        for key, value in fields.items():
            if value is not None:
                item[key] = value
        return True

    def remove_evidence(self, evidence_id):
        return self._evidence.pop(evidence_id, None) is not None

    def list_evidence(self, category=None, min_relevance=None, email_uid=None, limit=25, offset=0):
        items = list(self._evidence.values())
        if category:
            items = [item for item in items if item["category"] == category]
        if min_relevance:
            items = [item for item in items if item["relevance"] >= min_relevance]
        if email_uid:
            items = [item for item in items if item["email_uid"] == email_uid]
        return {"items": items[offset : offset + limit], "total": len(items)}

    def search_evidence(self, query, category=None, min_relevance=None, limit=25):
        items = [
            item
            for item in self._evidence.values()
            if query.lower() in (item.get("summary", "") + item.get("key_quote", "")).lower()
        ]
        return {"items": items[:limit], "total": len(items)}

    def evidence_timeline(self, category=None, min_relevance=None, limit=25, offset=0):
        items = list(self._evidence.values())
        return items[offset : offset + limit]

    def evidence_stats(self, category=None, min_relevance=None):
        return {"total": len(self._evidence), "verified": len(self._evidence)}

    def evidence_categories(self):
        categories = {}
        for item in self._evidence.values():
            category = item["category"]
            categories[category] = categories.get(category, 0) + 1
        return [{"category": key, "count": value} for key, value in categories.items()]

    def verify_evidence_quotes(self):
        return {"total": len(self._evidence), "verified": len(self._evidence), "failed": 0}

    def get_custody_chain(self, target_type=None, target_id=None, action=None, limit=50):
        return [
            {
                "id": 1,
                "target_type": "evidence",
                "target_id": "1",
                "action": "evidence_add",
                "timestamp": "2025-06-01T00:00:00",
                "details": {"note": "added"},
                "content_hash": "abc123",
            },
        ]

    def email_provenance(self, email_uid):
        return {"email_uid": email_uid, "ingestion_run": "run-1", "custody_events": []}

    def evidence_provenance(self, evidence_id):
        return {"evidence_id": evidence_id, "source_email": "uid-1", "chain": []}

    def top_contacts(self, email, limit=5):
        return [{"email": "bob@example.com", "count": 5}]


class MockDeps:
    _email_db = MockEmailDB()

    @staticmethod
    def get_retriever():
        return MagicMock()

    @staticmethod
    def get_email_db():
        return MockDeps._email_db

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


class FakeMCP:
    def __init__(self):
        self._tools = {}

    def tool(self, name=None, annotations=None):
        def decorator(fn):
            self._tools[name] = fn
            return fn

        return decorator


def register_tools():
    from src.tools import evidence

    fake_mcp = FakeMCP()
    evidence.register(fake_mcp, MockDeps)
    return fake_mcp
