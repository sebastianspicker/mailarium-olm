"""MCP tools for synchronized EWS state and immutable action proposals."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .utils import ToolDepsProto, get_deps, json_error, json_response

_deps: ToolDepsProto | None = None


class MailboxAccountInput(BaseModel):
    """Validate the account identifier required by account-scoped mailbox tools."""

    account_id: str = Field(min_length=1, max_length=200)


class MailboxSyncInput(MailboxAccountInput):
    """Validate optional folder and attachment-content controls for mailbox synchronization."""

    folders: list[str] = Field(default_factory=list, max_length=100)
    include_attachment_content: bool = False


class MailboxTriageInput(MailboxAccountInput):
    """Validate optional folder selection for synchronized mailbox triage."""

    folders: list[str] = Field(default_factory=list, max_length=100)


class MailboxProposalInput(MailboxAccountInput):
    """Validate immutable parameters for creating a mailbox action proposal."""

    folder_id: str = Field(min_length=1, max_length=500)
    operation: str = Field(min_length=1, max_length=50)
    target_identity: str = Field(default="", max_length=4000)
    target_change_key: str = Field(default="", max_length=4000)
    parameters: dict[str, Any] = Field(default_factory=dict)


class MailboxProposalStatusInput(BaseModel):
    """Validate a proposal identifier or lifecycle-state filter for proposal lookup."""

    proposal_id: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=30)


class MailboxProposalIdInput(BaseModel):
    """Validate the identifier required to act on one mailbox proposal."""

    proposal_id: str = Field(min_length=1, max_length=100)


def _d() -> ToolDepsProto:
    return get_deps(_deps)


def _service() -> Any:
    service = _d().get_mailbox_service()
    if service is None:
        raise RuntimeError("SQLite database not available. Run ingestion or configure the archive path first.")
    return service


def _remote_error(exc: Exception) -> str:
    """Return a stable error shape without exposing remote SOAP diagnostics."""
    return json_error(f"Remote mailbox operation failed: {type(exc).__name__}")


def register(mcp_instance: Any, deps: ToolDepsProto) -> None:
    """Register mailbox tools without exposing approval or actor parameters."""
    global _deps
    _deps = deps

    @mcp_instance.tool(name="email_mailbox_status", annotations=deps.tool_annotations("Mailbox Readiness"))
    async def email_mailbox_status(params: MailboxAccountInput) -> str:
        try:
            return json_response(await deps.offload(_service().readiness, params.account_id))
        except (KeyError, ValueError, RuntimeError) as exc:
            return json_error(str(exc))

    _register_sync_tool(mcp_instance, deps)

    @mcp_instance.tool(name="email_mailbox_triage", annotations=deps.tool_annotations("Triage Synchronized Mailbox"))
    async def email_mailbox_triage(params: MailboxTriageInput) -> str:
        try:
            result = await deps.offload(_service().triage, params.account_id, folders=params.folders)
            return json_response(result)
        except (KeyError, ValueError, RuntimeError) as exc:
            return json_error(str(exc))

    @mcp_instance.tool(
        name="email_mailbox_propose_action",
        annotations=deps.idempotent_write_annotations("Propose Mailbox Action"),
    )
    async def email_mailbox_propose_action(params: MailboxProposalInput) -> str:
        try:
            result = await deps.offload(
                _service().propose_action,
                account_id=params.account_id,
                folder_id=params.folder_id,
                operation=params.operation,
                target_identity=params.target_identity,
                target_change_key=params.target_change_key,
                parameters=params.parameters,
            )
            return json_response(result)
        except (KeyError, ValueError, RuntimeError) as exc:
            return json_error(str(exc))

    @mcp_instance.tool(name="email_mailbox_proposal_status", annotations=deps.tool_annotations("Mailbox Proposal Status"))
    async def email_mailbox_proposal_status(params: MailboxProposalStatusInput) -> str:
        try:
            if params.proposal_id:
                result = await deps.offload(_service().proposal, params.proposal_id)
            else:
                result = await deps.offload(_service().proposals, state=params.state)
            return json_response(result)
        except (KeyError, ValueError, RuntimeError) as exc:
            return json_error(str(exc))

    _register_execution_tools(mcp_instance, deps)


def _register_sync_tool(mcp_instance: Any, deps: ToolDepsProto) -> None:
    @mcp_instance.tool(name="email_mailbox_sync", annotations=deps.remote_sync_annotations("Synchronize EWS Mailbox"))
    async def email_mailbox_sync(params: MailboxSyncInput) -> str:
        try:
            result = await deps.offload(
                _service().sync,
                params.account_id,
                folders=params.folders,
                include_attachment_content=params.include_attachment_content,
            )
            return json_response(result)
        except (KeyError, ValueError, PermissionError, RuntimeError) as exc:
            return json_error(str(exc))
        except Exception as exc:
            return _remote_error(exc)


def _register_execution_tools(mcp_instance: Any, deps: ToolDepsProto) -> None:
    @mcp_instance.tool(
        name="email_mailbox_execute_approved",
        annotations=deps.remote_execute_annotations("Execute Approved Mailbox Action"),
    )
    async def email_mailbox_execute_approved(params: MailboxProposalIdInput) -> str:
        try:
            return json_response(await deps.offload(_service().execute, params.proposal_id))
        except (KeyError, ValueError, PermissionError, RuntimeError) as exc:
            return json_error(str(exc))
        except Exception as exc:
            return _remote_error(exc)

    @mcp_instance.tool(
        name="email_mailbox_reconcile",
        annotations=deps.remote_sync_annotations("Reconcile Uncertain Mailbox Action"),
    )
    async def email_mailbox_reconcile(params: MailboxProposalIdInput) -> str:
        try:
            return json_response(await deps.offload(_service().reconcile, params.proposal_id))
        except (KeyError, ValueError, PermissionError, RuntimeError) as exc:
            return json_error(str(exc))
        except Exception as exc:
            return _remote_error(exc)
