"""Root database integration tests for mailbox schema version 36."""

from __future__ import annotations

import sqlite3
import unittest

from mailarium.db_schema import _SCHEMA_VERSION, init_schema
from mailarium.mailbox_store import MailboxStore

_MAILBOX_TABLES = {
    "mailbox_accounts",
    "mailbox_folders",
    "email_sources",
    "email_source_identity_history",
    "mailbox_sync_cursors",
    "mailbox_action_proposals",
    "mailbox_action_events",
    "mailbox_action_attempts",
}


class MailboxSchemaIntegrationTests(unittest.TestCase):
    def test_root_schema_initializes_mailbox_tables_at_version_36(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            init_schema(conn)
            version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            source_columns = {row[1] for row in conn.execute("PRAGMA table_info(email_sources)")}
            folder_columns = {row[1] for row in conn.execute("PRAGMA table_info(mailbox_folders)")}
        finally:
            conn.close()

        self.assertEqual(36, _SCHEMA_VERSION)
        self.assertEqual(36, version)
        self.assertLessEqual(_MAILBOX_TABLES, tables)
        self.assertIn("canonical_preexisting", source_columns)
        self.assertIn("selected", folder_columns)

    def test_version_35_database_migrates_without_rebuilding_email_tables(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            init_schema(conn)
            for table in (
                "mailbox_action_attempts",
                "mailbox_action_events",
                "mailbox_action_proposals",
                "mailbox_sync_cursors",
                "email_source_identity_history",
                "email_sources",
                "mailbox_folders",
                "mailbox_accounts",
            ):
                conn.execute(f"DROP TABLE {table}")
            conn.execute("DELETE FROM schema_version")
            conn.execute("INSERT INTO schema_version(version) VALUES(35)")
            conn.commit()

            init_schema(conn)

            version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
        self.assertEqual(36, version)
        self.assertLessEqual(_MAILBOX_TABLES, tables)

    def test_version_35_early_mailbox_schema_gains_compatibility_columns(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            init_schema(conn)
            conn.execute("DROP TABLE mailbox_action_proposals")
            conn.execute("DROP TABLE email_sources")
            conn.execute("DROP TABLE mailbox_folders")
            conn.executescript(
                """
                CREATE TABLE mailbox_folders (
                    account_id TEXT NOT NULL,
                    folder_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    display_name TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(account_id, folder_id)
                );
                CREATE TABLE email_sources (
                    account_id TEXT NOT NULL,
                    folder_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_identity TEXT NOT NULL,
                    canonical_email_uid TEXT NOT NULL DEFAULT '',
                    remote_item_id TEXT NOT NULL,
                    change_key TEXT NOT NULL DEFAULT '',
                    is_tombstone INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(account_id, source, remote_item_id)
                );
                CREATE TABLE mailbox_action_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    folder_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    target_identity TEXT NOT NULL,
                    target_change_key TEXT NOT NULL,
                    proposal_digest TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL,
                    proposer_kind TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    approved_at TEXT,
                    execution_deadline TEXT
                );
                """
            )
            conn.execute("DELETE FROM schema_version")
            conn.execute("INSERT INTO schema_version(version) VALUES(35)")
            conn.commit()

            init_schema(conn)

            proposal_columns = {row[1] for row in conn.execute("PRAGMA table_info(mailbox_action_proposals)")}
            source_columns = {row[1] for row in conn.execute("PRAGMA table_info(email_sources)")}
            folder_columns = {row[1] for row in conn.execute("PRAGMA table_info(mailbox_folders)")}
            store = MailboxStore(conn)
            store.configure_account("account", "ews")
            store.set_folders("account", {"inbox": "Inbox"}, source="ews")
            proposal = store.create_proposal(
                account_id="account",
                folder_id="inbox",
                operation="update_item",
                target_identity="item-1",
                target_change_key="ck-1",
                target={"remote_item_id": "item-1"},
                parameters={"is_read": True},
            )
        finally:
            conn.close()

        self.assertLessEqual({"target_json", "parameters_json"}, proposal_columns)
        self.assertIn("canonical_preexisting", source_columns)
        self.assertIn("selected", folder_columns)
        self.assertEqual({"remote_item_id": "item-1"}, proposal.target)
        self.assertEqual({"is_read": True}, proposal.parameters)


if __name__ == "__main__":
    unittest.main()
