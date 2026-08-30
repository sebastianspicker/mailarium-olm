"""Adapter wiring checks using registered handlers and synthetic services."""

from __future__ import annotations

import asyncio
import json

from mailarium.interfaces.mcp.mcp_models_search import EmailSearchStructuredInput
from mailarium.interfaces.mcp.tools import mailbox as mailbox_tools
from mailarium.interfaces.mcp.tools import search as search_tools
from mailarium.interfaces.mcp.tools.mailbox import MailboxSyncInput


class _Registry:
    def __init__(self) -> None:
        self.handlers = {}
        self.annotations = {}

    def tool(self, *, name, annotations):
        self.annotations[name] = annotations

        def register(handler):
            self.handlers[name] = handler
            return handler

        return register


class _Retriever:
    def __init__(self) -> None:
        self.calls = []
        self.last_search_debug = {"use_hybrid": True, "retrieval_policy": {"scope": "finance"}}

    def search_filtered(self, **kwargs):
        self.calls.append(kwargs)
        return []

    @staticmethod
    def serialize_results(query, results):
        return {"query": query, "count": len(results), "results": []}


class _MailboxService:
    def __init__(self) -> None:
        self.calls = []

    def sync(self, account_id, *, folders, include_attachment_content):
        self.calls.append((account_id, folders, include_attachment_content))
        return {"account_id": account_id, "created": 1}


class _Dependencies:
    DB_UNAVAILABLE = "not used"

    def __init__(self, retriever: _Retriever, mailbox_service: _MailboxService) -> None:
        self.retriever = retriever
        self.mailbox_service = mailbox_service

    def get_retriever(self):
        return self.retriever

    def get_mailbox_service(self):
        return self.mailbox_service

    async def offload(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    @staticmethod
    def tool_annotations(title):
        return {"kind": "read", "title": title}

    @staticmethod
    def idempotent_write_annotations(title):
        return {"kind": "idempotent-write", "title": title}

    @staticmethod
    def remote_sync_annotations(title):
        return {"kind": "remote-sync", "title": title}

    @staticmethod
    def remote_execute_annotations(title):
        return {"kind": "remote-execute", "title": title}


def test_mcp_adapters_forward_validated_search_and_sync_requests_to_services() -> None:
    """Registered tools preserve structured filters and use the injected service boundary."""
    registry = _Registry()
    retriever = _Retriever()
    mailbox_service = _MailboxService()
    deps = _Dependencies(retriever, mailbox_service)
    search_tools.register(registry, deps)
    mailbox_tools.register(registry, deps)

    search_response = asyncio.run(
        registry.handlers["email_search_structured"](
            EmailSearchStructuredInput(query="handoff", top_k=4, sender="analyst", folder="Inbox", hybrid=True, scope="finance")
        )
    )
    sync_response = asyncio.run(
        registry.handlers["email_mailbox_sync"](
            MailboxSyncInput(account_id="synthetic", folders=["inbox"], include_attachment_content=False)
        )
    )

    assert retriever.calls == [
        {"query": "handoff", "top_k": 4, "sender": "analyst", "folder": "Inbox", "hybrid": True, "scope": "finance"}
    ]
    assert json.loads(search_response)["retrieval_diagnostics"]["retrieval_policy"] == {"scope": "finance"}
    assert mailbox_service.calls == [("synthetic", ["inbox"], False)]
    assert json.loads(sync_response) == {"account_id": "synthetic", "created": 1}
    assert registry.annotations["email_mailbox_sync"]["kind"] == "remote-sync"
