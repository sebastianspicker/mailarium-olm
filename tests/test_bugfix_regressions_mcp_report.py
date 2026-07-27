"""MCP, CLI, and report regression tests split out from the RF8 catch-all."""

from __future__ import annotations

from html import escape as html_escape
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.helpers.web_app_fixtures import _sidebar_retriever


class TestP0SidebarHtmlEscape:
    """P0 fix #2 & #3: sidebar folder name and sender name html_escape."""

    def test_html_escape_in_folder_name(self):
        malicious_folder = '<script>alert("xss")</script>'
        escaped = html_escape(malicious_folder)
        assert "<script>" not in escaped
        assert "&lt;script&gt;" in escaped

    def test_html_escape_in_sender_name(self):
        malicious_sender = "<img src=x onerror=alert(1)>"
        escaped = html_escape(malicious_sender)
        assert "<img" not in escaped
        assert "&lt;img" in escaped

    def test_ampersand_escape(self):
        name = "R&D Department"
        escaped = html_escape(name)
        assert "&amp;" in escaped

    @patch("mailarium.web_app.st")
    def test_render_sidebar_escapes_folder_in_markdown(self, mock_st):
        from mailarium.web_app import render_sidebar

        retriever = _sidebar_retriever(
            mock_st,
            stats={
                "total_emails": 10,
                "total_chunks": 20,
                "unique_senders": 5,
                "date_range": {"earliest": "2024-01-01", "latest": "2024-12-31"},
                "folders": {'<script>alert("xss")</script>': 5},
            },
            senders=[],
        )

        render_sidebar(retriever)

        all_markdown_calls = [str(call) for call in mock_st.sidebar.markdown.call_args_list]
        folder_calls = [call for call in all_markdown_calls if "alert" in call]
        for call_str in folder_calls:
            assert "<script>" not in call_str or "&lt;script&gt;" in call_str

    @patch("mailarium.web_app.st")
    def test_render_sidebar_escapes_sender_in_markdown(self, mock_st):
        from mailarium.web_app import render_sidebar

        retriever = _sidebar_retriever(
            mock_st,
            stats={
                "total_emails": 10,
                "total_chunks": 20,
                "unique_senders": 5,
                "date_range": {"earliest": "2024-01-01", "latest": "2024-12-31"},
                "folders": {},
            },
            senders=[{"name": '<img onerror="alert(1)">', "email": "evil@example.test", "count": 5}],
        )

        render_sidebar(retriever)

        all_markdown_calls = [str(call) for call in mock_st.sidebar.markdown.call_args_list]
        sender_calls = [call for call in all_markdown_calls if "alert" in call]
        for call_str in sender_calls:
            assert "<img" not in call_str or "&lt;img" in call_str


class TestP2PathContainmentIsRelativeTo:
    """P2: Path containment must use is_relative_to(), not string prefix."""

    def test_similar_prefix_directory_rejected(self, monkeypatch):
        from mailarium.mcp_models_base import _validate_output_path

        monkeypatch.setenv("MAILARIUM_ALLOWED_OUTPUT_ROOTS", "/home/user/output")

        with pytest.raises(ValueError, match="allowed output roots"):
            _validate_output_path("/home/user2/evil.html")

    def test_valid_subdirectory_accepted(self, monkeypatch):
        from mailarium.mcp_models_base import _validate_output_path

        monkeypatch.setenv("MAILARIUM_ALLOWED_OUTPUT_ROOTS", "/home/user/output")
        result = _validate_output_path("/home/user/output/report.html")
        assert result == str(Path("/home/user/output/report.html").resolve())


class TestP2TopicModelerPathValidation:
    """P2: TopicModeler.load must validate file extension."""

    def test_non_pickle_extension_rejected(self, tmp_path):
        from mailarium.topic_modeler import TopicModeler

        with pytest.raises(ValueError, match=r"must be \.pkl or \.pickle"):
            TopicModeler.load(str(tmp_path / "evil.bin"))

    def test_nonexistent_file_raises(self, tmp_path):
        from mailarium.topic_modeler import TopicModeler

        with pytest.raises(FileNotFoundError):
            TopicModeler.load(str(tmp_path / "model.pkl"))
