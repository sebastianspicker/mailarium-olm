"""MCP, CLI, and report regression tests split out from the RF8 catch-all."""

from __future__ import annotations

import argparse
from html import escape as html_escape
from unittest.mock import MagicMock, patch

import pytest


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

    @patch("src.web_app.st")
    def test_render_sidebar_escapes_folder_in_markdown(self, mock_st):
        from src.web_app import render_sidebar

        mock_st.sidebar.expander.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_st.sidebar.expander.return_value.__exit__ = MagicMock(return_value=False)
        mock_st.sidebar.columns.return_value = [MagicMock(), MagicMock(), MagicMock()]

        retriever = MagicMock()
        retriever.stats.return_value = {
            "total_emails": 10,
            "total_chunks": 20,
            "unique_senders": 5,
            "date_range": {"earliest": "2024-01-01", "latest": "2024-12-31"},
            "folders": {'<script>alert("xss")</script>': 5},
        }
        retriever.list_senders.return_value = []

        render_sidebar(retriever)

        all_markdown_calls = [str(call) for call in mock_st.sidebar.markdown.call_args_list]
        folder_calls = [call for call in all_markdown_calls if "alert" in call]
        for call_str in folder_calls:
            assert "<script>" not in call_str or "&lt;script&gt;" in call_str

    @patch("src.web_app.st")
    def test_render_sidebar_escapes_sender_in_markdown(self, mock_st):
        from src.web_app import render_sidebar

        mock_st.sidebar.expander.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_st.sidebar.expander.return_value.__exit__ = MagicMock(return_value=False)
        mock_st.sidebar.columns.return_value = [MagicMock(), MagicMock(), MagicMock()]

        retriever = MagicMock()
        retriever.stats.return_value = {
            "total_emails": 10,
            "total_chunks": 20,
            "unique_senders": 5,
            "date_range": {"earliest": "2024-01-01", "latest": "2024-12-31"},
            "folders": {},
        }
        retriever.list_senders.return_value = [
            {"name": '<img onerror="alert(1)">', "email": "evil@test.com", "count": 5},
        ]

        render_sidebar(retriever)

        all_markdown_calls = [str(call) for call in mock_st.sidebar.markdown.call_args_list]
        sender_calls = [call for call in all_markdown_calls if "alert" in call]
        for call_str in sender_calls:
            assert "<img" not in call_str or "&lt;img" in call_str


class TestP1LegacyDossierFormat:
    """P1 fix #13: legacy --dossier format defaults to 'html'."""

    def test_legacy_dossier_format_default(self):
        from src.cli import _infer_subcommand

        args = argparse.Namespace(
            query=None,
            browse=False,
            export_thread=None,
            export_email=None,
            generate_report=None,
            export_network=None,
            evidence_list=False,
            evidence_export=None,
            evidence_stats=False,
            evidence_verify=False,
            dossier="output.html",
            dossier_format=None,
            custody_chain=False,
            provenance=None,
        )
        cmd = _infer_subcommand(args)
        assert cmd == "evidence"
        assert args.format == "html"

    def test_legacy_dossier_format_pdf(self):
        from src.cli import _infer_subcommand

        args = argparse.Namespace(
            query=None,
            browse=False,
            export_thread=None,
            export_email=None,
            generate_report=None,
            export_network=None,
            evidence_list=False,
            evidence_export=None,
            evidence_stats=False,
            evidence_verify=False,
            dossier="output.pdf",
            dossier_format="pdf",
            custody_chain=False,
            provenance=None,
        )
        cmd = _infer_subcommand(args)
        assert cmd == "evidence"
        assert args.format == "pdf"


class TestP1LegacyVolumePeriod:
    """P1 fix #14: legacy --volume period propagated correctly."""

    def test_legacy_volume_period_propagated(self):
        from src.cli import _infer_subcommand

        args = argparse.Namespace(
            query=None,
            browse=False,
            export_thread=None,
            export_email=None,
            generate_report=None,
            export_network=None,
            evidence_list=False,
            evidence_export=None,
            evidence_stats=False,
            evidence_verify=False,
            dossier=None,
            custody_chain=False,
            provenance=None,
            stats=False,
            list_senders=False,
            suggest=False,
            top_contacts=None,
            volume="week",
        )
        cmd = _infer_subcommand(args)
        assert cmd == "analytics"
        assert args.period == "week"

    def test_legacy_volume_default_period(self):
        from src.cli import _infer_subcommand

        args = argparse.Namespace(
            query=None,
            browse=False,
            export_thread=None,
            export_email=None,
            generate_report=None,
            export_network=None,
            evidence_list=False,
            evidence_export=None,
            evidence_stats=False,
            evidence_verify=False,
            dossier=None,
            custody_chain=False,
            provenance=None,
            stats=False,
            list_senders=False,
            suggest=False,
            top_contacts=None,
            volume="month",
        )
        cmd = _infer_subcommand(args)
        assert cmd == "analytics"
        assert args.period == "month"


class TestP2PathContainmentIsRelativeTo:
    """P2: Path containment must use is_relative_to(), not string prefix."""

    def test_similar_prefix_directory_rejected(self):
        from pathlib import Path
        from unittest.mock import patch as local_patch

        from src.mcp_models_base import _validate_output_path

        with (
            local_patch("src.mcp_models_base.Path.cwd", return_value=Path("/home/user")),
            local_patch("src.mcp_models_base.Path.home", return_value=Path("/home/user")),
        ):
            with pytest.raises(ValueError, match="Output path must be under"):
                _validate_output_path("/home/user2/evil.html")

    def test_valid_subdirectory_accepted(self):
        from pathlib import Path
        from unittest.mock import patch as local_patch

        from src.mcp_models_base import _validate_output_path

        with (
            local_patch("src.mcp_models_base.Path.cwd", return_value=Path("/home/user")),
            local_patch("src.mcp_models_base.Path.home", return_value=Path("/home/user")),
        ):
            result = _validate_output_path("/home/user/output/report.html")
            assert result == "/home/user/output/report.html"


class TestP2TopicModelerPathValidation:
    """P2: TopicModeler.load must validate file extension."""

    def test_non_pickle_extension_rejected(self):
        from src.topic_modeler import TopicModeler

        with pytest.raises(ValueError, match=r"must be \.pkl or \.pickle"):
            TopicModeler.load("/tmp/evil.bin")

    def test_nonexistent_file_raises(self, tmp_path):
        from src.topic_modeler import TopicModeler

        with pytest.raises(FileNotFoundError):
            TopicModeler.load(str(tmp_path / "model.pkl"))
