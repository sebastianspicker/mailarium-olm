"""Golden answer-context payloads for single-lane and multi-lane retrieval.

A deterministic fake retriever and archive drive the public answer-context
entry point through the single-lane path (one derived lane, with query
expansion terms), the multi-lane path (explicit query lanes, segment hits,
attachments, and calendar evidence), and a scan-session path where previously
seen messages are filtered out. The snapshot pins the public payload and the
internal retrieval context (evidence bank, support diversity, and expansion
attribution) recorded from the pre-reconstruction implementation. Regenerate
deliberately with ``MAILARIUM_UPDATE_SNAPSHOTS=1``.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from mailarium.interfaces.mcp.models.answer_context import EmailAnswerContextInput
from mailarium.investigation.answer_context import build_answer_context_payload
from mailarium.platform.settings import Settings
from mailarium.retrieval.models import SearchResult
from mailarium.retrieval.scan_session import filter_seen, reset_session

SNAPSHOT = Path(__file__).parent / "snapshots" / "answer_context_lanes.json"

_EMAILS: dict[str, dict[str, Any]] = {
    "m1": {
        "uid": "m1",
        "subject": "Budget approval",
        "sender_email": "alice@example.test",
        "sender_name": "Alice",
        "to": ["bob@example.test"],
        "cc": ["carol@example.test"],
        "date": "2026-03-01T09:00:00",
        "conversation_id": "conv-budget",
        "body_text": "We approved the budget for the pilot.\nThe total is 40k and Bob owns the rollout.",
        "forensic_body_text": "We approved the budget for the pilot.\nThe total is 40k and Bob owns the rollout.",
    },
    "m2": {
        "uid": "m2",
        "subject": "Re: Budget approval",
        "sender_email": "bob@example.test",
        "sender_name": "Bob",
        "to": ["alice@example.test"],
        "date": "2026-03-02T10:30:00",
        "conversation_id": "conv-budget",
        "in_reply_to": "<m1@example.test>",
        "references": ["<m1@example.test>"],
        "reply_context_from": "alice@example.test",
        "body_text": "Thanks, I will start the rollout on Monday.\n\n> We approved the budget for the pilot.",
    },
    "m3": {
        "uid": "m3",
        "subject": "Rollout meeting invite",
        "sender_email": "carol@example.test",
        "sender_name": "Carol",
        "to": ["alice@example.test", "bob@example.test"],
        "date": "2026-03-03T08:15:00",
        "conversation_id": "",
        "inferred_thread_id": "inferred-rollout",
        "inferred_parent_uid": "m2",
        "inferred_match_reason": "subject",
        "inferred_match_confidence": 0.7,
        "body_text": "Calendar invite: rollout kickoff meeting on Monday at 10.",
    },
    "m4": {
        "uid": "m4",
        "subject": "Cost sheet",
        "sender_email": "dave@example.test",
        "sender_name": "Dave",
        "to": ["alice@example.test"],
        "date": "2026-03-04T12:00:00",
        "conversation_id": "conv-costs",
        "body_text": "Attached is the cost sheet for the pilot budget.",
    },
    "m5": {
        "uid": "m5",
        "subject": "Vendor follow-up",
        "sender_email": "erin@example.test",
        "sender_name": "Erin",
        "to": ["alice@example.test"],
        "date": "2026-03-05T16:45:00",
        "conversation_id": "conv-vendor",
        "body_text": "Following up on the vendor quote; the pilot budget may change.",
    },
}

_SEGMENTS: dict[str, list[dict[str, Any]]] = {
    "m2": [
        {"ordinal": 0, "segment_type": "authored_body", "text": "Thanks, I will start the rollout on Monday."},
        {"ordinal": 1, "segment_type": "quoted_reply", "text": "From: alice@example.test\nWe approved the budget for the pilot."},
    ],
    "m5": [
        {"ordinal": 0, "segment_type": "authored_body", "text": "Following up on the vendor quote; the pilot budget may change."},
        {"ordinal": 1, "segment_type": "forwarded_message", "text": "bob@example.test and carol@example.test discussed quotes."},
    ],
}

# Each lane query maps to (uid, chunk suffix, text, distance, extra metadata) hits in retriever order.
_HITS: dict[str, list[tuple[str, str, str, float, dict[str, Any]]]] = {
    "budget": [
        ("m5", "0", "Following up on the vendor quote; the pilot budget may change.", 0.30, {}),
        ("m1", "0", "We approved the budget for the pilot.", 0.12, {}),
        ("m2", "0", "Thanks, I will start the rollout on Monday.", 0.25, {}),
        (
            "m4",
            "att_0",
            "Pilot cost sheet: total 40k, rollout owner Bob.",
            0.20,
            {
                "attachment_filename": "costs.xlsx",
                "is_attachment": True,
                "attachment_id": "att-1",
                "char_start": 0,
                "char_end": 46,
            },
        ),
    ],
    "rollout": [
        ("m3", "0", "Calendar invite: rollout kickoff meeting on Monday at 10.", 0.18, {"is_calendar_message": True}),
        ("m2", "0", "Thanks, I will start the rollout on Monday.", 0.22, {}),
        ("m1", "1", "The total is 40k and Bob owns the rollout.", 0.35, {}),
    ],
    "vendor": [
        ("m5", "0", "Following up on the vendor quote; the pilot budget may change.", 0.15, {}),
    ],
}


def _hits_for(query: str) -> list[tuple[str, str, str, float, dict[str, Any]]]:
    hits: list[tuple[str, str, str, float, dict[str, Any]]] = []
    for keyword, keyword_hits in _HITS.items():
        if keyword in query.casefold():
            hits.extend(keyword_hits)
    return hits


class _Queries:
    def search_message_segments(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        if "budget" not in query.casefold():
            return []
        rows = [
            {
                **_EMAILS["m2"],
                "ordinal": 1,
                "segment_type": "quoted_reply",
                "segment_text": _SEGMENTS["m2"][1]["text"],
                "score": 0.83,
            },
            {
                **_EMAILS["m5"],
                "ordinal": 0,
                "segment_type": "authored_body",
                "segment_text": _SEGMENTS["m5"][0]["text"],
                "score": 0.64,
            },
        ]
        return rows[:limit]

    def get_emails_full_batch(self, uids: list[str]) -> dict[str, dict[str, Any]]:
        return {uid: dict(_EMAILS[uid]) for uid in uids if uid in _EMAILS}

    def message_segments_for_emails(self, uids: list[str]) -> dict[str, list[dict[str, Any]]]:
        return {uid: [dict(row) for row in _SEGMENTS[uid]] for uid in uids if uid in _SEGMENTS}

    def message_segments_for_email(self, uid: str) -> list[dict[str, Any]]:
        return [dict(row) for row in _SEGMENTS.get(uid, [])]

    def get_thread_emails(self, conversation_id: str) -> list[dict[str, Any]]:
        return [dict(email) for email in _EMAILS.values() if email["conversation_id"] == conversation_id]

    def get_inferred_thread_emails(self, thread_id: str) -> list[dict[str, Any]]:
        return [dict(email) for email in _EMAILS.values() if email.get("inferred_thread_id") == thread_id]


class _Attachments:
    def attachments_for_email(self, uid: str) -> list[dict[str, Any]]:
        if uid != "m4":
            return []
        return [
            {
                "name": "costs.xlsx",
                "attachment_id": "att-1",
                "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "size": 2048,
                "content_sha256": "0" * 64,
            }
        ]


class _Events:
    def event_records_for_uids(self, uids: list[str]) -> dict[str, list[dict[str, Any]]]:
        return {"m3": [{"event_type": "meeting", "date": "2026-03-09"}]} if "m3" in uids else {}


class _Entities:
    def entity_occurrences_for_uids(self, uids: list[str]) -> dict[str, list[dict[str, Any]]]:
        return {"m1": [{"entity": "Bob", "entity_type": "person"}]} if "m1" in uids else {}


class _Database:
    def __init__(self) -> None:
        self.queries = _Queries()
        self.attachments = _Attachments()
        self.events = _Events()
        self.entities = _Entities()


class _Retriever:
    def __init__(self, database: _Database) -> None:
        self.email_db = database
        self.last_search_debug: dict[str, Any] = {}

    def search_filtered(self, *, query: str, top_k: int, **kwargs: Any) -> list[SearchResult]:
        suffix = "pilot costs" if "budget" in query.casefold() else ""
        self.last_search_debug = {
            "original_query": query,
            "executed_query": f"{query} {suffix}".strip(),
            "query_expansion_suffix": suffix,
            "used_query_expansion": bool(suffix),
            "expand_query_requested": bool(suffix),
            "use_hybrid": bool(kwargs.get("hybrid")),
            "use_rerank": bool(kwargs.get("rerank")),
            "fetch_size": top_k * 2,
            "retrieval_policy": {"mode": "synthetic"},
        }
        results = []
        for uid, chunk, text, distance, extra in _hits_for(query)[:top_k]:
            email = _EMAILS[uid]
            metadata = {
                "uid": uid,
                "subject": email["subject"],
                "sender_email": email["sender_email"],
                "sender_name": email["sender_name"],
                "date": email["date"],
                "conversation_id": email["conversation_id"],
                **extra,
            }
            results.append(SearchResult(chunk_id=f"{uid}__{chunk}", text=text, metadata=metadata, distance=distance))
        return results


class _Dependencies:
    def __init__(self) -> None:
        self.database = _Database()
        self.retriever = _Retriever(self.database)

    def get_retriever(self) -> _Retriever:
        return self.retriever

    def get_archive_database(self) -> _Database:
        return self.database

    async def offload(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)


def _result_view(result: Any) -> dict[str, Any]:
    return {
        "chunk_id": result.chunk_id,
        "text": result.text,
        "score": round(float(result.score), 6),
        "metadata": result.metadata,
    }


def _normalize(value: Any) -> Any:
    if isinstance(value, SearchResult):
        return _normalize(_result_view(value))
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, float):
        return round(value, 6)
    return value


def _run_case(monkeypatch, params: EmailAnswerContextInput) -> dict[str, Any]:
    """Run the public entry point and capture the payload plus the internal retrieval context."""
    import mailarium.investigation.answer_context.assembly as assembly

    original = assembly._search_across_query_lanes
    captured: dict[str, Any] = {}

    def _recording(**kwargs: Any) -> Any:
        results, lane_diagnostics, context = original(**kwargs)
        captured.update(results=results, lane_diagnostics=lane_diagnostics, context=context)
        return results, lane_diagnostics, context

    monkeypatch.setattr(assembly, "_search_across_query_lanes", _recording)
    payload = asyncio.run(build_answer_context_payload(_Dependencies(), params))
    return _normalize(
        {
            "payload": payload,
            "selected_results": captured["results"],
            "lane_diagnostics": captured["lane_diagnostics"],
            "retrieval_context": captured["context"],
        }
    )


def test_answer_context_single_and_multi_lane_payloads_match_snapshot(monkeypatch) -> None:
    """Single-lane, multi-lane, and scan-filtered answer contexts keep their recorded payloads."""
    settings = replace(Settings(), mcp_max_search_results=6, mcp_max_json_response_chars=500_000, mcp_model_profile="test")
    monkeypatch.setattr("mailarium.platform.settings.get_settings", lambda: settings)
    scan_id = "answer-context-lanes-scan"
    reset_session(scan_id)
    # Mark one message as already reviewed so the scan case excludes it from every lane.
    filter_seen(scan_id, [SearchResult(chunk_id="m1__0", text="seen", metadata={"uid": "m1"}, distance=0.0)])
    try:
        outputs = {
            "single_lane_expansion": _run_case(
                monkeypatch,
                EmailAnswerContextInput(question="What budget was approved for the pilot?", max_results=4),
            ),
            "single_lane_exact_forensic": _run_case(
                monkeypatch,
                EmailAnswerContextInput(
                    question="What exactly did Alice write about the rollout?",
                    max_results=3,
                    evidence_mode="forensic",
                ),
            ),
            "multi_lane": _run_case(
                monkeypatch,
                EmailAnswerContextInput(
                    question="Who owns the pilot rollout and budget?",
                    max_results=5,
                    query_lanes=["pilot budget approval", "rollout owner meeting", "vendor quote"],
                    evidence_mode="hybrid",
                ),
            ),
            "multi_lane_scan_filtered": _run_case(
                monkeypatch,
                EmailAnswerContextInput(
                    question="Who owns the pilot rollout and budget?",
                    max_results=5,
                    query_lanes=["pilot budget approval", "rollout owner meeting"],
                    scan_id=scan_id,
                ),
            ),
        }
    finally:
        reset_session(scan_id)

    if os.environ.get("MAILARIUM_UPDATE_SNAPSHOTS") == "1":
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(outputs, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        return
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert sorted(outputs) == sorted(expected)
    for key, value in expected.items():
        assert outputs[key] == value, key
