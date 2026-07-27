"""Verify that browse results retain canonical mail while hiding mailbox-only tombstoned sources."""

from __future__ import annotations

import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from mailarium.db_queries_browse import BROWSE_COUNT_SQL
from mailarium.mailbox_visibility import active_mailbox_uids, filter_active_mailbox_results


class MailboxVisibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            """CREATE TABLE email_sources (
                canonical_email_uid TEXT NOT NULL,
                folder_id TEXT NOT NULL DEFAULT '',
                is_tombstone INTEGER NOT NULL,
                canonical_preexisting INTEGER NOT NULL DEFAULT 0
            )"""
        )

    def tearDown(self) -> None:
        self.conn.close()

    def test_mailbox_only_tombstone_is_hidden(self) -> None:
        self.conn.execute(
            "INSERT INTO email_sources(canonical_email_uid,is_tombstone,canonical_preexisting) VALUES('deleted',1,0)"
        )
        self.conn.execute(
            "INSERT INTO email_sources(canonical_email_uid,is_tombstone,canonical_preexisting) VALUES('active',0,0)"
        )

        visible = active_mailbox_uids(self.conn, ("deleted", "active", "local"))

        self.assertEqual({"active", "local"}, visible)

    def test_preexisting_canonical_email_survives_mailbox_tombstone(self) -> None:
        self.conn.execute(
            "INSERT INTO email_sources(canonical_email_uid,is_tombstone,canonical_preexisting) VALUES('shared',1,1)"
        )

        self.assertEqual({"shared"}, active_mailbox_uids(self.conn, ("shared",)))

    def test_any_active_source_keeps_canonical_email_visible(self) -> None:
        self.conn.executemany(
            "INSERT INTO email_sources(canonical_email_uid,is_tombstone,canonical_preexisting) VALUES(?,?,0)",
            (("copied", 1), ("copied", 0)),
        )

        results = [
            SimpleNamespace(metadata={"uid": "copied"}),
            SimpleNamespace(metadata={"uid": "missing"}),
        ]

        self.assertEqual(results, filter_active_mailbox_results(results, conn=self.conn))

    def test_default_browse_excludes_only_mailbox_owned_tombstones(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE emails (
                uid TEXT PRIMARY KEY,
                folder TEXT,
                sender_email TEXT,
                date TEXT
            );
            CREATE TABLE email_categories (email_uid TEXT, category TEXT);
            INSERT INTO emails VALUES('deleted','inbox','sender@example.test','2026-07-17');
            INSERT INTO emails VALUES('shared','inbox','sender@example.test','2026-07-17');
            INSERT INTO emails VALUES('local','archive','local@example.test','2026-07-17');
            """
        )
        self.conn.execute(
            "INSERT INTO email_sources(canonical_email_uid,is_tombstone,canonical_preexisting) VALUES('deleted',1,0)"
        )
        self.conn.execute(
            "INSERT INTO email_sources(canonical_email_uid,is_tombstone,canonical_preexisting) VALUES('shared',1,1)"
        )
        empty_filters = [None] * 11

        total = self.conn.execute(BROWSE_COUNT_SQL, empty_filters).fetchone()[0]

        self.assertEqual(2, total)

    def test_semantic_search_can_overfetch_past_public_limit_for_tombstones(self) -> None:
        from mailarium.retriever import EmailRetriever
        from mailarium.retriever_models import SearchResult

        tombstone_count = 1001
        self.conn.executemany(
            "INSERT INTO email_sources(canonical_email_uid,is_tombstone,canonical_preexisting) VALUES(?,1,0)",
            ((f"deleted-{index}",) for index in range(tombstone_count)),
        )
        ranked = [
            SearchResult(
                chunk_id=f"chunk-{index}",
                text="deleted",
                metadata={"uid": f"deleted-{index}"},
                distance=0.1,
            )
            for index in range(tombstone_count)
        ]
        live = SearchResult(
            chunk_id="live-chunk",
            text="live",
            metadata={"uid": "live"},
            distance=0.2,
        )
        ranked.append(live)

        retriever = EmailRetriever.__new__(EmailRetriever)
        retriever._email_db = SimpleNamespace(conn=self.conn)
        retriever._email_db_checked = True
        retriever.settings = SimpleNamespace(top_k=10)
        retriever._encode_query = MagicMock(return_value=[[0.1]])
        retriever._query_with_embedding = MagicMock(side_effect=lambda _embedding, n_results, where=None: ranked[:n_results])
        retriever._merge_image_results = MagicMock(side_effect=lambda _query, results, _top_k, where=None: results)

        results = EmailRetriever.search(retriever, "live message", top_k=1000)

        self.assertEqual([live], results)
        self.assertGreater(retriever._query_with_embedding.call_args.args[1], 1000)


if __name__ == "__main__":
    unittest.main()
