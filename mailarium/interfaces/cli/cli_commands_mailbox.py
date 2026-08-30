"""Root CLI handlers for proposal-gated EWS mailbox operations."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from mailarium.mailbox.mailbox_service import MailboxService


def cmd_mailbox(args: argparse.Namespace, service: MailboxService) -> None:
    """Dispatch the ``mailarium mailbox`` command with runtime-owned services."""
    try:
        result = _run(args, service)
    except (KeyError, ValueError) as exc:
        print(f"Mailbox request is invalid: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except (PermissionError, RuntimeError) as exc:
        print(f"Mailbox operation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"Remote mailbox operation failed: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from exc
    _emit(result, as_json=bool(getattr(args, "json", False)))


def _run(args: argparse.Namespace, service: Any) -> Any:
    action = args.mailbox_action
    if action in {"accounts", "folders", "proposals"}:
        return _nested_action(args, service)
    if action == "readiness":
        return service.readiness(args.account_id)
    if action == "sync":
        return _sync(args, service)
    if action == "triage":
        return service.triage(
            args.account_id,
            folders=args.folders,
            create_proposals=args.create_proposals,
        )
    if action == "approve":
        proposal = service.proposal(args.proposal_id)
        _confirm_approval(proposal)
        return service.approve(args.proposal_id)
    if action == "reject":
        _require_interactive_terminal("Rejection")
        return service.reject(args.proposal_id, reason=args.reason)
    if action == "execute":
        return service.execute(args.proposal_id)
    if action == "reconcile":
        return service.reconcile(args.proposal_id)
    raise ValueError(f"Unknown mailbox action: {action}")


def _nested_action(args: argparse.Namespace, service: Any) -> Any:
    if args.mailbox_action == "accounts":
        return _accounts(args, service)
    if args.mailbox_action == "folders":
        return _folders(args, service)
    return _proposals(args, service)


def _proposals(args: argparse.Namespace, service: Any) -> Any:
    if args.mailbox_proposals_action == "list":
        return service.proposals(state=args.state)
    return service.proposal(args.proposal_id)


def _sync(args: argparse.Namespace, service: Any) -> Any:
    return service.sync(
        args.account_id,
        folders=args.folders,
        include_attachment_content=args.include_attachment_content,
        until_complete=bool(getattr(args, "until_complete", False)),
        defer_indexing=bool(getattr(args, "defer_indexing", False)),
    )


def _folders(args: argparse.Namespace, service: Any) -> Any:
    if args.mailbox_folders_action == "discover":
        return service.discover_folders(args.account_id, select=args.select)
    raise ValueError(f"Unknown folders action: {args.mailbox_folders_action}")


def _accounts(args: argparse.Namespace, service: Any) -> Any:
    action = args.mailbox_accounts_action
    if action == "list":
        return service.accounts()
    if action == "show":
        return service.account(args.account_id)
    if action == "configure":
        return service.configure_account(
            account_id=args.account_id,
            mailbox_address=args.mailbox_address,
            endpoint=args.endpoint,
            auth_mode=args.auth_mode,
            credential_ref=args.credential_ref,
            folders=args.folders,
            read_enabled=args.read_enabled,
            write_enabled=args.write_enabled,
        )
    raise ValueError(f"Unknown accounts action: {action}")


def _confirm_approval(proposal: dict[str, Any]) -> None:
    """Show the immutable intent and require a proposal-bound TTY response."""
    _require_interactive_terminal("Approval")
    print("Immutable mailbox action intent:")
    print(json.dumps(proposal, indent=2, sort_keys=True, default=str))
    suffix = str(proposal["proposal_id"])[-8:]
    confirmation = input(f"Type proposal ID suffix {suffix} to approve: ").strip()
    if confirmation != suffix:
        raise PermissionError("Approval confirmation did not match the proposal ID.")


def _require_interactive_terminal(action: str) -> None:
    if not sys.stdin.isatty():
        raise PermissionError(f"{action} requires an interactive local terminal.")


def _emit(value: Any, *, as_json: bool) -> None:
    if as_json or isinstance(value, (dict, list)):
        print(json.dumps(value, indent=2, sort_keys=True, default=str))
    else:
        print(value)
