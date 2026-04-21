# ruff: noqa: F401,I001
"""Extended tests for low-coverage MCP tool modules.

Tests cover: threads.py, reporting.py, temporal.py, data_quality.py,
browse.py, and scan.py. Each test mocks deps (retriever + email_db),
calls the async tool function, and asserts valid JSON with expected keys.
"""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from src.config import get_settings
from src.mcp_server import _offload
from src.retriever import SearchResult
from src.sanitization import sanitize_untrusted_text

# ── Shared Test Infrastructure ───────────────────────────────

from .helpers.mcp_tool_extended_fakes import FakeMCP, MockDeps, MockEmailDB, MockRetriever, _make_result, _register_module


class TestSearchTools:
    @pytest.mark.asyncio
    async def test_email_answer_context_registered_and_returns_candidates(self):
        from src.tools import search

        class SegmentMatchingRetriever(MockRetriever):
            def search_filtered(self, query="", top_k=10, **kwargs):
                return [_make_result(uid="uid-1", text="We decided to go with vendor A.")]

        fake_mcp = FakeMCP()
        old_retriever = MockDeps._retriever
        MockDeps._retriever = SegmentMatchingRetriever()
        try:
            search.register(fake_mcp, MockDeps)
            fn = fake_mcp._tools["email_answer_context"]

            from src.mcp_models import EmailAnswerContextInput

            params = EmailAnswerContextInput(question="What was decided?", max_results=2)
            result = await fn(params)
            data = json.loads(result)

            assert data["question"] == "What was decided?"
            assert data["count"] == 1
            assert data["candidates"][0]["uid"] == "uid-1"
            assert data["candidates"][0]["follow_up"]["uid"] == "uid-1"
            assert data["evidence_mode"]["requested"] == "retrieval"
            assert data["candidates"][0]["body_render_mode"] == "retrieval"
            assert data["candidates"][0]["body_render_source"] == "body_text"
            assert data["candidates"][0]["verification_status"] == "retrieval_exact"
            assert data["candidates"][0]["provenance"]["uid"] == "uid-1"
            assert data["candidates"][0]["provenance"]["segment_ordinal"] == 0
            assert data["candidates"][0]["provenance"]["snippet_start"] == 0
            assert data["candidates"][0]["provenance"]["snippet_end"] == 31
            assert data["candidates"][0]["provenance"]["evidence_handle"].startswith("email:uid-1:retrieval:body_text:0:31:0")
        finally:
            MockDeps._retriever = old_retriever

    @pytest.mark.asyncio
    async def test_email_answer_context_registered_forensic_mode_uses_forensic_render(self):
        from src.tools import search

        class ForensicDB(MockEmailDB):
            def __init__(self):
                super().__init__()
                self.conn.execute(
                    "UPDATE emails SET forensic_body_text = ?, forensic_body_source = ? WHERE uid = ?",
                    ("Quoted header\nWe decided to go with vendor A.\nRegards", "raw_body_html", "uid-1"),
                )
                self.conn.commit()

        class SegmentMatchingRetriever(MockRetriever):
            def search_filtered(self, query="", top_k=10, **kwargs):
                return [_make_result(uid="uid-1", text="We decided to go with vendor A.")]

        fake_mcp = FakeMCP()
        old_retriever = MockDeps._retriever
        old_db = MockDeps._email_db
        MockDeps._retriever = SegmentMatchingRetriever()
        MockDeps._email_db = ForensicDB()
        try:
            search.register(fake_mcp, MockDeps)
            fn = fake_mcp._tools["email_answer_context"]

            from src.mcp_models import EmailAnswerContextInput

            params = EmailAnswerContextInput(question="What was decided?", evidence_mode="forensic")
            result = await fn(params)
            data = json.loads(result)

            assert data["evidence_mode"]["requested"] == "forensic"
            assert data["candidates"][0]["body_render_mode"] == "forensic"
            assert data["candidates"][0]["body_render_source"] == "raw_body_html"
            assert data["candidates"][0]["verification_status"] == "forensic_exact"
            assert data["candidates"][0]["provenance"]["evidence_handle"].startswith("email:uid-1:forensic:raw_body_html:")
        finally:
            MockDeps._retriever = old_retriever
            MockDeps._email_db = old_db

    @pytest.mark.asyncio
    async def test_email_answer_context_registered_handles_empty_results(self):
        from src.tools import search

        class EmptyRetriever(MockRetriever):
            def search_filtered(self, query="", top_k=10, **kwargs):
                return []

        fake_mcp = FakeMCP()
        old_retriever = MockDeps._retriever
        MockDeps._retriever = EmptyRetriever()
        try:
            search.register(fake_mcp, MockDeps)
            fn = fake_mcp._tools["email_answer_context"]

            from src.mcp_models import EmailAnswerContextInput

            params = EmailAnswerContextInput(question="Did anyone mention the maintenance window?")
            result = await fn(params)
            data = json.loads(result)

            assert data["count"] == 0
            assert data["candidates"] == []
            assert data["attachment_candidates"] == []
            assert data["conversation_groups"] == []
            assert "message" in data
        finally:
            MockDeps._retriever = old_retriever

    @pytest.mark.asyncio
    async def test_email_answer_context_registered_separates_attachment_candidates(self):
        from src.tools import search

        class AttachmentRetriever(MockRetriever):
            def search_filtered(self, query="", top_k=10, **kwargs):
                return [
                    SearchResult(
                        chunk_id="uid-1__att_budget__0",
                        text='[Attachment: budget.xlsx from email "Budget Review" (2025-06-01)]\n\nBudget totals are attached.',
                        metadata={
                            "uid": "uid-1",
                            "subject": "Budget Review",
                            "sender_email": "employee@example.test",
                            "sender_name": "Alice",
                            "date": "2025-06-01",
                            "conversation_id": "conv-1",
                            "is_attachment": "True",
                            "parent_uid": "uid-1",
                            "attachment_filename": "budget.xlsx",
                        },
                        distance=0.12,
                    )
                ]

        fake_mcp = FakeMCP()
        old_retriever = MockDeps._retriever
        MockDeps._retriever = AttachmentRetriever()
        try:
            search.register(fake_mcp, MockDeps)
            fn = fake_mcp._tools["email_answer_context"]

            from src.mcp_models import EmailAnswerContextInput

            result = await fn(EmailAnswerContextInput(question="What is in the budget spreadsheet?"))
            data = json.loads(result)

            assert data["count"] == 1
            assert data["counts"] == {"body": 0, "attachments": 1, "total": 1}
            assert data["candidates"] == []
            assert len(data["attachment_candidates"]) == 1
            candidate = data["attachment_candidates"][0]
            assert candidate["uid"] == "uid-1"
            assert candidate["attachment"]["filename"] == "budget.xlsx"
            assert candidate["attachment"]["mime_type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            assert candidate["attachment"]["size"] == 2048
            assert candidate["attachment"]["extraction_state"] == "text_extracted"
            assert candidate["attachment"]["text_available"] is True
            assert candidate["attachment"]["ocr_used"] is False
            assert candidate["attachment"]["failure_reason"] is None
            assert candidate["attachment"]["evidence_strength"] == "strong_text"
            assert candidate["attachment"]["is_inline"] is False
            assert candidate["follow_up"]["uid"] == "uid-1"
            assert candidate["provenance"]["evidence_handle"].startswith("attachment:uid-1:budget.xlsx:")
        finally:
            MockDeps._retriever = old_retriever

    @pytest.mark.asyncio
    async def test_email_answer_context_registered_surfaces_ocr_attachment_state(self):
        from src.tools import search

        class OCRAttachmentRetriever(MockRetriever):
            def search_filtered(self, query="", top_k=10, **kwargs):
                return [
                    SearchResult(
                        chunk_id="uid-ocr-1__img_scan__0",
                        text='[Attachment: invoice-scan.png from email "Invoice" (2025-06-01)]\n\nInvoice total 120 EUR.',
                        metadata={
                            "uid": "uid-ocr-1",
                            "subject": "Invoice",
                            "sender_email": "employee@example.test",
                            "sender_name": "Alice",
                            "date": "2025-06-01",
                            "conversation_id": "",
                            "is_attachment": "True",
                            "attachment_filename": "invoice-scan.png",
                            "extraction_state": "ocr_text_extracted",
                        },
                        distance=0.12,
                    )
                ]

        fake_mcp = FakeMCP()
        old_retriever = MockDeps._retriever
        MockDeps._retriever = OCRAttachmentRetriever()
        try:
            search.register(fake_mcp, MockDeps)
            fn = fake_mcp._tools["email_answer_context"]

            from src.mcp_models import EmailAnswerContextInput

            result = await fn(EmailAnswerContextInput(question="What does the invoice scan say?"))
            data = json.loads(result)

            candidate = data["attachment_candidates"][0]
            assert candidate["attachment"]["extraction_state"] == "ocr_text_extracted"
            assert candidate["attachment"]["text_available"] is True
            assert candidate["attachment"]["ocr_used"] is True
            assert candidate["attachment"]["failure_reason"] is None
            assert candidate["attachment"]["evidence_strength"] == "strong_text"
        finally:
            MockDeps._retriever = old_retriever

    @pytest.mark.asyncio
    async def test_email_answer_context_registered_adds_conversation_groups(self):
        from src.tools import search

        class ThreadedRetriever(MockRetriever):
            def search_filtered(self, query="", top_k=10, **kwargs):
                return [
                    _make_result(
                        uid="uid-2",
                        text="Please send the updated report by Friday.",
                        sender="bob@example.com",
                        date="2025-06-02",
                        conversation_id="conv-1",
                        distance=0.12,
                    ),
                    _make_result(
                        uid="uid-1",
                        text="We decided to go with vendor A.",
                        sender="employee@example.test",
                        date="2025-06-01",
                        conversation_id="conv-1",
                        distance=0.2,
                    ),
                ]

        fake_mcp = FakeMCP()
        old_retriever = MockDeps._retriever
        MockDeps._retriever = ThreadedRetriever()
        try:
            search.register(fake_mcp, MockDeps)
            fn = fake_mcp._tools["email_answer_context"]

            from src.mcp_models import EmailAnswerContextInput

            result = await fn(EmailAnswerContextInput(question="What happened in the budget thread?", max_results=2))
            data = json.loads(result)

            assert len(data["conversation_groups"]) == 1
            group = data["conversation_groups"][0]
            assert group["conversation_id"] == "conv-1"
            assert group["top_uid"] == "uid-2"
            assert group["message_count"] == 2
            assert group["participants"] == ["employee@example.test", "bob@example.com"]
            assert group["date_range"] == {"first": "2025-06-01", "last": "2025-06-02"}
            assert group["matched_uids"] == ["uid-2", "uid-1"]
            assert data["candidates"][0]["conversation_context"]["conversation_id"] == "conv-1"
            assert data["candidates"][0]["conversation_context"]["message_count"] == 2
            assert data["candidates"][0]["conversation_context"]["top_uid"] == "uid-2"
        finally:
            MockDeps._retriever = old_retriever

    @pytest.mark.asyncio
    async def test_email_answer_context_registered_reports_ambiguity(self):
        from src.tools import search

        class AmbiguousRetriever(MockRetriever):
            def search_filtered(self, query="", top_k=10, **kwargs):
                return [
                    _make_result(
                        uid="uid-1",
                        text="We decided to go with vendor A.",
                        sender="employee@example.test",
                        date="2025-06-01",
                        conversation_id="conv-1",
                        distance=0.10,
                    ),
                    _make_result(
                        uid="uid-2",
                        text="Please send the updated report by Friday.",
                        sender="bob@example.com",
                        date="2025-06-02",
                        conversation_id="conv-2",
                        distance=0.11,
                    ),
                ]

        fake_mcp = FakeMCP()
        old_retriever = MockDeps._retriever
        MockDeps._retriever = AmbiguousRetriever()
        try:
            search.register(fake_mcp, MockDeps)
            fn = fake_mcp._tools["email_answer_context"]

            from src.mcp_models import EmailAnswerContextInput

            result = await fn(EmailAnswerContextInput(question="Which result is best?", max_results=2))
            data = json.loads(result)

            assert data["answer_quality"]["confidence_label"] == "ambiguous"
            assert data["answer_quality"]["ambiguity_reason"] == "close_top_scores"
            assert data["answer_quality"]["top_candidate_uid"] == "uid-1"
            assert data["answer_quality"]["alternative_candidates"] == ["uid-2"]
        finally:
            MockDeps._retriever = old_retriever

    @pytest.mark.asyncio
    async def test_email_answer_context_registered_adds_timeline(self):
        from src.tools import search

        class TemporalRetriever(MockRetriever):
            def search_filtered(self, query="", top_k=10, **kwargs):
                return [
                    _make_result(
                        uid="uid-2",
                        text="Decision made on the rollout.",
                        sender="bob@example.com",
                        date="2025-06-03",
                        conversation_id="conv-1",
                        distance=0.09,
                    ),
                    _make_result(
                        uid="uid-1",
                        text="Initial request for the rollout.",
                        sender="employee@example.test",
                        date="2025-06-01",
                        conversation_id="conv-1",
                        distance=0.12,
                    ),
                    _make_result(
                        uid="uid-3",
                        text="Follow-up confirmation after rollout.",
                        sender="carol@example.com",
                        date="2025-06-05",
                        conversation_id="conv-1",
                        distance=0.15,
                    ),
                ]

        fake_mcp = FakeMCP()
        old_retriever = MockDeps._retriever
        old_db = MockDeps._email_db
        MockDeps._retriever = TemporalRetriever()
        try:
            search.register(fake_mcp, MockDeps)
            fn = fake_mcp._tools["email_answer_context"]

            from src.mcp_models import EmailAnswerContextInput

            result = await fn(EmailAnswerContextInput(question="How did the rollout evolve?", max_results=3))
            data = json.loads(result)

            assert data["timeline"]["event_count"] == 3
            assert data["timeline"]["date_range"] == {"first": "2025-06-01", "last": "2025-06-05"}
            assert data["timeline"]["first_uid"] == "uid-1"
            assert data["timeline"]["last_uid"] == "uid-3"
            assert data["timeline"]["key_transition_uid"] == "uid-2"
            assert [event["uid"] for event in data["timeline"]["events"]] == ["uid-1", "uid-2", "uid-3"]
        finally:
            MockDeps._retriever = old_retriever
            MockDeps._email_db = old_db

    @pytest.mark.asyncio
    async def test_email_answer_context_registered_adds_speaker_attribution(self):
        from src.tools import search

        class SpeakerRetriever(MockRetriever):
            def search_filtered(self, query="", top_k=10, **kwargs):
                return [
                    _make_result(
                        uid="uid-1",
                        text="We decided to go with vendor A.",
                        sender="employee@example.test",
                        date="2025-06-01",
                        conversation_id="conv-1",
                        distance=0.09,
                    )
                ]

        fake_mcp = FakeMCP()
        old_retriever = MockDeps._retriever
        MockDeps._retriever = SpeakerRetriever()
        try:
            search.register(fake_mcp, MockDeps)
            fn = fake_mcp._tools["email_answer_context"]

            from src.mcp_models import EmailAnswerContextInput

            result = await fn(EmailAnswerContextInput(question="Who said what about the vendor?", max_results=1))
            data = json.loads(result)

            attribution = data["candidates"][0]["speaker_attribution"]
            assert attribution["authored_speaker"]["email"] == "employee@example.test"
            assert attribution["quoted_blocks"][0]["speaker_email"] == "bob@example.com"
            assert attribution["quoted_blocks"][0]["source"] == "conversation_participant_exclusion"
            assert attribution["quoted_blocks"][0]["confidence"] == pytest.approx(0.5)
        finally:
            MockDeps._retriever = old_retriever
