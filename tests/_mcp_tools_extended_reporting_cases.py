# ruff: noqa: F401,I001
"""Extended tests for low-coverage MCP tool modules.

Tests cover: threads.py, reporting.py, temporal.py, data_quality.py,
browse.py, and scan.py. Each test mocks deps (retriever + email_db),
calls the async tool function, and asserts valid JSON with expected keys.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from src.config import get_settings
from src.mcp_server import _offload
from src.retriever import SearchResult
from src.sanitization import sanitize_untrusted_text

# ── Shared Test Infrastructure ───────────────────────────────

from .helpers.mcp_tool_extended_fakes import FakeMCP, MockDeps, MockEmailDB, MockRetriever, _make_result, _register_module


class TestReportingTools:
    @pytest.mark.asyncio
    async def test_writing_analysis_single_sender(self):
        from src.tools import reporting

        fake_mcp = _register_module(reporting)
        fn = fake_mcp._tools["email_report"]

        from src.mcp_models import EmailReportInput

        params = EmailReportInput(type="writing", sender="employee@example.test", limit=10)
        result = await fn(params)
        data = json.loads(result)

        # Either returns a profile or an error (no emails long enough)
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_writing_analysis_no_sender_compares_top(self):
        from src.tools import reporting

        fake_mcp = _register_module(reporting)
        fn = fake_mcp._tools["email_report"]

        from src.mcp_models import EmailReportInput

        params = EmailReportInput(type="writing", limit=5)
        result = await fn(params)
        data = json.loads(result)
        # Returns list of profiles or error
        assert isinstance(data, (list, dict))

    @pytest.mark.asyncio
    async def test_archive_report(self, tmp_path, monkeypatch):
        from src.tools import reporting

        fake_mcp = _register_module(reporting)
        fn = fake_mcp._tools["email_report"]

        output_file = str(tmp_path / "report.html")
        monkeypatch.setenv("EMAIL_RAG_ALLOWED_OUTPUT_ROOTS", str(tmp_path))

        from src.mcp_models import EmailReportInput

        params = EmailReportInput(type="archive", output_path=output_file)

        # Mock ReportGenerator since it requires full DB setup
        with patch("src.report_generator.ReportGenerator") as mock_gen_cls:
            mock_gen = MagicMock()
            mock_gen_cls.return_value = mock_gen
            result = await fn(params)
            data = json.loads(result)
            assert data.get("status") == "ok"
            assert data.get("output_path") == output_file

    @pytest.mark.asyncio
    async def test_archive_report_surfaces_degraded_status(self, tmp_path, monkeypatch):
        from src.tools import reporting

        fake_mcp = _register_module(reporting)
        fn = fake_mcp._tools["email_report"]

        output_file = str(tmp_path / "report.html")
        monkeypatch.setenv("EMAIL_RAG_ALLOWED_OUTPUT_ROOTS", str(tmp_path))

        from src.mcp_models import EmailReportInput

        params = EmailReportInput(type="archive", output_path=output_file)

        with patch("src.report_generator.ReportGenerator") as mock_gen_cls:
            mock_gen = MagicMock()
            mock_gen.last_warnings = ["monthly_volume unavailable: RuntimeError"]
            mock_gen_cls.return_value = mock_gen
            result = await fn(params)
            data = json.loads(result)
            assert data.get("status") == "degraded"
            assert data.get("warnings") == ["monthly_volume unavailable: RuntimeError"]

    @pytest.mark.asyncio
    async def test_archive_report_returns_error_when_rendering_fails(self, tmp_path, monkeypatch):
        from src.report_generator import ReportGenerationError
        from src.tools import reporting

        fake_mcp = _register_module(reporting)
        fn = fake_mcp._tools["email_report"]

        output_file = str(tmp_path / "report.html")
        monkeypatch.setenv("EMAIL_RAG_ALLOWED_OUTPUT_ROOTS", str(tmp_path))

        from src.mcp_models import EmailReportInput

        params = EmailReportInput(type="archive", output_path=output_file)

        with patch("src.report_generator.ReportGenerator") as mock_gen_cls:
            mock_gen = MagicMock()
            mock_gen.generate.side_effect = ReportGenerationError(
                "Jinja2 is required for report generation. Run: pip install jinja2"
            )
            mock_gen_cls.return_value = mock_gen
            result = await fn(params)
            data = json.loads(result)
            assert data.get("success") is False
            assert "Jinja2 is required" in data.get("error", "")

    @pytest.mark.asyncio
    async def test_invalid_report_type(self):
        from pydantic import ValidationError

        from src.mcp_models import EmailReportInput

        with pytest.raises(ValidationError, match="type"):
            EmailReportInput.model_validate({"type": "invalid_type"})


class TestTemporalTools:
    @pytest.mark.asyncio
    async def test_volume_analysis(self):
        from src.tools import temporal

        fake_mcp = _register_module(temporal)
        fn = fake_mcp._tools["email_temporal"]

        from src.mcp_models import EmailTemporalInput

        with patch("src.temporal_analysis.TemporalAnalyzer") as mock_cls:
            mock_analyzer = MagicMock()
            mock_analyzer.volume_over_time.return_value = [
                {"period": "2025-06-01", "count": 5},
                {"period": "2025-06-02", "count": 3},
            ]
            mock_cls.return_value = mock_analyzer

            params = EmailTemporalInput(analysis="volume", period="day")
            result = await fn(params)
            data = json.loads(result)

            assert isinstance(data, list)
            assert len(data) == 2
            assert data[0]["period"] == "2025-06-01"

    @pytest.mark.asyncio
    async def test_activity_heatmap(self):
        from src.tools import temporal

        fake_mcp = _register_module(temporal)
        fn = fake_mcp._tools["email_temporal"]

        from src.mcp_models import EmailTemporalInput

        with patch("src.temporal_analysis.TemporalAnalyzer") as mock_cls:
            mock_analyzer = MagicMock()
            mock_analyzer.activity_heatmap.return_value = {
                "Monday": {9: 5, 10: 3},
                "Tuesday": {14: 7},
            }
            mock_cls.return_value = mock_analyzer

            params = EmailTemporalInput(analysis="activity")
            result = await fn(params)
            data = json.loads(result)

            assert "Monday" in data
            assert "Tuesday" in data

    @pytest.mark.asyncio
    async def test_response_times(self):
        from src.tools import temporal

        fake_mcp = _register_module(temporal)
        fn = fake_mcp._tools["email_temporal"]

        from src.mcp_models import EmailTemporalInput

        with patch("src.temporal_analysis.TemporalAnalyzer") as mock_cls:
            mock_analyzer = MagicMock()
            mock_analyzer.response_times.return_value = [
                {"sender": "employee@example.test", "avg_hours": 2.5},
            ]
            mock_cls.return_value = mock_analyzer

            params = EmailTemporalInput(analysis="response_times", limit=10)
            result = await fn(params)
            data = json.loads(result)

            assert isinstance(data, list)
            assert data[0]["sender"] == "employee@example.test"

    @pytest.mark.asyncio
    async def test_invalid_analysis_type(self):
        from pydantic import ValidationError

        from src.mcp_models import EmailTemporalInput

        with pytest.raises(ValidationError, match="analysis"):
            EmailTemporalInput.model_validate({"analysis": "invalid"})


class TestDataQualityTools:
    @pytest.mark.asyncio
    async def test_language_stats(self):
        from src.tools import data_quality

        fake_mcp = _register_module(data_quality)
        fn = fake_mcp._tools["email_quality"]

        from src.mcp_models import EmailQualityInput

        params = EmailQualityInput(check="languages")
        result = await fn(params)
        data = json.loads(result)

        assert "languages" in data
        assert data["coverage"]["total_emails"] >= data["coverage"]["labeled_emails"]
        assert len(data["languages"]) > 0
        assert data["languages"][0]["language"] == "en"
        assert "confidence_breakdown" in data
        assert data["coverage"]["language_metadata_emails"] >= data["coverage"]["labeled_emails"]
        assert data["coverage"]["low_confidence_labeled_emails"] == 0
        assert isinstance(data["caveats"], list)

    @pytest.mark.asyncio
    async def test_sentiment_overview(self):
        from src.tools import data_quality

        fake_mcp = _register_module(data_quality)
        fn = fake_mcp._tools["email_quality"]

        from src.mcp_models import EmailQualityInput

        params = EmailQualityInput(check="sentiment")
        result = await fn(params)
        data = json.loads(result)

        assert "sentiments" in data
        assert len(data["sentiments"]) > 0

    @pytest.mark.asyncio
    async def test_duplicate_detection(self):
        from src.tools import data_quality

        fake_mcp = _register_module(data_quality)
        fn = fake_mcp._tools["email_quality"]

        from src.mcp_models import EmailQualityInput

        with patch("src.dedup_detector.DuplicateDetector") as mock_cls:
            mock_detector = MagicMock()
            mock_detector.find_duplicates.return_value = [{"uid_a": "uid-1", "uid_b": "uid-2", "similarity": 0.92}]
            mock_cls.return_value = mock_detector

            params = EmailQualityInput(check="duplicates", threshold=0.85, limit=50)
            result = await fn(params)
            data = json.loads(result)

            assert "count" in data
            assert "duplicates" in data
            assert data["count"] == 1

    @pytest.mark.asyncio
    async def test_invalid_check_type(self):
        from pydantic import ValidationError

        from src.mcp_models import EmailQualityInput

        with pytest.raises(ValidationError, match="check"):
            EmailQualityInput.model_validate({"check": "nonexistent"})

    @pytest.mark.asyncio
    async def test_languages_missing_column_graceful(self):
        """When the column doesn't exist, the tool returns an instructive error."""
        from src.tools import data_quality

        class NoDB:
            """Stub DB whose conn raises OperationalError on any query."""

            class conn:
                @staticmethod
                def execute(*args):
                    raise sqlite3.OperationalError("no such column: detected_language")

        old_db = MockDeps._email_db
        MockDeps._email_db = cast(Any, NoDB())
        try:
            fake_mcp = _register_module(data_quality)
            fn = fake_mcp._tools["email_quality"]

            from src.mcp_models import EmailQualityInput

            params = EmailQualityInput(check="languages")
            result = await fn(params)
            data = json.loads(result)
            assert "error" in data
            assert "reingest" in data["error"].lower() or "language" in data["error"].lower()
        finally:
            MockDeps._email_db = cast(Any, old_db)
