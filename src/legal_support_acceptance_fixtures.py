"""Compatibility facade for realistic legal-support acceptance fixtures."""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
from typing import Any
from unittest.mock import patch

from . import legal_support_acceptance_cases as _cases
from . import legal_support_acceptance_projection as _projection
from .case_full_pack import execute_case_full_pack
from .legal_support_acceptance_context import build_fixture_answer_context
from .retriever_models import SearchResult

FIXTURE_CASES = _cases.FIXTURE_CASES
FIXTURE_ROOT = _cases.FIXTURE_ROOT
FullPackAcceptanceCase = _cases.FullPackAcceptanceCase
acceptance_case = _cases.acceptance_case
acceptance_case_dir = _cases.acceptance_case_dir
acceptance_case_ids = _cases.acceptance_case_ids
build_fixture_full_pack_input = _cases.build_fixture_full_pack_input
build_golden_projection = _projection.build_golden_projection


def _fixture_retrieval_terms(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9äöüß]+", str(text or "").casefold()) if len(token) >= 3}


def _fixture_retrieval_corpus(case_id: str) -> list[dict[str, Any]]:
    payload = build_fixture_answer_context(case_id)
    corpus: list[dict[str, Any]] = []
    for candidate in payload.get("candidates", []) or []:
        row = _fixture_candidate_row(candidate, case_id)
        if row:
            corpus.append(row)
    return corpus


def _fixture_candidate_row(candidate: object, case_id: str) -> dict[str, Any] | None:
    if not isinstance(candidate, dict):
        return None
    uid = str(candidate.get("uid") or "")
    if not uid:
        return None
    subject = str(candidate.get("subject") or "")
    snippet = str(candidate.get("snippet") or "")
    body_text = "\n".join(part for part in [subject, snippet] if part).strip()
    return {
        "uid": uid,
        "subject": subject,
        "sender_name": str(candidate.get("sender_name") or ""),
        "sender_email": str(candidate.get("sender_email") or ""),
        "date": str(candidate.get("date") or ""),
        "conversation_id": f"fixture:{case_id}:thread:1",
        "body_text": body_text,
        "forensic_body_text": body_text,
        "normalized_body_text": body_text,
        "to": ["employee@example.test"],
        "cc": [],
        "bcc": [],
        "reply_context_from": "",
        "reply_context_to": [],
        "message_id": f"<{uid}@fixture.local>",
        "references": [],
    }


class _FixtureRetrievalDB:
    def __init__(self, case_id: str):
        self._rows = _fixture_retrieval_corpus(case_id)
        self._by_uid = {str(row.get("uid") or ""): dict(row) for row in self._rows if str(row.get("uid") or "")}
        self._by_conversation: dict[str, list[dict[str, Any]]] = {}
        for row in self._rows:
            conversation_id = str(row.get("conversation_id") or "")
            self._by_conversation.setdefault(conversation_id, []).append(dict(row))
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            "CREATE TABLE message_segments ("
            "email_uid TEXT, ordinal INTEGER, segment_type TEXT, depth INTEGER, text TEXT, source_surface TEXT"
            ")"
        )
        for row in self._rows:
            self.conn.execute(
                "INSERT INTO message_segments ("
                "email_uid, ordinal, segment_type, depth, text, source_surface"
                ") VALUES (?, ?, ?, ?, ?, ?)",
                (str(row.get("uid") or ""), 1, "authored_text", 0, str(row.get("body_text") or ""), "body_text"),
            )
        self.conn.commit()

    def get_emails_full_batch(self, uids: list[str]) -> dict[str, dict[str, Any]]:
        return {uid: dict(self._by_uid[uid]) for uid in uids if uid in self._by_uid}

    def get_thread_emails(self, conversation_id: str) -> list[dict[str, Any]]:
        return [dict(row) for row in self._by_conversation.get(str(conversation_id or ""), [])]

    def attachments_for_email(self, uid: str) -> list[dict[str, Any]]:
        del uid
        return []


class _FixtureRetrievalRetriever:
    def __init__(self, case_id: str, *, email_db: _FixtureRetrievalDB):
        self._rows = _fixture_retrieval_corpus(case_id)
        self.email_db = email_db
        self.last_search_debug: dict[str, Any] = {"used_query_expansion": False}

    def search_filtered(self, query: str, top_k: int = 10, **kwargs: Any) -> list[SearchResult]:
        query_terms = _fixture_retrieval_terms(query)
        scored = _score_fixture_rows(self._rows, query_terms)
        scored.sort(key=lambda item: (-item[0], str(item[1].get("date") or ""), str(item[1].get("uid") or "")))
        selected = scored[: max(int(top_k or 0), 0)]
        self.last_search_debug = {
            "executed_query": query,
            "used_query_expansion": bool(kwargs.get("expand_query")),
            "original_query": query,
        }
        return [_fixture_search_result(score, row) for score, row in selected]

    def stats(self) -> dict[str, Any]:
        return {"total_emails": len(self._rows)}


def _score_fixture_rows(rows: list[dict[str, Any]], query_terms: set[str]) -> list[tuple[float, dict[str, Any]]]:
    scored: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        searchable = " ".join(str(row.get(key) or "") for key in ("subject", "sender_name", "sender_email", "body_text"))
        overlap = len(query_terms & _fixture_retrieval_terms(searchable))
        if query_terms and overlap <= 0:
            continue
        scored.append((min(0.2 + overlap * 0.12, 0.95), row))
    return scored


def _fixture_search_result(score: float, row: dict[str, Any]) -> SearchResult:
    metadata = {
        key: str(row.get(key) or "") for key in ("uid", "subject", "sender_email", "sender_name", "date", "conversation_id")
    }
    metadata.update({"normalized_body_source": "body_text", "score_kind": "semantic", "score_calibration": "calibrated"})
    return SearchResult(
        chunk_id=f"fixture:{row['uid']}:body",
        text=str(row.get("body_text") or ""),
        metadata=metadata,
        distance=max(0.0, 1.0 - float(score)),
    )


class _FixtureRetrievalDeps:
    def __init__(self, case_id: str):
        self._email_db = _FixtureRetrievalDB(case_id)
        self._retriever = _FixtureRetrievalRetriever(case_id, email_db=self._email_db)

    def get_retriever(self) -> _FixtureRetrievalRetriever:
        return self._retriever

    def get_email_db(self) -> _FixtureRetrievalDB:
        return self._email_db


async def execute_fixture_full_pack(
    case_id: str,
    *,
    output_path: str | None = None,
    blocked: bool = False,
    compile_only: bool = False,
) -> dict[str, Any]:
    """Execute the real full-pack workflow for one deterministic realistic fixture case."""

    async def _fake_build_answer_context(_deps: Any, _params: Any) -> str:
        return json.dumps(build_fixture_answer_context(case_id))

    async def _fake_build_answer_context_payload(_deps: Any, _params: Any, **kwargs: Any) -> dict[str, Any]:
        return build_fixture_answer_context(case_id)

    class _FixtureDeps:
        @staticmethod
        def get_email_db() -> None:
            return None

    params = build_fixture_full_pack_input(
        case_id,
        output_path=output_path,
        blocked=blocked,
        compile_only=compile_only,
    )
    with (
        patch("src.tools.search_answer_context.build_answer_context", _fake_build_answer_context),
        patch("src.tools.search_answer_context.build_answer_context_payload", _fake_build_answer_context_payload),
    ):
        payload = await execute_case_full_pack(_FixtureDeps(), params)
        payload["acceptance_lane"] = {
            "mode": "fixture_assembly",
            "retrieval_sensitive": False,
        }
        return payload


def execute_fixture_full_pack_sync(
    case_id: str,
    *,
    output_path: str | None = None,
    blocked: bool = False,
    compile_only: bool = False,
) -> dict[str, Any]:
    """Synchronous wrapper for script-driven acceptance/golden refresh flows."""
    return asyncio.run(
        execute_fixture_full_pack(
            case_id,
            output_path=output_path,
            blocked=blocked,
            compile_only=compile_only,
        )
    )


async def execute_retrieval_fixture_full_pack(
    case_id: str,
    *,
    output_path: str | None = None,
    blocked: bool = False,
    compile_only: bool = False,
) -> dict[str, Any]:
    """Execute one deterministic full-pack case through the real retrieval path."""
    params = build_fixture_full_pack_input(
        case_id,
        output_path=output_path,
        blocked=blocked,
        compile_only=compile_only,
    )
    payload = await execute_case_full_pack(_FixtureRetrievalDeps(case_id), params)
    payload["acceptance_lane"] = {
        "mode": "retrieval_fixture",
        "retrieval_sensitive": True,
        "corpus_email_count": len(_fixture_retrieval_corpus(case_id)),
    }
    return payload


def execute_retrieval_fixture_full_pack_sync(
    case_id: str,
    *,
    output_path: str | None = None,
    blocked: bool = False,
    compile_only: bool = False,
) -> dict[str, Any]:
    """Synchronous wrapper for deterministic retrieval-backed acceptance runs."""
    return asyncio.run(
        execute_retrieval_fixture_full_pack(
            case_id,
            output_path=output_path,
            blocked=blocked,
            compile_only=compile_only,
        )
    )
