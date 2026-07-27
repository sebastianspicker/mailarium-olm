"""Regression coverage for effective mailbox folder membership."""

from __future__ import annotations

import sqlite3
import unittest

from mailarium.db_analytics import AnalyticsMixin
from mailarium.db_queries import QueryMixin
from mailarium.db_queries_browse import BROWSE_COUNT_SQL
from mailarium.mailbox_visibility import active_source_folders, effective_source_folders
from mailarium.result_filters import apply_metadata_filters
from mailarium.retriever_models import SearchResult


class _ProjectionDB(QueryMixin, AnalyticsMixin):
    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE emails (
                uid TEXT PRIMARY KEY,
                subject TEXT,
                sender_name TEXT,
                sender_email TEXT,
                date TEXT,
                folder TEXT,
                email_type TEXT,
                has_attachments INTEGER,
                attachment_count INTEGER,
                body_length INTEGER,
                conversation_id TEXT
            );
            CREATE TABLE email_categories (email_uid TEXT, category TEXT);
            CREATE TABLE email_keywords (email_uid TEXT, keyword TEXT, score REAL);
            CREATE TABLE email_sources (
                canonical_email_uid TEXT,
                folder_id TEXT,
                is_tombstone INTEGER,
                canonical_preexisting INTEGER
            );
            """
        )

    def close(self) -> None:
        self.conn.close()

    def add_email(self, uid: str, folder: str) -> None:
        self.conn.execute(
            "INSERT INTO emails VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                uid,
                uid,
                "Sender",
                "sender@example.test",
                "2026-07-17T10:00:00",
                folder,
                "original",
                0,
                0,
                7,
                "",
            ),
        )

    def add_source(
        self,
        uid: str,
        folder: str,
        *,
        tombstone: bool = False,
        preexisting: bool = False,
    ) -> None:
        self.conn.execute(
            "INSERT INTO email_sources VALUES(?,?,?,?)",
            (uid, folder, int(tombstone), int(preexisting)),
        )


class FolderProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = _ProjectionDB()

    def tearDown(self) -> None:
        self.db.close()

    def test_active_source_folders_are_deterministic_and_exclude_tombstones(self) -> None:
        self.db.add_source("copy", "Archive")
        self.db.add_source("copy", "Inbox")
        self.db.add_source("copy", "Deleted", tombstone=True)

        self.assertEqual(
            {"copy": ("Archive", "Inbox")},
            active_source_folders(self.db.conn, ["copy"]),
        )

    def test_folder_queries_use_active_union_and_preexisting_fallback(self) -> None:
        self.db.add_email("copy", "Archive")
        self.db.add_email("preexisting", "Local")
        self.db.add_source("copy", "Inbox")
        self.db.add_source("copy", "Archive")
        self.db.add_source("copy", "Deleted", tombstone=True)
        self.db.add_source("preexisting", "Inbox", tombstone=True, preexisting=True)
        self.db.insert_keywords_batch("copy", [("keyword", 0.8)])

        inbox = self.db.list_emails_paginated(folder="Inbox")
        archive = self.db.list_emails_paginated(folder="Archive")
        local = self.db.list_emails_paginated(folder="Local")

        self.assertEqual(["copy"], [row["uid"] for row in inbox["emails"]])
        self.assertEqual(["Archive", "Inbox"], inbox["emails"][0]["source_folders"])
        self.assertEqual(["copy"], [row["uid"] for row in archive["emails"]])
        self.assertEqual(["preexisting"], [row["uid"] for row in local["emails"]])
        self.assertEqual({"Archive": 1, "Inbox": 1, "Local": 1}, self.db.folder_counts())
        self.assertEqual(
            [{"keyword": "keyword", "avg_score": 0.8, "email_count": 1}],
            self.db.top_keywords(folder="Inbox"),
        )
        self.assertEqual([], self.db.top_keywords(folder="Deleted"))

        params = [
            None,
            None,
            "Inbox",
            "Inbox",
            "Inbox",
            None,
            None,
            None,
            None,
            None,
            None,
        ]
        self.assertEqual(
            1,
            self.db.conn.execute(BROWSE_COUNT_SQL, params).fetchone()[0],
        )

    def test_semantic_filter_uses_effective_folder_projection(self) -> None:
        self.db.add_email("copy", "Archive")
        self.db.add_source("copy", "Archive")
        self.db.add_source("copy", "Inbox")
        projected = effective_source_folders(
            self.db.conn,
            {"copy": "Archive"},
        )
        result = SearchResult(
            chunk_id="copy-0",
            text="keyword",
            metadata={
                "uid": "copy",
                "folder": "Archive",
                "source_folders": projected["copy"],
            },
            distance=0.1,
        )

        self.assertEqual([result], apply_metadata_filters([result], folder="Inbox"))
        self.assertEqual([], apply_metadata_filters([result], folder="Deleted"))


if __name__ == "__main__":
    unittest.main()
