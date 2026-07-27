"""Verify transactional mailbox persistence, cursor synchronization, and action-proposal state transitions."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mailarium.mailbox_models import ActorKind, MailboxMessageRecord, ProposalState
from mailarium.mailbox_store import MAILBOX_SCHEMA_SQL, MailboxStore, initialize_mailbox_schema


class MailboxStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = MailboxStore(Path(self.temp.name) / "mail.sqlite")
        self.store.configure_account(
            "a",
            "ews",
            mailbox_address="mail@example.test",
            endpoint="https://ews.example.test",
            auth_mode="oauth",
            credential_ref="env:MAIL_CREDENTIAL",
            read_enabled=True,
            write_enabled=False,
        )
        self.store.set_folders("a", {"inbox": "Inbox"}, source="ews")

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def uncertain_draft_proposal(self):
        """Create an approved draft proposal and advance it to uncertain."""
        proposal = self.store.create_proposal(
            account_id="a",
            folder_id="inbox",
            operation="create_draft",
            target_identity="drafts",
            target_change_key="new",
            parameters={"subject": "subject", "body_text": "body", "recipients": ["person@example.test"]},
        )
        self.store.approve_proposal(proposal.proposal_id, approver_kind=ActorKind.HUMAN)
        claim = self.store.claim_execution(proposal.proposal_id)
        self.store.complete_execution(claim, ProposalState.UNCERTAIN)
        return proposal

    def test_schema_can_be_installed_on_existing_connection(self) -> None:
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        initialize_mailbox_schema(conn)
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("mailbox_action_proposals", names)
        self.assertIn("mailbox_action_events", MAILBOX_SCHEMA_SQL)

    def test_sources_history_tombstones_and_scoped_cursor_cas(self) -> None:
        self.store.upsert_source(
            MailboxMessageRecord(
                "a",
                "inbox",
                "ews",
                "id",
                canonical_email_uid="email-1",
                remote_item_id="remote-1",
                change_key="v1",
                metadata={"canonical_preexisting": True},
            )
        )
        self.store.set_folders("a", {"archive": "Archive"}, source="ews")
        self.store.upsert_source(
            MailboxMessageRecord(
                "a",
                "archive",
                "ews",
                "id",
                canonical_email_uid="email-1",
                remote_item_id="remote-1",
                change_key="v2",
            )
        )
        moved = self.store.conn.execute(
            "SELECT folder_id,canonical_email_uid FROM email_sources WHERE account_id='a' AND remote_item_id='remote-1'"
        ).fetchone()
        self.assertEqual(("archive", "email-1"), tuple(moved))
        self.store.tombstone_source(
            account_id="a",
            folder_id="inbox",
            source="ews",
            source_identity="id",
            change_key="v2",
        )
        self.assertEqual([], self.store.list_sources("a", "inbox"))
        self.assertEqual(1, len(self.store.list_sources("a", "inbox", include_tombstones=True)))
        tombstone = self.store.list_sources("a", "inbox", include_tombstones=True)[0]
        self.assertEqual("email-1", tombstone["canonical_email_uid"])
        self.assertEqual(1, tombstone["canonical_preexisting"])
        self.assertTrue(tombstone["metadata"]["canonical_preexisting"])
        self.assertEqual("mail@example.test", self.store.get_account("a")["mailbox_address"])
        generation = self.store.start_cursor_generation("a", "inbox", scope="items")
        self.assertEqual(
            1,
            self.store.commit_cursor(
                "a",
                "inbox",
                "watermark",
                scope="items",
                expected_generation=generation,
                expected_cursor_value="",
                completed=True,
            ),
        )
        with self.assertRaisesRegex(RuntimeError, "generation conflict"):
            self.store.commit_cursor("a", "inbox", "stale", scope="items", expected_generation=0)
        with self.assertRaisesRegex(RuntimeError, "watermark conflict"):
            self.store.commit_cursor(
                "a",
                "inbox",
                "stale",
                scope="items",
                expected_generation=generation,
                expected_cursor_value="older",
            )

    def test_stale_full_refresh_cannot_tombstone_a_newer_generation(self) -> None:
        generation_one = self.store.start_cursor_generation(
            "a",
            "inbox",
            expected_generation=0,
        )
        self.store.upsert_source(
            MailboxMessageRecord(
                "a",
                "inbox",
                "ews",
                "item",
                remote_item_id="item",
                change_key="ck-1",
                metadata={"sync_generation": generation_one},
            )
        )
        self.store.commit_cursor(
            "a",
            "inbox",
            "page-one",
            expected_generation=generation_one,
            expected_cursor_value="",
        )
        generation_two = self.store.start_cursor_generation(
            "a",
            "inbox",
            expected_generation=generation_one,
        )
        self.store.upsert_source(
            MailboxMessageRecord(
                "a",
                "inbox",
                "ews",
                "item",
                remote_item_id="item",
                change_key="ck-2",
                metadata={"sync_generation": generation_two},
            )
        )

        with self.assertRaisesRegex(RuntimeError, "generation conflict"):
            self.store.complete_full_refresh(
                "a",
                "inbox",
                "stale-complete",
                generation=generation_one,
                expected_cursor_value="page-one",
            )

        active = self.store.conn.execute(
            "SELECT is_tombstone,change_key FROM email_sources WHERE account_id='a' AND remote_item_id='item'"
        ).fetchone()
        self.assertEqual((0, "ck-2"), tuple(active))
        self.assertEqual(
            0,
            self.store.complete_full_refresh(
                "a",
                "inbox",
                "generation-two-complete",
                generation=generation_two,
                expected_cursor_value="",
            ),
        )

    def test_action_observations_survive_concurrent_full_refresh_completion(self) -> None:
        self.store.set_folders("a", {"drafts": "Drafts", "archive": "Archive"}, source="ews")
        draft_generation = self.store.start_cursor_generation("a", "drafts")
        self.store.upsert_source(
            MailboxMessageRecord(
                "a",
                "drafts",
                "ews",
                "new-draft",
                remote_item_id="new-draft",
                change_key="draft-ck",
                metadata={"proposal_id": "proposal"},
            ),
            stamp_current_generation=True,
        )

        self.assertEqual(
            0,
            self.store.complete_full_refresh(
                "a",
                "drafts",
                "draft-complete",
                generation=draft_generation,
                expected_cursor_value="",
            ),
        )
        draft = self.store.list_sources("a", "drafts")[0]
        self.assertEqual(draft_generation, draft["metadata"]["sync_generation"])

        self.store.upsert_source(
            MailboxMessageRecord(
                "a",
                "inbox",
                "ews",
                "copy-source",
                canonical_email_uid="copy-uid",
                remote_item_id="copy-source",
                change_key="source-ck",
            )
        )
        archive_generation = self.store.start_cursor_generation("a", "archive")
        self.store.record_remote_identity_change(
            account_id="a",
            source="ews",
            old_remote_item_id="copy-source",
            new_remote_item_id="copy-result",
            new_change_key="copy-ck",
            destination_folder_id="archive",
            copy=True,
        )

        self.assertEqual(
            0,
            self.store.complete_full_refresh(
                "a",
                "archive",
                "archive-complete",
                generation=archive_generation,
                expected_cursor_value="",
            ),
        )
        copied = self.store.list_sources("a", "archive")[0]
        self.assertEqual(archive_generation, copied["metadata"]["sync_generation"])

    def test_proposal_requires_different_approver_and_claim_is_single_winner(self) -> None:
        proposal = self.store.create_proposal(
            account_id="a",
            folder_id="inbox",
            operation="move_item",
            target_identity="id",
            target_change_key="ck",
            target={"id": "id"},
            parameters={
                "destination_folder_id": "archive",
                "token": "stored-exactly",
            },
        )
        self.assertEqual(
            {"destination_folder_id": "archive", "token": "stored-exactly"},
            proposal.parameters,
        )
        with self.assertRaises(PermissionError):
            self.store.approve_proposal(proposal.proposal_id, approver_kind=ActorKind.ASSISTANT)
        approved = self.store.approve_proposal(proposal.proposal_id, approver_kind=ActorKind.HUMAN)
        self.assertEqual(ProposalState.APPROVED, approved.state)
        first = self.store.claim_execution(proposal.proposal_id)
        self.assertIsNotNone(first)
        self.assertIsNone(self.store.claim_execution(proposal.proposal_id))
        outcome = self.store.complete_execution(
            first,
            ProposalState.SUCCEEDED,
            detail={"token": "do-not-store", "status": "ok"},
        )
        self.assertEqual(ProposalState.SUCCEEDED, outcome.state)
        event = self.store.conn.execute(
            "SELECT detail_json FROM mailbox_action_events WHERE proposal_id=? ORDER BY id DESC LIMIT 1",
            (proposal.proposal_id,),
        ).fetchone()[0]
        self.assertIn("[REDACTED]", event)
        self.assertNotIn("do-not-store", event)
        stored = self.store.conn.execute(
            "SELECT parameters_json FROM mailbox_action_proposals WHERE proposal_id=?",
            (proposal.proposal_id,),
        ).fetchone()[0]
        self.assertIn("stored-exactly", stored)
        retry = self.store.create_proposal(
            account_id="a",
            folder_id="inbox",
            operation="move_item",
            target_identity="retry",
            target_change_key="ck",
        )
        self.store.approve_proposal(retry.proposal_id, approver_kind=ActorKind.HUMAN)
        retry_claim = self.store.claim_execution(retry.proposal_id)
        self.store.complete_execution(retry_claim, ProposalState.RETRYABLE)
        self.assertIsNotNone(self.store.claim_execution(retry.proposal_id))

    def test_expiry_and_execution_window_are_enforced(self) -> None:
        then = datetime(2026, 1, 1, tzinfo=UTC)
        proposal = self.store.create_proposal(
            account_id="a",
            folder_id="inbox",
            operation="move_item",
            target_identity="id",
            target_change_key="ck",
            now=then,
        )
        self.assertIsNone(self.store.claim_execution(proposal.proposal_id, now=then + timedelta(hours=24)))
        self.assertEqual(
            ProposalState.EXPIRED,
            self.store.get_proposal(proposal.proposal_id).state,
        )
        proposal = self.store.create_proposal(
            account_id="a",
            folder_id="inbox",
            operation="move_item",
            target_identity="id2",
            target_change_key="ck",
            now=then,
        )
        self.store.approve_proposal(
            proposal.proposal_id,
            approver_kind=ActorKind.HUMAN,
            now=then,
        )
        self.assertIsNone(
            self.store.claim_execution(
                proposal.proposal_id,
                now=then + timedelta(minutes=15),
            )
        )
        self.assertEqual(
            ProposalState.EXPIRED,
            self.store.get_proposal(proposal.proposal_id).state,
        )

    def test_expired_execution_claim_becomes_uncertain_without_replay(self) -> None:
        then = datetime(2026, 1, 1, tzinfo=UTC)
        proposal = self.store.create_proposal(
            account_id="a",
            folder_id="inbox",
            operation="move_item",
            target_identity="claimed",
            target_change_key="ck",
            now=then,
        )
        self.store.approve_proposal(
            proposal.proposal_id,
            approver_kind=ActorKind.HUMAN,
            now=then,
        )
        self.assertIsNotNone(self.store.claim_execution(proposal.proposal_id, now=then))

        self.assertIsNone(
            self.store.claim_execution(
                proposal.proposal_id,
                now=then + timedelta(minutes=15),
            )
        )

        self.assertEqual(
            ProposalState.UNCERTAIN,
            self.store.get_proposal(proposal.proposal_id).state,
        )
        attempt = self.store.conn.execute(
            "SELECT state,completed_at FROM mailbox_action_attempts WHERE proposal_id=? ORDER BY id DESC LIMIT 1",
            (proposal.proposal_id,),
        ).fetchone()
        self.assertEqual(ProposalState.UNCERTAIN, attempt["state"])
        self.assertIsNotNone(attempt["completed_at"])

    def test_safe_terminal_intent_requires_fresh_approval_when_reproposed(self) -> None:
        then = datetime(2026, 1, 1, tzinfo=UTC)
        values = {
            "account_id": "a",
            "folder_id": "inbox",
            "operation": "move_item",
            "target_identity": "repropose",
            "target_change_key": "ck",
            "parameters": {"destination_folder_id": "archive"},
        }
        proposal = self.store.create_proposal(**values, now=then)
        self.assertIsNone(
            self.store.claim_execution(
                proposal.proposal_id,
                now=then + timedelta(hours=24),
            )
        )

        reproposed = self.store.create_proposal(
            **values,
            now=then + timedelta(hours=25),
        )

        self.assertEqual(proposal.proposal_id, reproposed.proposal_id)
        self.assertEqual(ProposalState.PENDING, reproposed.state)
        self.assertIsNone(reproposed.approved_at)
        self.assertIsNone(reproposed.execution_deadline)
        self.assertIsNone(
            self.store.claim_execution(
                reproposed.proposal_id,
                now=then + timedelta(hours=25),
            )
        )
        approved = self.store.approve_proposal(
            reproposed.proposal_id,
            approver_kind=ActorKind.HUMAN,
            now=then + timedelta(hours=25),
        )
        self.assertEqual(ProposalState.APPROVED, approved.state)

    def test_rejected_and_uncertain_intents_do_not_reopen_implicitly(self) -> None:
        then = datetime(2026, 1, 1, tzinfo=UTC)
        rejected_values = {
            "account_id": "a",
            "folder_id": "inbox",
            "operation": "delete_item",
            "target_identity": "rejected",
            "target_change_key": "ck",
        }
        rejected = self.store.create_proposal(**rejected_values, now=then)
        self.store.reject_proposal(rejected.proposal_id, actor_kind=ActorKind.HUMAN)
        self.assertEqual(
            ProposalState.REJECTED,
            self.store.create_proposal(
                **rejected_values,
                now=then + timedelta(days=2),
            ).state,
        )

        uncertain_values = {
            **rejected_values,
            "target_identity": "uncertain",
        }
        uncertain = self.store.create_proposal(**uncertain_values, now=then)
        self.store.approve_proposal(
            uncertain.proposal_id,
            approver_kind=ActorKind.HUMAN,
            now=then,
        )
        claim = self.store.claim_execution(uncertain.proposal_id, now=then)
        self.store.complete_execution(claim, ProposalState.UNCERTAIN)
        self.assertEqual(
            ProposalState.UNCERTAIN,
            self.store.create_proposal(
                **uncertain_values,
                now=then + timedelta(days=2),
            ).state,
        )

    def test_uncertain_proposal_can_be_atomically_conflicted_with_redacted_count(self) -> None:
        proposal = self.uncertain_draft_proposal()

        conflicted = self.store.conflict_uncertain_proposal(
            proposal.proposal_id,
            detail={"reason": "duplicate_correlation_matches", "matched": 2},
        )

        self.assertEqual(ProposalState.CONFLICTED, conflicted.state)
        event = self.store.conn.execute(
            "SELECT detail_json FROM mailbox_action_events WHERE proposal_id=? AND event_type=? ORDER BY id DESC LIMIT 1",
            (proposal.proposal_id, ProposalState.CONFLICTED),
        ).fetchone()
        self.assertEqual(
            {"reason": "duplicate_correlation_matches", "matched": 2},
            json.loads(event["detail_json"]),
        )

    def test_concurrent_uncertain_resolution_has_one_terminal_winner(self) -> None:
        proposal = self.uncertain_draft_proposal()
        database = str(Path(self.temp.name) / "mail.sqlite")
        barrier = threading.Barrier(2)
        outcomes: list[ProposalState] = []
        errors: list[BaseException] = []

        def resolve(*, conflict: bool) -> None:
            store = MailboxStore(database)
            try:
                barrier.wait()
                if conflict:
                    outcome = store.conflict_uncertain_proposal(
                        proposal.proposal_id,
                        detail={"reason": "duplicate_correlation_matches", "matched": 2},
                    )
                else:
                    outcome = store.reconcile_uncertain(
                        proposal.proposal_id,
                        detail={"matched": 1},
                    )
                outcomes.append(outcome.state)
            except BaseException as error:  # test records unexpected concurrent failures
                errors.append(error)
            finally:
                store.close()

        threads = [
            threading.Thread(target=resolve, kwargs={"conflict": False}),
            threading.Thread(target=resolve, kwargs={"conflict": True}),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual([], errors)
        self.assertEqual(2, len(outcomes))
        self.assertEqual(1, len(set(outcomes)))
        self.assertIn(outcomes[0], {ProposalState.SUCCEEDED, ProposalState.CONFLICTED})
        terminal_events = self.store.conn.execute(
            "SELECT COUNT(*) FROM mailbox_action_events WHERE proposal_id=? AND event_type IN (?,?)",
            (proposal.proposal_id, ProposalState.SUCCEEDED, ProposalState.CONFLICTED),
        ).fetchone()[0]
        self.assertEqual(1, terminal_events)

    def test_two_connections_have_one_execution_claim_winner(self) -> None:
        proposal = self.store.create_proposal(
            account_id="a",
            folder_id="inbox",
            operation="move_item",
            target_identity="race",
            target_change_key="ck",
        )
        self.store.approve_proposal(proposal.proposal_id, approver_kind=ActorKind.HUMAN)
        database = str(Path(self.temp.name) / "mail.sqlite")
        barrier = threading.Barrier(2)
        results: list[bool] = []
        errors: list[BaseException] = []

        def claim() -> None:
            store = MailboxStore(database)
            try:
                barrier.wait()
                results.append(store.claim_execution(proposal.proposal_id) is not None)
            except Exception as error:  # test records unexpected concurrent failures
                errors.append(error)
            finally:
                store.close()

        threads = [threading.Thread(target=claim), threading.Thread(target=claim)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual([], errors)
        self.assertEqual([False, True], sorted(results))


if __name__ == "__main__":
    unittest.main()
