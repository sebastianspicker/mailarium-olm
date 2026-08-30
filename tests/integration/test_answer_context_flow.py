"""Synthetic answer-context workflow checks with deterministic response budgets."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace

from mailarium.config import Settings
from mailarium.interfaces.mcp.mcp_models_answer_context import EmailAnswerContextInput
from mailarium.investigation.answer_context import build_answer_context_payload


class _Retriever:
    def __init__(self) -> None:
        self.last_search_debug = {"use_hybrid": False, "used_query_expansion": False, "fetch_size": 0}


class _Dependencies:
    def get_retriever(self) -> _Retriever:
        return _Retriever()

    def get_archive_database(self) -> None:
        return None

    async def offload(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)


def test_answer_context_ranks_synthetic_evidence_and_respects_the_json_budget(monkeypatch) -> None:
    """Preloaded evidence follows the public workflow and enters deterministic packing when oversized."""
    settings = replace(
        Settings(),
        mcp_max_search_results=3,
        mcp_max_json_response_chars=1_800,
        mcp_model_profile="test",
    )
    monkeypatch.setattr("mailarium.config.get_settings", lambda: settings)
    rows = [
        {
            "uid": "mail-low",
            "subject": "Low confidence",
            "sender_email": "low@example.test",
            "date": "2026-08-20",
            "score": 0.20,
            "snippet": "low evidence " * 100,
        },
        {
            "uid": "mail-high",
            "subject": "High confidence",
            "sender_email": "high@example.test",
            "date": "2026-08-21",
            "score": 0.95,
            "snippet": "high evidence " * 100,
        },
        {
            "uid": "mail-attachment",
            "subject": "Attachment evidence",
            "sender_email": "attachment@example.test",
            "date": "2026-08-22",
            "score": 0.99,
            "snippet": "attachment evidence " * 100,
            "candidate_kind": "attachment",
            "attachment": {"filename": "timeline.txt", "extraction_state": "text_extracted"},
        },
    ]

    payload = asyncio.run(
        build_answer_context_payload(
            _Dependencies(),
            EmailAnswerContextInput(question="What is the exact handoff timeline?", max_results=3),
            preloaded_evidence_rows=rows,
        )
    )

    assert payload["candidates"][0]["uid"] == "mail-high"
    assert payload["_packed"]["applied"] is True
    assert payload["_packed"]["truncated"]["attachment_candidates"] == 1
    assert len(json.dumps(payload, separators=(",", ":"))) <= settings.mcp_max_json_response_chars
