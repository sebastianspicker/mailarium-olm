"""MCP registration tests for mailbox authority and annotation boundaries."""

from __future__ import annotations

import asyncio
import json
import unittest
from types import SimpleNamespace

from mailarium.ews.errors import EWSFaultError
from mailarium.tools import mailbox


class MCPFake:
    def __init__(self) -> None:
        self.tools = {}

    def tool(self, *, name, annotations):
        def decorate(function):
            self.tools[name] = (function, annotations)
            return function

        return decorate


class ServiceFake:
    def readiness(self, account_id):
        return {
            "account_id": account_id,
            "status": "Offline verified; live EWS writes unverified.",
        }

    def propose_action(self, **kwargs):
        return {"proposal_id": "proposal", **kwargs}

    def execute(self, proposal_id):
        return {"proposal_id": proposal_id, "state": "succeeded"}

    def sync(self, _account_id, **_kwargs):
        raise EWSFaultError("ErrorServerBusy", "private remote diagnostic")


class DepsFake:
    DB_UNAVAILABLE = "unavailable"

    def __init__(self) -> None:
        self.service = ServiceFake()

    def get_mailbox_service(self):
        return self.service

    async def offload(self, function, *args, **kwargs):
        return function(*args, **kwargs)

    @staticmethod
    def tool_annotations(title):
        return SimpleNamespace(title=title, readOnlyHint=True, destructiveHint=False, openWorldHint=False)

    @staticmethod
    def idempotent_write_annotations(title):
        return SimpleNamespace(title=title, readOnlyHint=False, destructiveHint=False, openWorldHint=False)

    @staticmethod
    def remote_sync_annotations(title):
        return SimpleNamespace(title=title, readOnlyHint=False, destructiveHint=False, openWorldHint=True)

    @staticmethod
    def remote_execute_annotations(title):
        return SimpleNamespace(title=title, readOnlyHint=False, destructiveHint=True, openWorldHint=True)


class MailboxMCPTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mcp = MCPFake()
        mailbox.register(self.mcp, DepsFake())

    def test_mcp_exposes_no_approval_or_rejection_tool(self) -> None:
        self.assertNotIn("email_mailbox_approve", self.mcp.tools)
        self.assertNotIn("email_mailbox_reject", self.mcp.tools)
        self.assertIn("email_mailbox_execute_approved", self.mcp.tools)

    def test_execution_annotation_is_remote_and_destructive(self) -> None:
        annotation = self.mcp.tools["email_mailbox_execute_approved"][1]
        self.assertTrue(annotation.openWorldHint)
        self.assertTrue(annotation.destructiveHint)
        self.assertFalse(annotation.readOnlyHint)

    def test_proposal_schema_has_no_actor_field(self) -> None:
        self.assertNotIn("actor", mailbox.MailboxProposalInput.model_fields)
        params = mailbox.MailboxProposalInput(
            account_id="account",
            folder_id="inbox",
            operation="update_item",
            target_identity="item",
            target_change_key="ck",
            parameters={"is_read": True},
        )
        response = asyncio.run(self.mcp.tools["email_mailbox_propose_action"][0](params))
        self.assertIn('"proposal_id"', response)

    def test_remote_fault_message_is_not_exposed(self) -> None:
        params = mailbox.MailboxSyncInput(account_id="account")

        response = asyncio.run(self.mcp.tools["email_mailbox_sync"][0](params))

        self.assertIn("EWSFaultError", response)
        self.assertNotIn("private remote diagnostic", response)

    def test_status_preserves_the_exact_ews_verification_boundary(self) -> None:
        params = mailbox.MailboxAccountInput(account_id="account")

        response = asyncio.run(self.mcp.tools["email_mailbox_status"][0](params))

        self.assertEqual(
            "Offline verified; live EWS writes unverified.",
            json.loads(response)["status"],
        )


if __name__ == "__main__":
    unittest.main()
