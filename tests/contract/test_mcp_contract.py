"""Protocol-level MCP registration contracts that do not start a server."""

from __future__ import annotations

import asyncio

from mailarium.mcp_server import McpRuntimeState, create_mcp_server


def test_mcp_registers_mailbox_tools_with_schema_and_safety_annotations() -> None:
    state = McpRuntimeState()
    try:
        mcp = create_mcp_server(state)
        registered = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
        assert {
            "email_mailbox_status",
            "email_mailbox_sync",
            "email_mailbox_triage",
            "email_mailbox_propose_action",
            "email_mailbox_proposal_status",
            "email_mailbox_execute_approved",
            "email_mailbox_reconcile",
        } <= registered.keys()

        sync = registered["email_mailbox_sync"]
        sync_params = sync.inputSchema["$defs"]["MailboxSyncInput"]["properties"]
        assert sync.inputSchema["required"] == ["params"]
        assert sync_params["account_id"]["minLength"] == 1
        assert sync_params["folders"]["maxItems"] == 100
        assert sync_params["include_attachment_content"]["type"] == "boolean"
        assert sync.annotations is not None
        assert sync.annotations.readOnlyHint is False
        assert sync.annotations.idempotentHint is True
        assert sync.annotations.openWorldHint is True

        execute = registered["email_mailbox_execute_approved"]
        execute_params = execute.inputSchema["$defs"]["MailboxProposalIdInput"]["properties"]
        assert execute_params["proposal_id"]["minLength"] == 1
        assert execute.annotations is not None
        assert execute.annotations.destructiveHint is True
        assert execute.annotations.idempotentHint is False
        assert execute.annotations.openWorldHint is True
    finally:
        state.close()
