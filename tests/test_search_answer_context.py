import json
from typing import Any, cast


def test_weak_message_semantics_describes_source_shell_message():
    from src.formatting import weak_message_semantics

    weak_message = weak_message_semantics(
        {
            "body_kind": "content",
            "body_empty_reason": "source_shell_only",
            "recovery_strategy": "source_shell_summary",
            "recovery_confidence": 0.2,
        }
    )

    assert weak_message is not None
    assert weak_message["code"] == "source_shell_only"
    assert weak_message["label"] == "Source-shell message"
    assert "visible authored text" in weak_message["explanation"]


def test_search_across_query_lanes_preserves_lane_provenance_after_scan_dedupe(monkeypatch):
    from src.retriever_models import SearchResult
    from src.tools.search_answer_context_runtime import _search_across_query_lanes

    result = SearchResult(
        chunk_id="chunk-1",
        text="Please document the restriction in writing.",
        metadata={
            "uid": "uid-1",
            "subject": "Restriction note",
            "sender_email": "employee@example.test",
            "sender_name": "Alice",
            "date": "2025-01-01",
            "conversation_id": "conv-1",
        },
        distance=0.1,
    )

    class _Retriever:
        def __init__(self):
            self.calls = 0
            self.last_search_debug = {"used_query_expansion": False}

        def search_filtered(self, **kwargs):
            self.calls += 1
            self.last_search_debug = {"executed_query": kwargs["query"], "used_query_expansion": False}
            return [result]

        email_db = None

    seen_calls = {"count": 0}

    def fake_filter_seen(_scan_id, results):
        seen_calls["count"] += 1
        if seen_calls["count"] == 1:
            return results, {"excluded_count": 0}
        return [], {"excluded_count": len(results)}

    monkeypatch.setattr("src.scan_session.filter_seen", fake_filter_seen)

    merged, _lane_diagnostics, summary = _search_across_query_lanes(
        retriever=_Retriever(),
        search_kwargs={"query": "restriction note"},
        query_lanes=["restriction note", "document restriction"],
        top_k=5,
        scan_id="scan-1",
        lane_top_k=5,
        reserve_per_lane=1,
        bank_limit=5,
    )

    assert len(merged) == 1
    assert merged[0].metadata["matched_query_lanes"] == ["lane_1", "lane_2"]
    assert merged[0].metadata["matched_query_queries"] == ["restriction note", "document restriction"]
    assert summary["evidence_bank"][0]["matched_query_lanes"] == ["lane_1", "lane_2"]


def test_search_across_query_lanes_keeps_body_and_attachment_hits_from_same_uid():
    from src.retriever_models import SearchResult
    from src.tools.search_answer_context_runtime import _search_across_query_lanes

    body_result = SearchResult(
        chunk_id="chunk-body",
        text="Please document the restriction in writing.",
        metadata={
            "uid": "uid-1",
            "subject": "Restriction note",
            "sender_email": "employee@example.test",
            "sender_name": "Alice",
            "date": "2025-01-01",
            "conversation_id": "conv-1",
        },
        distance=0.1,
    )
    attachment_result = SearchResult(
        chunk_id="chunk-attachment",
        text="Attached protocol records the same restriction.",
        metadata={
            "uid": "uid-1",
            "subject": "Restriction note",
            "sender_email": "employee@example.test",
            "sender_name": "Alice",
            "date": "2025-01-01",
            "conversation_id": "conv-1",
            "attachment_filename": "protocol.pdf",
        },
        distance=0.12,
    )

    class _Retriever:
        def __init__(self):
            self.last_search_debug = {"used_query_expansion": False}

        def search_filtered(self, **kwargs):
            self.last_search_debug = {"executed_query": kwargs["query"], "used_query_expansion": False}
            if kwargs["query"] == "restriction note":
                return [body_result]
            return [attachment_result]

        email_db = None

    merged, _lane_diagnostics, summary = _search_across_query_lanes(
        retriever=_Retriever(),
        search_kwargs={"query": "restriction note"},
        query_lanes=["restriction note", "protocol attachment"],
        top_k=5,
        lane_top_k=5,
        reserve_per_lane=1,
        bank_limit=5,
    )

    assert len(merged) == 2
    assert {item.metadata.get("chunk_id", item.chunk_id) for item in merged} == {"chunk-body", "chunk-attachment"}
    assert {item["candidate_kind"] for item in summary["evidence_bank"]} == {"body", "attachment"}


def test_search_across_query_lanes_applies_lane_diversity_to_evidence_bank():
    from src.retriever_models import SearchResult
    from src.tools.search_answer_context_runtime import _search_across_query_lanes

    lane_1_results = [
        SearchResult(
            chunk_id=f"lane1-{index}",
            text=f"Lane 1 result {index}",
            metadata={
                "uid": f"uid-l1-{index}",
                "subject": f"Lane 1 result {index}",
                "sender_email": "lane1@example.com",
                "date": f"2025-01-0{index + 1}",
                "conversation_id": f"conv-l1-{index}",
            },
            distance=0.1 + index * 0.01,
        )
        for index in range(3)
    ]
    lane_2_result = SearchResult(
        chunk_id="lane2-1",
        text="Lane 2 result",
        metadata={
            "uid": "uid-l2-1",
            "subject": "Lane 2 result",
            "sender_email": "lane2@example.com",
            "date": "2025-01-04",
            "conversation_id": "conv-l2-1",
        },
        distance=0.2,
    )

    class _Retriever:
        def __init__(self):
            self.last_search_debug = {"used_query_expansion": False}

        def search_filtered(self, **kwargs):
            self.last_search_debug = {"executed_query": kwargs["query"], "used_query_expansion": False}
            if kwargs["query"] == "lane one":
                return lane_1_results
            return [lane_2_result]

        email_db = None

    _merged, _lane_diagnostics, summary = _search_across_query_lanes(
        retriever=_Retriever(),
        search_kwargs={"query": "lane one"},
        query_lanes=["lane one", "lane two"],
        top_k=2,
        lane_top_k=3,
        reserve_per_lane=1,
        bank_limit=2,
    )

    assert len(summary["evidence_bank"]) == 2
    assert {tuple(item["matched_query_lanes"]) for item in summary["evidence_bank"]} == {("lane_1",), ("lane_2",)}


async def test_build_answer_context_payload_uses_preloaded_evidence_rows() -> None:
    from src.mcp_models import EmailAnswerContextInput
    from src.tools.search_answer_context import build_answer_context_payload

    class _Retriever:
        email_db = None

        @staticmethod
        def search_filtered(**kwargs):
            raise AssertionError(f"search_filtered should not run when preloaded evidence rows exist: {kwargs}")

    class _DB:
        conn = None

        @staticmethod
        def get_emails_full_batch(uids):
            assert uids == ["uid-preloaded", "uid-preloaded"]
            return {
                "uid-preloaded": {
                    "uid": "uid-preloaded",
                    "body_text": "Preloaded answer-bearing body text.",
                    "normalized_body_source": "body_text_html",
                    "conversation_id": "conv-preloaded",
                    "to": ["alex@example.org"],
                    "cc": [],
                    "bcc": [],
                    "reply_context_from": "manager@example.org",
                    "reply_context_to_json": "[]",
                }
            }

        @staticmethod
        def get_thread_emails(conversation_id):
            assert conversation_id == "conv-preloaded"
            return []

        @staticmethod
        def attachments_for_email(uid):
            assert uid == "uid-preloaded"
            return []

    class _Deps:
        DB_UNAVAILABLE = json.dumps({"error": "SQLite database not available."})

        @staticmethod
        def get_retriever():
            return _Retriever()

        @staticmethod
        def get_email_db():
            return _DB()

        @staticmethod
        async def offload(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        @staticmethod
        def sanitize(text: str) -> str:
            return text

        @staticmethod
        def tool_annotations(title: str):
            return {"title": title}

        @staticmethod
        def write_tool_annotations(title: str):
            return {"title": title}

        @staticmethod
        def idempotent_write_annotations(title: str):
            return {"title": title}

    payload = await build_answer_context_payload(
        cast(Any, _Deps()),
        EmailAnswerContextInput(question="Which record is strongest?", max_results=2),
        preloaded_evidence_rows=[
            {
                "uid": "uid-preloaded",
                "source_id": "email:uid-preloaded",
                "candidate_kind": "body",
                "subject": "Preloaded email",
                "sender_email": "manager@example.org",
                "sender_name": "Morgan Manager",
                "date": "2026-03-11T10:00:00",
                "conversation_id": "conv-preloaded",
                "score": 0.91,
                "snippet": "Preloaded answer-bearing body text.",
                "verification_status": "retrieval_exact",
                "score_calibration": "calibrated",
                "provenance": {"evidence_handle": "email:uid-preloaded"},
            },
            {
                "uid": "uid-preloaded",
                "source_id": "attachment:uid-preloaded:note.pdf",
                "candidate_kind": "attachment",
                "subject": "Preloaded email",
                "sender_email": "manager@example.org",
                "sender_name": "Morgan Manager",
                "date": "2026-03-11T10:00:00",
                "conversation_id": "conv-preloaded",
                "score": 0.88,
                "snippet": "Attached note excerpt.",
                "verification_status": "attachment_reference",
                "attachment": {"filename": "note.pdf", "source_type_hint": "attachment", "text_available": True},
                "provenance": {"evidence_handle": "attachment:uid-preloaded:note.pdf"},
            },
        ],
    )

    assert payload["count"] == 2
    assert payload["candidates"][0]["source_id"] == "email:uid-preloaded"
    assert payload["attachment_candidates"][0]["source_id"] == "attachment:uid-preloaded:note.pdf"
