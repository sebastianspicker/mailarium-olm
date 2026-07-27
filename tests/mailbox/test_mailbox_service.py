"""Service tests for trusted approval, stale-change protection, and gates."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mailarium.ews.errors import EWSAuthenticationError, EWSFaultError
from mailarium.ews.gateway import (
    EWSAttachment,
    EWSItem,
    EWSItemRef,
    EWSOperationResult,
    EWSSyncDelta,
)
from mailarium.ews.transport import EWSHTTPSSession
from mailarium.mailbox_models import MailboxMessageRecord, ProposalState
from mailarium.mailbox_runtime import MailboxRuntimePolicy
from mailarium.mailbox_service import MailboxService, build_ews_gateway
from mailarium.mailbox_store import MailboxStore


class FakeGateway:
    def __init__(self) -> None:
        self.calls = []

    def move_item(self, item_id, change_key, destination_folder_id):
        self.calls.append((item_id, change_key, destination_folder_id))
        return EWSOperationResult("MoveItem", (EWSItemRef("moved", "ck-2"),))

    def copy_item(self, item_id, change_key, destination_folder_id):
        self.calls.append((item_id, change_key, destination_folder_id))
        return EWSOperationResult("CopyItem", (EWSItemRef("copied", "copy-ck"),))

    def delete_to_deleted_items(self, item_id, change_key):
        self.calls.append((item_id, change_key, "deleteditems"))
        return EWSOperationResult("DeleteItem")

    def create_text_draft(self, subject, body_text, recipients, *, proposal_id):
        self.calls.append((subject, body_text, tuple(recipients), proposal_id))
        return EWSOperationResult("CreateItem", (EWSItemRef("draft", "draft-ck"),))

    def send_existing_draft(self, item_id, change_key, *, proposal_id):
        self.calls.append((item_id, change_key, proposal_id))
        return EWSOperationResult("SendItem")


class SyncGateway(FakeGateway):
    def sync_folder_items(self, folder_id, *, watermark, max_changes):
        return EWSSyncDelta((EWSItemRef("created", "ck"),), (), (), "watermark", False)

    def get_items(self, refs):
        return (
            EWSItem(
                "created",
                "ck",
                "Synced subject",
                sender="sender@example.test",
                body_text="Synced body",
                received_at="2026-07-17T10:00:00Z",
                internet_message_id="<synced@example.test>",
                recipients=("recipient@example.test",),
                is_read=False,
            ),
        )


class ReconcileGateway(FakeGateway):
    def __init__(self, matching_folders=()) -> None:
        super().__init__()
        self.matching_folders = set(matching_folders)

    def find_items_by_proposal_id(self, folder_id, _proposal_id):
        self.calls.append(folder_id)
        if folder_id in self.matching_folders:
            return (EWSItemRef("correlated", "ck"),)
        return ()


class PagedFullRefreshGateway(FakeGateway):
    def sync_folder_items(self, _folder_id, *, watermark, max_changes):
        self.calls.append((watermark, max_changes))
        if watermark is None:
            return EWSSyncDelta((EWSItemRef("page-1", "ck-1"),), (), (), "page-one", True)
        return EWSSyncDelta((EWSItemRef("page-2", "ck-2"),), (), (), "page-two", False)

    def get_items(self, refs):
        return tuple(
            EWSItem(
                ref.item_id,
                ref.change_key,
                ref.item_id,
                body_text=f"body {ref.item_id}",
                internet_message_id=f"<{ref.item_id}@example.test>",
            )
            for ref in refs
        )


class IncompleteGetItemGateway(FakeGateway):
    def sync_folder_items(self, _folder_id, *, watermark, max_changes):
        return EWSSyncDelta((EWSItemRef("missing", "ck"),), (), (), "unsafe", False)

    def get_items(self, _refs):
        return ()


class UnknownOutcomeGateway(FakeGateway):
    def copy_item(self, _item_id, _change_key, _destination_folder_id):
        raise TimeoutError("outcome is unknown")


class MalformedResponseGateway(FakeGateway):
    def copy_item(self, _item_id, _change_key, _destination_folder_id):
        raise EWSFaultError("MalformedResponse", "invalid EWS XML response")


class FaultGateway(FakeGateway):
    def __init__(self, code: str, *, http_status: int | None = None) -> None:
        super().__init__()
        self.code = code
        self.http_status = http_status

    def copy_item(self, _item_id, _change_key, _destination_folder_id):
        raise EWSFaultError(
            self.code,
            "redacted fixture fault",
            http_status=self.http_status,
        )


class ExpiredWatermarkGateway(FakeGateway):
    def __init__(self) -> None:
        super().__init__()
        self.sync_calls = []

    def sync_folder_items(self, _folder_id, *, watermark, max_changes):
        self.sync_calls.append((watermark, max_changes))
        if watermark:
            raise EWSFaultError("ErrorInvalidSyncStateData", "expired")
        return EWSSyncDelta((), (), (), "fresh-watermark", False)

    def get_items(self, _refs):
        return ()


class DuplicateReconcileGateway(FakeGateway):
    def __init__(self, matching_folder: str, item_ids=("correlated-one", "correlated-two")) -> None:
        super().__init__()
        self.matching_folder = matching_folder
        self.item_ids = tuple(item_ids)

    def find_items_by_proposal_id(self, folder_id, _proposal_id):
        self.calls.append(folder_id)
        if folder_id != self.matching_folder:
            return ()
        return tuple(EWSItemRef(item_id, f"ck-{index}") for index, item_id in enumerate(self.item_ids, 1))


class EmptyCreateGateway(FakeGateway):
    def create_text_draft(self, subject, body_text, recipients, *, proposal_id):
        self.calls.append((subject, body_text, tuple(recipients), proposal_id))
        return EWSOperationResult("CreateItem")


class ReturnedSendGateway(FakeGateway):
    def send_existing_draft(self, item_id, change_key, *, proposal_id):
        self.calls.append((item_id, change_key, proposal_id))
        return EWSOperationResult("SendItem", (EWSItemRef("sent", "sent-ck"),))


class NonAdvancingSyncGateway(FakeGateway):
    def sync_folder_items(self, _folder_id, *, watermark, max_changes):
        return EWSSyncDelta((), (), (), watermark, True)

    def get_items(self, _refs):
        raise AssertionError("GetItem must not run for a non-advancing sync page")


class UnparsedChangeGateway(FakeGateway):
    def sync_folder_items(self, _folder_id, *, watermark, max_changes):
        return EWSSyncDelta((), (), (), "unsafe-watermark", False, raw_change_count=1)

    def get_items(self, _refs):
        raise AssertionError("GetItem must not run for an unparsed sync change")


class ReadFlagSyncGateway(FakeGateway):
    def sync_folder_items(self, _folder_id, *, watermark, max_changes):
        return EWSSyncDelta(
            (),
            (EWSItemRef("item", "ck-2"),),
            (),
            "read-watermark",
            False,
            raw_change_count=1,
        )

    def get_items(self, _refs):
        return (EWSItem("item", "ck-2", "Read item", is_read=True),)


class AttachmentSyncGateway(FakeGateway):
    def __init__(self, items, payloads) -> None:
        super().__init__()
        self.items = tuple(items)
        self.payloads = dict(payloads)

    def sync_folder_items(self, _folder_id, *, watermark, max_changes):
        refs = tuple(EWSItemRef(item.item_id, item.change_key) for item in self.items)
        return EWSSyncDelta(refs, (), (), "attachment-watermark", False, len(refs))

    def get_items(self, _refs):
        return self.items

    def get_attachment(self, attachment_id, *, max_content_bytes):
        self.calls.append(attachment_id)
        content = self.payloads[attachment_id]
        if len(content) > max_content_bytes:
            raise ValueError("attachment exceeds supplied limit")
        return EWSAttachment(
            attachment_id,
            name=f"{attachment_id}.txt",
            size=len(content),
            content=content,
        )


class AuthenticationFailureGateway(FakeGateway):
    def move_item(self, item_id, change_key, destination_folder_id):
        raise EWSAuthenticationError("authentication rejected")


class MailboxServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = MailboxStore(Path(self.temp.name) / "mail.sqlite")
        self.gateway = FakeGateway()
        self.service = MailboxService(
            self.store,
            policy=MailboxRuntimePolicy(read_enabled=True, write_enabled=True),
            gateway_factory=lambda _account, _policy: self.gateway,
        )
        self.service.configure_account(
            account_id="account",
            mailbox_address="mailbox@example.test",
            endpoint="https://exchange.example.test/EWS/Exchange.asmx",
            auth_mode="ntlm",
            credential_ref="basic-env:EWS_USER:EWS_PASSWORD",
            folders=("inbox", "archive"),
            read_enabled=True,
            write_enabled=True,
        )
        self.store.upsert_source(
            MailboxMessageRecord(
                "account",
                "inbox",
                "ews",
                "item",
                canonical_email_uid="uid",
                remote_item_id="item",
                change_key="ck-1",
            )
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def _approved_action(
        self,
        operation: str,
        *,
        folder_id: str = "inbox",
        target_identity: str = "item",
        target_change_key: str = "ck-1",
        parameters: dict | None = None,
    ) -> dict:
        proposal = self.service.propose_action(
            account_id="account",
            folder_id=folder_id,
            operation=operation,
            target_identity=target_identity,
            target_change_key=target_change_key,
            parameters={} if parameters is None else parameters,
        )
        self.service.approve(proposal["proposal_id"])
        return proposal

    @staticmethod
    def _draft_parameters() -> dict:
        return {
            "subject": "Draft subject",
            "body_text": "Draft body",
            "recipients": ["recipient@example.test"],
        }

    def _approved_draft(self) -> dict:
        return self._approved_action(
            "create_draft",
            target_identity="",
            target_change_key="",
            parameters=self._draft_parameters(),
        )

    def _uncertain_action(self, operation: str, **kwargs) -> dict:
        proposal = self._approved_action(operation, **kwargs)
        claim = self.store.claim_execution(proposal["proposal_id"])
        self.store.complete_execution(claim, ProposalState.UNCERTAIN)
        return proposal

    def _sync_service(self, gateway, *, policy=None, persist_record=None) -> MailboxService:
        return MailboxService(
            self.store,
            db=object(),
            policy=policy or MailboxRuntimePolicy(read_enabled=True),
            gateway_factory=lambda _account, _policy: gateway,
            persist_record=persist_record or (lambda _record, **_kwargs: SimpleNamespace(indexed_chunks=0)),
        )

    def _assert_unadvanced_sync_cursor(self) -> None:
        self.assertEqual((1, ""), self.store.get_cursor("account", "inbox"))
        self.assertEqual("full_refresh", self.store.cursor_state("account", "inbox"))

    def _assert_attachment_sync_rejected(self, service, gateway, message: str, calls) -> None:
        with self.assertRaisesRegex(ValueError, message):
            service.sync(
                "account",
                folders=("inbox",),
                include_attachment_content=True,
            )
        self.assertEqual(calls, gateway.calls)
        self.assertEqual((1, ""), self.store.get_cursor("account", "inbox"))

    def _assert_conflicted_without_remote_call(self, proposal, reason: str) -> None:
        outcome = self.service.execute(proposal["proposal_id"])
        self.assertEqual("conflicted", outcome["state"])
        self.assertEqual({"reason": reason}, outcome["detail"])
        self.assertEqual([], self.gateway.calls)

    def test_cli_trusted_approval_then_execution_moves_identity(self) -> None:
        proposal = self._approved_action("move_item", parameters={"destination_folder_id": "archive"})

        outcome = self.service.execute(proposal["proposal_id"])

        self.assertEqual("succeeded", outcome["state"])
        row = self.store.conn.execute(
            "SELECT remote_item_id,folder_id,change_key FROM email_sources WHERE canonical_email_uid='uid'"
        ).fetchone()
        self.assertEqual(("moved", "archive", "ck-2"), tuple(row))

    def test_copy_is_immediately_searchable_in_both_active_source_folders(self) -> None:
        from mailarium.result_filters import apply_metadata_filters
        from mailarium.retriever import EmailRetriever
        from mailarium.retriever_models import SearchResult

        proposal = self._approved_action("copy_item", parameters={"destination_folder_id": "archive"})

        outcome = self.service.execute(proposal["proposal_id"])

        self.assertEqual("succeeded", outcome["state"])
        retriever = EmailRetriever.__new__(EmailRetriever)
        retriever._email_db = SimpleNamespace(conn=self.store.conn)
        retriever._email_db_checked = True
        candidate = SearchResult(
            chunk_id="uid__0",
            text="body",
            metadata={"uid": "uid", "folder": "inbox"},
            distance=0.1,
        )
        projected = retriever._active_mailbox_results([candidate])

        self.assertEqual(["archive", "inbox"], projected[0].metadata["source_folders"])
        self.assertEqual(projected, apply_metadata_filters(projected, folder="inbox"))
        self.assertEqual(projected, apply_metadata_filters(projected, folder="archive"))

    def test_reconfiguration_replaces_selected_folder_allowlist(self) -> None:
        self.service.configure_account(
            account_id="account",
            mailbox_address="mailbox@example.test",
            endpoint="https://exchange.example.test/EWS/Exchange.asmx",
            auth_mode="ntlm",
            credential_ref="basic-env:EWS_USER:EWS_PASSWORD",
            folders=("inbox",),
            read_enabled=True,
            write_enabled=True,
        )

        self.assertEqual(["inbox"], [row["folder_id"] for row in self.store.list_folders("account")])
        archive = self.store.conn.execute(
            "SELECT selected FROM mailbox_folders WHERE account_id='account' AND folder_id='archive'"
        ).fetchone()
        self.assertEqual(0, archive[0])

    def test_stale_change_key_conflicts_without_remote_call(self) -> None:
        proposal = self._approved_action(
            "move_item",
            target_change_key="stale",
            parameters={"destination_folder_id": "archive"},
        )

        outcome = self.service.execute(proposal["proposal_id"])

        self.assertEqual("conflicted", outcome["state"])
        self.assertEqual([], self.gateway.calls)

    def test_account_reconfiguration_conflicts_approved_intent_without_remote_call(self) -> None:
        proposal = self._approved_action("move_item", parameters={"destination_folder_id": "archive"})
        self.service.configure_account(
            account_id="account",
            mailbox_address="other-mailbox@example.test",
            endpoint="https://other-exchange.example.test/EWS/Exchange.asmx",
            auth_mode="ntlm",
            credential_ref="basic-env:EWS_USER:EWS_PASSWORD",
            folders=("inbox", "archive"),
            read_enabled=True,
            write_enabled=True,
        )

        outcome = self.service.execute(proposal["proposal_id"])

        self.assertEqual("conflicted", outcome["state"])
        self.assertEqual(
            {"reason": "account_configuration_changed"},
            outcome["detail"],
        )
        self.assertEqual([], self.gateway.calls)

    def test_missing_source_conflicts_without_remote_call(self) -> None:
        proposal = self._approved_action(
            "move_item",
            target_identity="missing",
            parameters={"destination_folder_id": "archive"},
        )

        self._assert_conflicted_without_remote_call(proposal, "source_item_missing")

    def test_source_folder_mismatch_conflicts_without_remote_call(self) -> None:
        proposal = self._approved_action("delete_item", folder_id="archive")

        self._assert_conflicted_without_remote_call(proposal, "source_item_missing")

    def test_unknown_copy_outcome_is_not_automatically_retryable(self) -> None:
        self.service.gateway_factory = lambda _account, _policy: UnknownOutcomeGateway()
        proposal = self._approved_action("copy_item", parameters={"destination_folder_id": "archive"})

        first = self.service.execute(proposal["proposal_id"])
        second = self.service.execute(proposal["proposal_id"])

        self.assertEqual("uncertain", first["state"])
        self.assertEqual("uncertain", second["state"])
        self.assertFalse(second["executed"])

    def test_malformed_response_after_dispatch_is_uncertain(self) -> None:
        self.service.gateway_factory = lambda _account, _policy: MalformedResponseGateway()
        proposal = self._approved_action("copy_item", parameters={"destination_folder_id": "archive"})

        outcome = self.service.execute(proposal["proposal_id"])

        self.assertEqual("uncertain", outcome["state"])
        self.assertEqual("MalformedResponse", outcome["detail"]["code"])
        self.assertEqual("transport_outcome_unknown", outcome["detail"]["reason"])

    def test_known_ews_conflict_is_conflicted(self) -> None:
        self.service.gateway_factory = lambda _account, _policy: FaultGateway("ErrorIrresolvableConflict")
        proposal = self._approved_action("copy_item", parameters={"destination_folder_id": "archive"})

        outcome = self.service.execute(proposal["proposal_id"])

        self.assertEqual("conflicted", outcome["state"])
        self.assertEqual("ErrorIrresolvableConflict", outcome["detail"]["code"])

    def test_known_ews_transient_fault_is_retryable(self) -> None:
        self.service.gateway_factory = lambda _account, _policy: FaultGateway("ErrorServerBusy")
        proposal = self._approved_action("copy_item", parameters={"destination_folder_id": "archive"})

        outcome = self.service.execute(proposal["proposal_id"])

        self.assertEqual("retryable", outcome["state"])
        self.assertEqual("ErrorServerBusy", outcome["detail"]["code"])

    def test_unclassified_http_503_fault_is_uncertain(self) -> None:
        self.service.gateway_factory = lambda _account, _policy: FaultGateway(
            "ErrorAccessDenied",
            http_status=503,
        )
        proposal = self._approved_action("copy_item", parameters={"destination_folder_id": "archive"})

        outcome = self.service.execute(proposal["proposal_id"])

        self.assertEqual("uncertain", outcome["state"])
        self.assertEqual(503, outcome["detail"]["http_status"])

    def test_local_gateway_preflight_failure_does_not_consume_approval(self) -> None:
        self.service.gateway_factory = lambda _account, _policy: (_ for _ in ()).throw(RuntimeError("credentials unavailable"))
        proposal = self._approved_action("move_item", parameters={"destination_folder_id": "archive"})

        with self.assertRaisesRegex(RuntimeError, "credentials unavailable"):
            self.service.execute(proposal["proposal_id"])

        self.assertEqual(
            ProposalState.APPROVED,
            self.store.get_proposal(proposal["proposal_id"]).state,
        )

    def test_authentication_rejection_is_explicitly_retryable(self) -> None:
        self.service.gateway_factory = lambda _account, _policy: AuthenticationFailureGateway()
        proposal = self._approved_action("move_item", parameters={"destination_folder_id": "archive"})

        outcome = self.service.execute(proposal["proposal_id"])

        self.assertEqual("retryable", outcome["state"])
        self.assertEqual("EWSAuthenticationError", outcome["detail"]["reason"])

    def test_operation_allowlist_rejects_hard_delete_shape(self) -> None:
        with self.assertRaises(ValueError):
            self.service.propose_action(
                account_id="account",
                folder_id="inbox",
                operation="delete_item",
                target_identity="item",
                target_change_key="ck-1",
                parameters={"delete_type": "HardDelete"},
            )

        with self.assertRaisesRegex(ValueError, "recipients must be a list"):
            self.service.propose_action(
                account_id="account",
                folder_id="inbox",
                operation="create_draft",
                target_identity="",
                target_change_key="",
                parameters={
                    "subject": "Subject",
                    "body_text": "Body",
                    "recipients": "recipient@example.test",
                },
            )

    def test_delete_success_tombstones_source_without_returned_item_id(self) -> None:
        proposal = self._approved_action("delete_item")

        outcome = self.service.execute(proposal["proposal_id"])

        self.assertEqual("succeeded", outcome["state"])
        row = self.store.conn.execute(
            "SELECT is_tombstone,canonical_email_uid FROM email_sources WHERE account_id='account' AND remote_item_id='item'"
        ).fetchone()
        self.assertEqual((1, "uid"), tuple(row))

    def test_create_then_send_tracks_and_tombstones_draft_identity(self) -> None:
        created = self._approved_draft()

        create_outcome = self.service.execute(created["proposal_id"])

        self.assertEqual("succeeded", create_outcome["state"])
        draft = self.store.conn.execute(
            "SELECT folder_id,change_key,is_tombstone FROM email_sources WHERE account_id='account' AND remote_item_id='draft'"
        ).fetchone()
        self.assertEqual(("drafts", "draft-ck", 0), tuple(draft))
        self.assertNotIn(
            "drafts",
            {row["folder_id"] for row in self.store.list_folders("account")},
        )
        send = self._approved_action(
            "send_item",
            folder_id="drafts",
            target_identity="draft",
            target_change_key="draft-ck",
        )

        send_outcome = self.service.execute(send["proposal_id"])

        self.assertEqual("succeeded", send_outcome["state"])
        tombstone = self.store.conn.execute(
            "SELECT is_tombstone FROM email_sources WHERE account_id='account' AND remote_item_id='draft'"
        ).fetchone()
        self.assertEqual(1, tombstone[0])

    def test_send_result_does_not_add_sent_items_to_selected_folders(self) -> None:
        self.store.set_folders("account", {"drafts": "drafts"}, source="ews", selected=False)
        self.store.upsert_source(
            MailboxMessageRecord(
                "account",
                "drafts",
                "ews",
                "draft",
                remote_item_id="draft",
                change_key="draft-ck",
            )
        )
        self.service.gateway_factory = lambda _account, _policy: ReturnedSendGateway()
        proposal = self._approved_action(
            "send_item",
            folder_id="drafts",
            target_identity="draft",
            target_change_key="draft-ck",
        )

        outcome = self.service.execute(proposal["proposal_id"])

        self.assertEqual("succeeded", outcome["state"])
        sent_folder = self.store.conn.execute(
            "SELECT selected FROM mailbox_folders WHERE account_id='account' AND folder_id='sentitems'"
        ).fetchone()
        self.assertEqual(0, sent_folder[0])
        self.assertNotIn(
            "sentitems",
            {row["folder_id"] for row in self.store.list_folders("account")},
        )

    def test_create_without_result_identity_is_uncertain(self) -> None:
        self.service.gateway_factory = lambda _account, _policy: EmptyCreateGateway()
        proposal = self._approved_draft()

        outcome = self.service.execute(proposal["proposal_id"])

        self.assertEqual("uncertain", outcome["state"])
        self.assertIsNone(
            self.store.conn.execute("SELECT 1 FROM email_sources WHERE account_id='account' AND folder_id='drafts'").fetchone()
        )

    def test_sync_projects_full_item_and_commits_completed_watermark(self) -> None:
        records = []
        gateway = SyncGateway()
        service = self._sync_service(
            gateway,
            persist_record=lambda record, **_kwargs: records.append(record) or SimpleNamespace(indexed_chunks=0),
        )

        result = service.sync("account", folders=("inbox",))

        self.assertEqual(1, result["created"])
        self.assertEqual("Synced body", records[0].body_text)
        self.assertEqual((1, "watermark"), self.store.get_cursor("account", "inbox"))
        state = self.store.conn.execute(
            "SELECT state FROM mailbox_sync_cursors WHERE account_id='account' AND folder_id='inbox'"
        ).fetchone()[0]
        self.assertEqual("completed", state)

    def test_expired_watermark_starts_one_fresh_generation(self) -> None:
        generation = self.store.start_cursor_generation("account", "inbox", scope="items")
        self.store.commit_cursor(
            "account",
            "inbox",
            "expired-watermark",
            scope="items",
            expected_generation=generation,
            expected_cursor_value="",
            completed=True,
        )
        gateway = ExpiredWatermarkGateway()
        service = self._sync_service(gateway)

        result = service.sync("account", folders=("inbox",))

        self.assertTrue(result["folders"]["inbox"]["complete"])
        self.assertEqual("expired-watermark", gateway.sync_calls[0][0])
        self.assertIsNone(gateway.sync_calls[1][0])
        self.assertEqual((generation + 1, "fresh-watermark"), self.store.get_cursor("account", "inbox"))

    def test_uncertain_send_reconciles_only_against_sent_items(self) -> None:
        proposal = self._uncertain_action("send_item")
        drafts_only = ReconcileGateway({"drafts"})
        self.service.gateway_factory = lambda _account, _policy: drafts_only

        first = self.service.reconcile(proposal["proposal_id"])

        self.assertFalse(first["reconciled"])
        self.assertEqual(["sentitems"], drafts_only.calls)
        sent = ReconcileGateway({"sentitems"})
        self.service.gateway_factory = lambda _account, _policy: sent

        second = self.service.reconcile(proposal["proposal_id"])

        self.assertTrue(second["reconciled"])
        source = self.store.conn.execute(
            "SELECT is_tombstone FROM email_sources WHERE account_id='account' AND remote_item_id='item'"
        ).fetchone()
        self.assertEqual(1, source[0])

    def test_uncertain_create_reconciliation_tracks_the_correlated_draft(self) -> None:
        proposal = self._uncertain_action(
            "create_draft",
            target_identity="",
            target_change_key="",
            parameters=self._draft_parameters(),
        )
        self.service.gateway_factory = lambda _account, _policy: ReconcileGateway({"drafts"})

        outcome = self.service.reconcile(proposal["proposal_id"])

        self.assertTrue(outcome["reconciled"])
        source = self.store.conn.execute(
            "SELECT folder_id,remote_item_id,change_key,is_tombstone FROM email_sources "
            "WHERE account_id='account' AND remote_item_id='correlated'"
        ).fetchone()
        self.assertEqual(("drafts", "correlated", "ck", 0), tuple(source))
        self.assertNotIn(
            "drafts",
            {row["folder_id"] for row in self.store.list_folders("account")},
        )

    def test_duplicate_create_correlation_conflicts_without_local_projection(self) -> None:
        proposal = self._uncertain_action(
            "create_draft",
            target_identity="",
            target_change_key="",
            parameters=self._draft_parameters(),
        )
        self.service.gateway_factory = lambda _account, _policy: DuplicateReconcileGateway("drafts")

        outcome = self.service.reconcile(proposal["proposal_id"])

        self.assertEqual("conflicted", outcome["state"])
        self.assertFalse(outcome["reconciled"])
        self.assertEqual("duplicate_correlation_matches", outcome["detail"]["reason"])
        self.assertEqual(2, outcome["detail"]["matched"])
        projected = self.store.conn.execute(
            "SELECT remote_item_id FROM email_sources WHERE account_id='account' AND folder_id='drafts'"
        ).fetchall()
        self.assertEqual([], projected)

    def test_duplicate_send_correlation_conflicts_without_tombstoning_source(self) -> None:
        proposal = self._uncertain_action("send_item")
        self.service.gateway_factory = lambda _account, _policy: DuplicateReconcileGateway("sentitems")

        outcome = self.service.reconcile(proposal["proposal_id"])

        self.assertEqual("conflicted", outcome["state"])
        source = self.store.conn.execute(
            "SELECT is_tombstone FROM email_sources WHERE account_id='account' AND remote_item_id='item'"
        ).fetchone()
        self.assertEqual(0, source[0])

    def test_repeated_identical_correlation_id_reconciles_once(self) -> None:
        proposal = self._uncertain_action(
            "create_draft",
            target_identity="",
            target_change_key="",
            parameters=self._draft_parameters(),
        )
        self.service.gateway_factory = lambda _account, _policy: DuplicateReconcileGateway("drafts", ("correlated", "correlated"))

        outcome = self.service.reconcile(proposal["proposal_id"])

        self.assertEqual("succeeded", outcome["state"])
        self.assertTrue(outcome["reconciled"])
        count = self.store.conn.execute(
            "SELECT COUNT(*) FROM email_sources WHERE account_id='account' AND remote_item_id='correlated'"
        ).fetchone()[0]
        self.assertEqual(1, count)

    def test_capped_full_refresh_preserves_prior_pages_and_tombstones_stale_rows(self) -> None:
        gateway = PagedFullRefreshGateway()

        def persist(record, **_kwargs):
            self.store.upsert_source(record)
            return SimpleNamespace(indexed_chunks=0)

        service = self._sync_service(
            gateway,
            policy=MailboxRuntimePolicy(read_enabled=True, max_sync_items=1),
            persist_record=persist,
        )

        first = service.sync("account", folders=("inbox",))

        self.assertFalse(first["folders"]["inbox"]["complete"])
        self.assertEqual(1, gateway.calls[0][1])
        self.assertEqual("full_refresh", self.store.cursor_state("account", "inbox"))

        second = service.sync("account", folders=("inbox",))

        self.assertTrue(second["folders"]["inbox"]["complete"])
        active = {row["remote_item_id"] for row in self.store.list_sources("account", "inbox")}
        self.assertEqual({"page-1", "page-2"}, active)
        stale = self.store.conn.execute("SELECT is_tombstone FROM email_sources WHERE remote_item_id='item'").fetchone()
        self.assertEqual(1, stale[0])

    def test_incomplete_get_item_response_does_not_advance_cursor(self) -> None:
        service = self._sync_service(IncompleteGetItemGateway())

        with self.assertRaisesRegex(RuntimeError, "every synchronized item"):
            service.sync("account", folders=("inbox",))

        self._assert_unadvanced_sync_cursor()

    def test_nonadvancing_partial_sync_page_stops_before_get_item(self) -> None:
        service = self._sync_service(NonAdvancingSyncGateway())

        with self.assertRaisesRegex(RuntimeError, "watermark did not advance"):
            service.sync("account", folders=("inbox",))

        self._assert_unadvanced_sync_cursor()

    def test_unparsed_sync_change_does_not_advance_cursor(self) -> None:
        service = self._sync_service(UnparsedChangeGateway())

        with self.assertRaisesRegex(RuntimeError, "unsupported or unparsed"):
            service.sync("account", folders=("inbox",))

        self._assert_unadvanced_sync_cursor()

    def test_read_flag_change_refreshes_triage_state(self) -> None:
        def persist(record, **_kwargs):
            self.store.upsert_source(record)
            return SimpleNamespace(indexed_chunks=0)

        service = self._sync_service(ReadFlagSyncGateway(), persist_record=persist)

        result = service.sync("account", folders=("inbox",))

        self.assertTrue(result["folders"]["inbox"]["complete"])
        self.assertEqual([], service.triage("account", folders=("inbox",)))
        source = self.store.list_sources("account", "inbox")[0]
        self.assertTrue(source["metadata"]["is_read"])

    def test_attachment_count_limit_rejects_before_content_calls(self) -> None:
        attachments = tuple(EWSAttachment(f"attachment-{index}", size=1) for index in range(2))
        gateway = AttachmentSyncGateway(
            (EWSItem("attachment-item", "ck", "Attachments", attachments=attachments),),
            {"attachment-0": b"a", "attachment-1": b"b"},
        )
        service = self._sync_service(
            gateway,
            policy=MailboxRuntimePolicy(
                read_enabled=True,
                attachment_content_enabled=True,
                max_attachments_per_item=1,
            ),
        )

        self._assert_attachment_sync_rejected(service, gateway, "attachment-count", [])

    def test_attachment_aggregate_limit_stops_before_next_content_call(self) -> None:
        attachments = (
            EWSAttachment("attachment-0", size=3),
            EWSAttachment("attachment-1", size=3),
        )
        gateway = AttachmentSyncGateway(
            (EWSItem("attachment-item", "ck", "Attachments", attachments=attachments),),
            {"attachment-0": b"abc", "attachment-1": b"def"},
        )
        service = self._sync_service(
            gateway,
            policy=MailboxRuntimePolicy(
                read_enabled=True,
                attachment_content_enabled=True,
                max_attachment_bytes=4,
                max_attachment_total_bytes_per_item=5,
            ),
        )

        self._assert_attachment_sync_rejected(service, gateway, "aggregate byte", ["attachment-0"])

    def test_attachment_per_sync_budget_spans_items(self) -> None:
        items = tuple(
            EWSItem(
                f"item-{index}",
                f"ck-{index}",
                "Attachment",
                attachments=(EWSAttachment(f"attachment-{index}", size=3),),
            )
            for index in range(2)
        )
        gateway = AttachmentSyncGateway(
            items,
            {"attachment-0": b"abc", "attachment-1": b"def"},
        )
        service = self._sync_service(
            gateway,
            policy=MailboxRuntimePolicy(
                read_enabled=True,
                attachment_content_enabled=True,
                max_attachment_bytes=4,
                max_attachment_total_bytes_per_item=10,
                max_attachment_total_bytes_per_sync=5,
            ),
        )

        self._assert_attachment_sync_rejected(service, gateway, "aggregate byte", ["attachment-0"])

    def test_readiness_rejects_any_invalid_account_configuration(self) -> None:
        self.store.conn.execute("UPDATE mailbox_accounts SET auth_mode='invalid' WHERE account_id='account'")
        self.store.conn.commit()

        with patch(
            "mailarium.mailbox_service._credential_environment_available",
            return_value=True,
        ):
            readiness = self.service.readiness("account")

        self.assertFalse(readiness["offline_ready"])
        self.assertFalse(readiness["read_ready"])
        self.assertEqual("Offline verified; live EWS writes unverified.", readiness["status"])

    def test_default_gateway_preflights_ntlm_dependencies(self) -> None:
        account = self.store.get_account("account")
        with (
            patch(
                "mailarium.mailbox_service.resolve_external_credentials",
                return_value=("user", "password"),
            ),
            patch.object(EWSHTTPSSession, "preflight", autospec=True) as preflight,
        ):
            gateway = build_ews_gateway(
                account,
                MailboxRuntimePolicy(read_enabled=True, write_enabled=True),
            )

        self.assertIsNotNone(gateway)
        preflight.assert_called_once()


if __name__ == "__main__":
    unittest.main()
