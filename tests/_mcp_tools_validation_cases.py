# ruff: noqa: F401
import json
import sqlite3

import pytest
from pydantic import ValidationError

from src.config import get_settings

from .helpers.mcp_tool_fakes import _BasicRetriever, _make_result, _patch_search_deps


def test_structured_input_rejects_invalid_dates():
    from src.mcp_models import EmailSearchStructuredInput

    with pytest.raises(ValidationError):
        EmailSearchStructuredInput(
            query="hello",
            date_from="2024/01/01",
        )


def test_structured_input_rejects_invalid_date_order():
    from src.mcp_models import EmailSearchStructuredInput

    with pytest.raises(ValidationError):
        EmailSearchStructuredInput(
            query="hello",
            date_from="2024-05-01",
            date_to="2024-01-01",
        )


def test_structured_input_rejects_invalid_min_score():
    from src.mcp_models import EmailSearchStructuredInput

    with pytest.raises(ValidationError):
        EmailSearchStructuredInput(
            query="hello",
            min_score=1.2,
        )


def test_structured_input_accepts_email_type():
    from src.mcp_models import EmailSearchStructuredInput

    params = EmailSearchStructuredInput(
        query="hello",
        email_type="forward",
    )
    assert params.email_type == "forward"


def test_ingest_input_accepts_extract_attachments_and_embed_images(tmp_path):
    from src.mcp_models import EmailIngestInput

    olm_path = tmp_path / "archive.olm"
    olm_path.write_text("fixture", encoding="utf-8")

    params = EmailIngestInput(
        olm_path=str(olm_path),
        extract_attachments=True,
        embed_images=True,
    )
    assert params.extract_attachments is True
    assert params.embed_images is True


def test_all_tool_modules_importable():
    """Smoke test: every tool module under src/tools/ imports cleanly."""
    from src.tools import (
        attachments,
        browse,
        data_quality,
        diagnostics,
        entities,
        evidence,
        network,
        reporting,
        temporal,
        threads,
        topics,
    )

    for module in [
        attachments,
        browse,
        data_quality,
        diagnostics,
        entities,
        evidence,
        network,
        reporting,
        temporal,
        threads,
        topics,
    ]:
        assert callable(module.register), f"{module.__name__} missing register()"


class TestAttachmentFilters:
    def test_matches_attachment_name_in_names(self):
        from src.result_filters import _matches_attachment_name
        from src.retriever import SearchResult

        r = SearchResult(chunk_id="x", text="", metadata={"attachment_names": "report.pdf, budget.xlsx"}, distance=0.1)
        assert _matches_attachment_name(r, "report") is True
        assert _matches_attachment_name(r, "slides") is False
        assert _matches_attachment_name(r, None) is True

    def test_matches_attachment_name_in_filename(self):
        from src.result_filters import _matches_attachment_name
        from src.retriever import SearchResult

        r = SearchResult(chunk_id="x", text="", metadata={"attachment_filename": "report.pdf"}, distance=0.1)
        assert _matches_attachment_name(r, "report") is True

    def test_matches_attachment_name_in_legacy_filename(self):
        from src.result_filters import _matches_attachment_name
        from src.retriever import SearchResult

        r = SearchResult(chunk_id="x", text="", metadata={"filename": "legacy_scan.png"}, distance=0.1)
        assert _matches_attachment_name(r, "scan") is True

    def test_matches_attachment_name_list_metadata(self):
        from src.result_filters import _matches_attachment_name
        from src.retriever import SearchResult

        r = SearchResult(chunk_id="x", text="", metadata={"attachment_names": ["report.pdf", "budget.xlsx"]}, distance=0.1)
        assert _matches_attachment_name(r, "budget") is True

    def test_matches_attachment_type(self):
        from src.result_filters import _matches_attachment_type
        from src.retriever import SearchResult

        r = SearchResult(chunk_id="x", text="", metadata={"attachment_names": "report.pdf, budget.xlsx"}, distance=0.1)
        assert _matches_attachment_type(r, "pdf") is True
        assert _matches_attachment_type(r, "xlsx") is True
        assert _matches_attachment_type(r, "docx") is False
        assert _matches_attachment_type(r, None) is True

    def test_matches_attachment_type_with_dot(self):
        from src.result_filters import _matches_attachment_type
        from src.retriever import SearchResult

        r = SearchResult(chunk_id="x", text="", metadata={"attachment_filename": "slides.pptx"}, distance=0.1)
        assert _matches_attachment_type(r, ".pptx") is True
        assert _matches_attachment_type(r, "pptx") is True

    def test_matches_attachment_type_with_legacy_filename(self):
        from src.result_filters import _matches_attachment_type
        from src.retriever import SearchResult

        r = SearchResult(chunk_id="x", text="", metadata={"filename": "slide-deck.pptx"}, distance=0.1)
        assert _matches_attachment_type(r, "pptx") is True

    def test_matches_attachment_type_no_substring_false_positive(self):
        """Filtering for .doc should NOT match .docx files."""
        from src.result_filters import _matches_attachment_type
        from src.retriever import SearchResult

        r = SearchResult(chunk_id="x", text="", metadata={"attachment_names": "report.docx"}, distance=0.1)
        assert _matches_attachment_type(r, "doc") is False
        assert _matches_attachment_type(r, "docx") is True

    def test_matches_category_no_substring_false_positive(self):
        """Filtering for 'urgent' should NOT match 'Non-Urgent'."""
        from src.result_filters import _matches_category
        from src.retriever import SearchResult

        r = SearchResult(chunk_id="x", text="", metadata={"categories": "Non-Urgent, Important"}, distance=0.1)
        assert _matches_category(r, "urgent") is False
        assert _matches_category(r, "Non-Urgent") is True
        assert _matches_category(r, "Important") is True
        assert _matches_category(r, "import") is False
