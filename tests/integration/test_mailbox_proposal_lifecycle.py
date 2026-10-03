"""Differential state-machine record of the proposal-gated EWS mailbox write path.

Every scenario drives only the public ``MailboxService`` API over a real
temporary archive, with a synthetic in-process gateway injected through
``gateway_factory`` (no network, no real credentials). The record captures each
public return value or raised error, the final proposals, the lifecycle event
and execution attempt rows, the affected source rows, and every gateway call.

The snapshot was recorded from the pre-recomposition mixin implementation
(commit 8c9c054, ``mailarium/mailbox/mailbox_service.py``) and pins its
observable behavior. Proposal identifiers are replaced by first-appearance
tokens and wall-clock timestamps are normalized; the expiry and execution
deadline windows are kept as durations. Regenerate deliberately with
``MAILARIUM_UPDATE_SNAPSHOTS=1``.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from mailarium.archive import open_archive_database
from mailarium.mailbox.ews.errors import EWSFaultError
from mailarium.mailbox.ews.gateway import EWSItem, EWSItemRef, EWSOperationResult, EWSSyncDelta

try:
    from mailarium.mailbox.service import MailboxService
except ModuleNotFoundError as exc:  # pre-recomposition layout
    if exc.name != "mailarium.mailbox.service":
        raise
    from mailarium.mailbox.mailbox_service import MailboxService  # type: ignore[no-redef]

SNAPSHOT = Path(__file__).parent / "snapshots" / "mailbox_proposal_lifecycle.json"
ACCOUNT = "synthetic"
SOURCE_FOLDERS = ("inbox", "archive", "drafts", "sentitems")
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z)?")


def _item(item_id: str, change_key: str, subject: str, *, is_read: bool) -> EWSItem:
    return EWSItem(
        item_id=item_id,
        change_key=change_key,
        subject=subject,
        sender="sender@example.test",
        body_text=f"Synthetic body for {subject}.",
        received_at="2026-08-20T10:00:00Z",
        internet_message_id=f"<{item_id}@example.test>",
        recipients=("recipient@example.test",),
        is_read=is_read,
    )


def _delta(*, created: tuple[str, ...] = (), updated: tuple[str, ...] = (), watermark: str) -> EWSSyncDelta:
    return EWSSyncDelta(
        created=tuple(EWSItemRef(value, None) for value in created),
        updated=tuple(EWSItemRef(value, None) for value in updated),
        deleted=(),
        watermark=watermark,
        has_more=False,
        raw_change_count=len(created) + len(updated),
    )


class _Gateway:
    """Synthetic remote mailbox with scripted sync pages, mutation results, and one-shot failures."""

    def __init__(self) -> None:
        self.calls: list[list[Any]] = []
        self.items: dict[str, EWSItem] = {}
        self.pages: dict[str, list[EWSSyncDelta]] = {}
        self.failures: dict[str, Exception] = {}
        self.correlated: dict[str, tuple[EWSItemRef, ...]] = {}

    def _call(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append([name, list(args), dict(sorted(kwargs.items()))])
        failure = self.failures.pop(name, None)
        if failure is not None:
            raise failure

    def sync_folder_items(self, folder_id: str, *, watermark: str | None, max_changes: int) -> EWSSyncDelta:
        self._call("sync_folder_items", folder_id, watermark=watermark)
        return self.pages[folder_id].pop(0)

    def get_items(self, item_ids: Any) -> tuple[EWSItem, ...]:
        refs = tuple(item_ids)
        self._call("get_items", *(ref.item_id for ref in refs))
        return tuple(self.items[ref.item_id] for ref in refs)

    def update_item(self, item_id: str, change_key: str, **fields: Any) -> EWSOperationResult:
        self._call("update_item", item_id, change_key, **fields)
        return EWSOperationResult("UpdateItem", (EWSItemRef(item_id, f"{change_key}-updated"),))

    def move_item(self, item_id: str, change_key: str, destination_folder_id: str) -> EWSOperationResult:
        self._call("move_item", item_id, change_key, destination_folder_id)
        return EWSOperationResult("MoveItem", (EWSItemRef(f"{item_id}-moved", f"{change_key}-moved"),))

    def copy_item(self, item_id: str, change_key: str, destination_folder_id: str) -> EWSOperationResult:
        self._call("copy_item", item_id, change_key, destination_folder_id)
        return EWSOperationResult("CopyItem", (EWSItemRef(f"{item_id}-copy", f"{change_key}-copy"),))

    def delete_to_deleted_items(self, item_id: str, change_key: str) -> EWSOperationResult:
        self._call("delete_to_deleted_items", item_id, change_key)
        return EWSOperationResult("DeleteItem")

    def create_text_draft(
        self, subject: str, body_text: str, recipients: Any, *, proposal_id: str | None = None
    ) -> EWSOperationResult:
        self._call("create_text_draft", subject, body_text, list(recipients), proposal_id=proposal_id)
        return EWSOperationResult("CreateItem", (EWSItemRef("draft-1", "draft-change-1"),))

    def send_existing_draft(self, item_id: str, change_key: str, *, proposal_id: str | None = None) -> EWSOperationResult:
        self._call("send_existing_draft", item_id, change_key, proposal_id=proposal_id)
        return EWSOperationResult("SendItem")

    def find_items_by_proposal_id(self, folder_id: str, proposal_id: str) -> tuple[EWSItemRef, ...]:
        self._call("find_items_by_proposal_id", folder_id, proposal_id)
        return self.correlated.get(folder_id, ())


class _Harness:
    """One temporary archive, one synthetic gateway, and the ordered record of public calls."""

    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True)
        self.database = open_archive_database(str(root / "archive.db"))
        self.gateway = _Gateway()
        self.factory_calls: list[dict[str, Any]] = []
        self.steps: list[list[Any]] = []
        self.service = MailboxService(self.database.mailbox, db=self.database, gateway_factory=self._factory)

    def _factory(self, account: Any, policy: Any) -> _Gateway:
        self.factory_calls.append(
            {
                "account_id": account["account_id"],
                "account_write_enabled": bool(account["write_enabled"]),
                "process_write_enabled": bool(policy.write_enabled),
            }
        )
        return self.gateway

    def step(self, name: str, call: Callable[[], Any]) -> Any:
        try:
            value = call()
        except Exception as exc:
            self.steps.append([name, {"raises": type(exc).__name__, "message": str(exc)}])
            return None
        self.steps.append([name, value])
        return value

    def configure(self, *, write_enabled: bool = True, endpoint: str = "https://ews.example.test/EWS/Exchange.asmx") -> None:
        self.step(
            "configure_account",
            lambda: self.service.configure_account(
                account_id=ACCOUNT,
                mailbox_address="archive@example.test",
                endpoint=endpoint,
                auth_mode="basic",
                credential_ref="basic-env:SYNTHETIC_EWS_USER:SYNTHETIC_EWS_PASSWORD",
                folders=("inbox", "archive"),
                read_enabled=True,
                write_enabled=write_enabled,
            ),
        )

    def seed(self, *, write_enabled: bool = True) -> None:
        self.configure(write_enabled=write_enabled)
        self.gateway.items.update(
            {
                "remote-1": _item("remote-1", "change-1", "Unread inbox handoff", is_read=False),
                "remote-2": _item("remote-2", "change-2", "Read inbox note", is_read=True),
                "remote-3": _item("remote-3", "change-3", "Unread archive note", is_read=False),
            }
        )
        self.gateway.pages["inbox"] = [_delta(created=("remote-1", "remote-2"), watermark="wm-inbox-1")]
        self.gateway.pages["archive"] = [_delta(created=("remote-3",), watermark="wm-archive-1")]
        self.step("readiness", lambda: self.service.readiness(ACCOUNT))
        self.step("sync", lambda: self.service.sync(ACCOUNT, defer_indexing=True))

    def propose(self, name: str, *, folder_id: str, operation: str, target: str, change_key: str, **parameters: Any) -> str:
        proposal = self.step(
            name,
            lambda: self.service.propose_action(
                account_id=ACCOUNT,
                folder_id=folder_id,
                operation=operation,
                target_identity=target,
                target_change_key=change_key,
                parameters=parameters,
            ),
        )
        return "" if proposal is None else str(proposal["proposal_id"])

    def approve_and_execute(self, proposal_id: str, label: str) -> None:
        self.step(f"approve {label}", lambda: self.service.approve(proposal_id))
        self.step(f"execute {label}", lambda: self.service.execute(proposal_id))

    def close(self) -> None:
        self.service.close()
        self.database.close()


def _update(h: _Harness, name: str, target: str = "remote-1", change_key: str = "change-1", folder_id: str = "inbox") -> str:
    return h.propose(name, folder_id=folder_id, operation="update_item", target=target, change_key=change_key, is_read=True)


def _draft(h: _Harness, name: str) -> str:
    return h.propose(
        name,
        folder_id="drafts",
        operation="create_draft",
        target="",
        change_key="",
        subject="Synthetic draft",
        body_text="Synthetic draft body.",
        recipients=["recipient@example.test"],
    )


def _scenario_success_then_reconcile(h: _Harness) -> None:
    h.seed()
    proposal_id = _update(h, "propose update")
    h.approve_and_execute(proposal_id, "update")
    h.step("reconcile succeeded", lambda: h.service.reconcile(proposal_id))
    h.step("proposal", lambda: h.service.proposal(proposal_id))


def _scenario_reject(h: _Harness) -> None:
    h.seed()
    proposal_id = _update(h, "propose update")
    h.step("reject", lambda: h.service.reject(proposal_id, reason="synthetic reviewer declined"))
    h.step("approve rejected", lambda: h.service.approve(proposal_id))
    h.step("execute rejected", lambda: h.service.execute(proposal_id))
    h.step("reject again", lambda: h.service.reject(proposal_id, reason="again"))
    approved_id = _update(h, "propose second update", target="remote-3", change_key="change-3", folder_id="archive")
    h.step("approve second", lambda: h.service.approve(approved_id))
    h.step("reject approved", lambda: h.service.reject(approved_id, reason="withdrawn after approval"))


def _scenario_execute_without_approval(h: _Harness) -> None:
    h.seed()
    proposal_id = _update(h, "propose update")
    h.step("execute pending", lambda: h.service.execute(proposal_id))
    h.step("pending proposals", lambda: h.service.proposals(state="pending"))


def _scenario_stale_change_key(h: _Harness) -> None:
    h.seed()
    proposal_id = _update(h, "propose update")
    h.step("approve", lambda: h.service.approve(proposal_id))
    h.gateway.items["remote-1"] = _item("remote-1", "change-1b", "Unread inbox handoff", is_read=False)
    h.gateway.pages["inbox"] = [_delta(updated=("remote-1",), watermark="wm-inbox-2")]
    h.step("sync remote change", lambda: h.service.sync(ACCOUNT, folders=("inbox",), defer_indexing=True))
    h.step("execute stale", lambda: h.service.execute(proposal_id))
    _update(h, "repropose identical after conflict")
    rebased = _update(h, "propose current change key", change_key="change-1b")
    h.approve_and_execute(rebased, "current change key")


def _scenario_uncertain_then_reconcile(h: _Harness) -> None:
    h.seed()
    proposal_id = _draft(h, "propose draft")
    h.gateway.failures["create_text_draft"] = RuntimeError("synthetic connection reset after send")
    h.approve_and_execute(proposal_id, "draft uncertain")
    h.step("reconcile without match", lambda: h.service.reconcile(proposal_id))
    h.step("execute uncertain", lambda: h.service.execute(proposal_id))
    h.gateway.correlated["drafts"] = (EWSItemRef("draft-9", "draft-change-9"),)
    h.step("reconcile with match", lambda: h.service.reconcile(proposal_id))
    h.step("reconcile again", lambda: h.service.reconcile(proposal_id))


def _scenario_uncertain_send_duplicate_matches(h: _Harness) -> None:
    h.seed()
    draft_id = _draft(h, "propose draft")
    h.approve_and_execute(draft_id, "draft")
    send_id = h.propose("propose send", folder_id="drafts", operation="send_item", target="draft-1", change_key="draft-change-1")
    h.gateway.failures["send_existing_draft"] = EWSFaultError("SOAPFault", "synthetic gateway timeout", http_status=504)
    h.approve_and_execute(send_id, "send uncertain")
    h.gateway.correlated["sentitems"] = (EWSItemRef("sent-1", "sent-change-1"), EWSItemRef("sent-2", "sent-change-2"))
    h.step("reconcile duplicate matches", lambda: h.service.reconcile(send_id))


def _scenario_uncertain_send_reconciled(h: _Harness) -> None:
    h.seed()
    draft_id = _draft(h, "propose draft")
    h.approve_and_execute(draft_id, "draft")
    send_id = h.propose("propose send", folder_id="drafts", operation="send_item", target="draft-1", change_key="draft-change-1")
    h.gateway.failures["send_existing_draft"] = EWSFaultError("ErrorInternalServerError", "synthetic", http_status=500)
    h.approve_and_execute(send_id, "send uncertain")
    h.gateway.correlated["sentitems"] = (EWSItemRef("sent-1", "sent-change-1"),)
    h.step("reconcile single match", lambda: h.service.reconcile(send_id))


def _scenario_fault_classification(h: _Harness) -> None:
    h.seed()
    retry_id = _update(h, "propose busy update")
    h.gateway.failures["update_item"] = EWSFaultError("ErrorServerBusy", "synthetic busy")
    h.approve_and_execute(retry_id, "busy")
    h.step("execute retry", lambda: h.service.execute(retry_id))
    conflict_id = _update(h, "propose conflicting update", target="remote-3", change_key="change-3", folder_id="archive")
    h.gateway.failures["update_item"] = EWSFaultError("ErrorInvalidChangeKey", "synthetic conflict")
    h.approve_and_execute(conflict_id, "ews conflict")
    failed_id = h.propose(
        "propose rejected categories",
        folder_id="inbox",
        operation="update_item",
        target="remote-2",
        change_key="change-2",
        categories=["Synthetic"],
    )
    h.gateway.failures["update_item"] = EWSFaultError("ErrorAccessDenied", "synthetic denied")
    h.approve_and_execute(failed_id, "ews fault")
    uncertain_id = h.propose(
        "propose uncertain importance",
        folder_id="inbox",
        operation="update_item",
        target="remote-2",
        change_key="change-2",
        importance="High",
    )
    h.gateway.failures["update_item"] = RuntimeError("synthetic socket closed")
    h.approve_and_execute(uncertain_id, "transport uncertain")
    h.step("reconcile update not correlatable", lambda: h.service.reconcile(uncertain_id))


def _scenario_process_write_gate_disabled(h: _Harness) -> None:
    h.seed()
    proposal_id = _update(h, "propose update")
    h.approve_and_execute(proposal_id, "write gate disabled")
    h.step("reconcile write gate disabled", lambda: h.service.reconcile(proposal_id))


def _scenario_account_write_disabled(h: _Harness) -> None:
    h.seed(write_enabled=False)
    proposal_id = _update(h, "propose update")
    h.approve_and_execute(proposal_id, "account write disabled")


def _scenario_duplicate_execute(h: _Harness) -> None:
    h.seed()
    proposal_id = _update(h, "propose update")
    h.approve_and_execute(proposal_id, "first")
    h.step("execute duplicate", lambda: h.service.execute(proposal_id))
    h.step("execute duplicate again", lambda: h.service.execute(proposal_id))
    h.step("approve executed", lambda: h.service.approve(proposal_id))
    _update(h, "repropose identical after success")


def _scenario_account_configuration_changed(h: _Harness) -> None:
    h.seed()
    proposal_id = _update(h, "propose update")
    h.step("approve", lambda: h.service.approve(proposal_id))
    h.configure(endpoint="https://ews-moved.example.test/EWS/Exchange.asmx")
    h.step("execute after reconfiguration", lambda: h.service.execute(proposal_id))


def _scenario_source_missing(h: _Harness) -> None:
    h.seed()
    proposal_id = _update(h, "propose unknown item", target="remote-404", change_key="change-404")
    h.approve_and_execute(proposal_id, "missing source")


def _scenario_other_operations(h: _Harness) -> None:
    h.seed()
    move_id = h.propose(
        "propose move",
        folder_id="inbox",
        operation="move_item",
        target="remote-2",
        change_key="change-2",
        destination_folder_id="archive",
    )
    h.approve_and_execute(move_id, "move")
    copy_id = h.propose(
        "propose copy",
        folder_id="archive",
        operation="copy_item",
        target="remote-3",
        change_key="change-3",
        destination_folder_id="inbox",
    )
    h.approve_and_execute(copy_id, "copy")
    delete_id = h.propose("propose delete", folder_id="inbox", operation="delete_item", target="remote-1", change_key="change-1")
    h.approve_and_execute(delete_id, "delete")
    draft_id = _draft(h, "propose draft")
    h.approve_and_execute(draft_id, "draft")
    send_id = h.propose("propose send", folder_id="drafts", operation="send_item", target="draft-1", change_key="draft-change-1")
    h.approve_and_execute(send_id, "send")


def _scenario_triage_selected_folders(h: _Harness) -> None:
    h.seed()
    h.step("triage all", lambda: h.service.triage(ACCOUNT))
    h.step("triage archive with proposals", lambda: h.service.triage(ACCOUNT, folders=("archive",), create_proposals=True))
    h.step("triage archive again", lambda: h.service.triage(ACCOUNT, folders=(" archive ", "archive"), create_proposals=True))
    h.step("triage outside allowlist", lambda: h.service.triage(ACCOUNT, folders=("unknown",)))
    h.step("proposals", lambda: h.service.proposals())


def _scenario_proposal_validation(h: _Harness) -> None:
    h.seed()
    first = _update(h, "propose update")
    _update(h, "propose identical update")
    h.propose("unsupported operation", folder_id="inbox", operation="archive_item", target="remote-1", change_key="change-1")
    inbox = {"folder_id": "inbox", "target": "remote-1", "change_key": "change-1"}
    h.propose("unknown update field", operation="update_item", flag=1, **inbox)
    h.propose("empty update", folder_id="inbox", operation="update_item", target="remote-1", change_key="change-1")
    h.propose(
        "non-boolean is_read", folder_id="inbox", operation="update_item", target="remote-1", change_key="change-1", is_read="yes"
    )
    h.propose("bad importance", operation="update_item", importance="Urgent", **inbox)
    h.propose(
        "folder outside allowlist",
        folder_id="junk",
        operation="update_item",
        target="remote-1",
        change_key="change-1",
        is_read=True,
    )
    h.propose(
        "destination outside allowlist",
        folder_id="inbox",
        operation="move_item",
        target="remote-1",
        change_key="change-1",
        destination_folder_id="junk",
    )
    h.propose(
        "delete with parameters", folder_id="inbox", operation="delete_item", target="remote-1", change_key="change-1", hard=True
    )
    h.propose("send with parameters", folder_id="drafts", operation="send_item", target="draft-1", change_key="d", now=True)
    h.propose("draft missing fields", folder_id="drafts", operation="create_draft", target="", change_key="", subject="Only")
    h.propose(
        "draft blank subject",
        folder_id="drafts",
        operation="create_draft",
        target="",
        change_key="",
        subject=" ",
        body_text="Body",
        recipients=["recipient@example.test"],
    )
    h.propose(
        "draft no recipients",
        folder_id="drafts",
        operation="create_draft",
        target="",
        change_key="",
        subject="Subject",
        body_text="Body",
        recipients=[],
    )
    h.step(
        "unknown account",
        lambda: h.service.propose_action(
            account_id="missing",
            folder_id="inbox",
            operation="delete_item",
            target_identity="remote-1",
            target_change_key="change-1",
            parameters={},
        ),
    )
    h.step("approve unknown proposal", lambda: h.service.approve("missing-proposal"))
    h.step("execute unknown proposal", lambda: h.service.execute("missing-proposal"))
    h.step("proposals bad state", lambda: h.service.proposals(state="bogus"))
    h.step("approved proposals", lambda: h.service.proposals(state="approved"))
    h.step("proposal", lambda: h.service.proposal(first))


SCENARIOS: dict[str, tuple[dict[str, str], Callable[[_Harness], None]]] = {
    "success_then_reconcile": ({}, _scenario_success_then_reconcile),
    "reject": ({}, _scenario_reject),
    "execute_without_approval": ({}, _scenario_execute_without_approval),
    "stale_change_key": ({}, _scenario_stale_change_key),
    "uncertain_then_reconcile": ({}, _scenario_uncertain_then_reconcile),
    "uncertain_send_duplicate_matches": ({}, _scenario_uncertain_send_duplicate_matches),
    "uncertain_send_reconciled": ({}, _scenario_uncertain_send_reconciled),
    "fault_classification": ({}, _scenario_fault_classification),
    "process_write_gate_disabled": ({"EWS_WRITE_ENABLED": "false"}, _scenario_process_write_gate_disabled),
    "account_write_disabled": ({}, _scenario_account_write_disabled),
    "duplicate_execute": ({}, _scenario_duplicate_execute),
    "account_configuration_changed": ({}, _scenario_account_configuration_changed),
    "source_missing": ({}, _scenario_source_missing),
    "other_operations": ({}, _scenario_other_operations),
    "triage_selected_folders": ({}, _scenario_triage_selected_folders),
    "proposal_validation": ({}, _scenario_proposal_validation),
}


def _seconds_between(start: Any, end: Any) -> int | None:
    if not start or not end:
        return None
    return int((datetime.fromisoformat(str(end)) - datetime.fromisoformat(str(start))).total_seconds())


def _final_state(h: _Harness) -> dict[str, Any]:
    conn = h.database.conn
    proposals = [
        {
            **proposal,
            "expiry_window_seconds": _seconds_between(proposal["created_at"], proposal["expires_at"]),
            "execution_window_seconds": _seconds_between(proposal["approved_at"], proposal["execution_deadline"]),
        }
        for proposal in h.service.proposals()
    ]
    events = [
        {"proposal_id": row[0], "event_type": row[1], "actor_kind": row[2], "detail": json.loads(row[3]), "created_at": row[4]}
        for row in conn.execute(
            "SELECT proposal_id,event_type,actor_kind,detail_json,created_at FROM mailbox_action_events ORDER BY id"
        )
    ]
    attempts = [
        {
            "attempt_id": row[0],
            "proposal_id": row[1],
            "state": row[2],
            "started_at": row[3],
            "completed_at": row[4],
            "detail": json.loads(row[5]),
        }
        for row in conn.execute(
            "SELECT id,proposal_id,state,started_at,completed_at,detail_json FROM mailbox_action_attempts ORDER BY id"
        )
    ]
    sources = {
        folder: [
            {
                "remote_item_id": row["remote_item_id"],
                "change_key": row["change_key"],
                "is_tombstone": bool(row["is_tombstone"]),
                "has_canonical_email": bool(row["canonical_email_uid"]),
                "metadata": {key: row["metadata"][key] for key in ("is_read", "proposal_id") if key in row["metadata"]},
            }
            for row in h.database.mailbox.sources.list_sources(ACCOUNT, folder, include_tombstones=True)
        ]
        for folder in SOURCE_FOLDERS
    }
    return {"proposals": proposals, "events": events, "attempts": attempts, "sources": sources}


def _plain(value: Any) -> Any:
    """Convert dataclass-derived tuples and mappings into JSON-shaped values."""
    if isinstance(value, dict):
        return {str(key): _plain(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(nested) for nested in value]
    return value


def _normalize(record: Any, proposal_ids: set[str]) -> Any:
    """Replace proposal identifiers by first-appearance tokens and timestamps by a placeholder."""
    tokens: dict[str, str] = {}
    pattern = re.compile("|".join(re.escape(value) for value in sorted(proposal_ids))) if proposal_ids else None

    def token(match: re.Match[str]) -> str:
        return tokens.setdefault(match.group(0), f"<proposal-{len(tokens) + 1}>")

    def walk(value: Any) -> Any:
        if isinstance(value, dict):
            return {walk(key): walk(nested) for key, nested in value.items()}
        if isinstance(value, list):
            return [walk(nested) for nested in value]
        if isinstance(value, str):
            text = pattern.sub(token, value) if pattern is not None else value
            return _TIMESTAMP.sub("<timestamp>", text)
        return value

    return walk(record)


def _run_scenario(name: str, root: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    environment, scenario = SCENARIOS[name]
    with monkeypatch.context() as patch:
        for key in ("EWS_ATTACHMENT_CONTENT_ENABLED", "EWS_MAX_SYNC_ITEMS", "EWS_REQUEST_TIMEOUT_SECONDS"):
            patch.delenv(key, raising=False)
        patch.setenv("EWS_READ_ENABLED", "true")
        patch.setenv("EWS_WRITE_ENABLED", "true")
        patch.setenv("SYNTHETIC_EWS_USER", "synthetic-user")
        patch.setenv("SYNTHETIC_EWS_PASSWORD", "synthetic-password")
        for key, value in environment.items():
            patch.setenv(key, value)
        harness = _Harness(root / name)
        try:
            scenario(harness)
            final = _final_state(harness)
            proposal_ids = {str(proposal["proposal_id"]) for proposal in harness.service.proposals()}
        finally:
            harness.close()
    record = _plain(
        {
            "steps": harness.steps,
            "gateway_factory_calls": harness.factory_calls,
            "gateway_calls": harness.gateway.calls,
            **final,
        }
    )
    normalized = _normalize(record, proposal_ids)
    normalized["proposals"] = sorted(normalized["proposals"], key=lambda proposal: proposal["proposal_id"])
    return normalized


def test_mailbox_proposal_lifecycle_matches_the_recorded_state_machine(tmp_path, monkeypatch) -> None:
    """Every scenario reproduces the recorded public results, durable rows, and gateway calls."""
    outputs = {name: _run_scenario(name, tmp_path, monkeypatch) for name in SCENARIOS}

    if os.environ.get("MAILARIUM_UPDATE_SNAPSHOTS") == "1":
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(outputs, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        return
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert sorted(outputs) == sorted(expected)
    for name, value in expected.items():
        assert outputs[name] == value, name
