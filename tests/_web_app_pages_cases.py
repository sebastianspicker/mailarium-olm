# ruff: noqa: I001
"""Streamlit dashboard, entity, network, and evidence-page rendering behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ──────────────────────────────────────────────────────────

from .helpers.web_app_fixtures import (
    _patched_dashboard_chart_data,
    _setup_dashboard_page,
    _setup_evidence_page,
    _setup_verified_evidence_page,
)


class TestGetEmailDbSafeImpl:
    def test_prefers_explicit_sqlite_path(self, tmp_path):
        from mailarium import web_app_pages

        db_path = tmp_path / "archive.db"
        db_path.touch()

        with patch("mailarium.email_db.EmailDatabase") as mock_db:
            result = web_app_pages.get_email_db_safe_impl(str(db_path))

        mock_db.assert_called_once_with(str(db_path))
        assert result is mock_db.return_value

    def test_returns_none_for_invalid_sqlite_runtime(self, tmp_path):
        from mailarium import web_app_pages

        db_path = tmp_path / "archive.db"
        db_path.touch()

        with patch("mailarium.email_db.EmailDatabase", side_effect=RuntimeError("malformed sqlite header")):
            result = web_app_pages.get_email_db_safe_impl(str(db_path))

        assert result is None


class TestRenderDashboardPage:
    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_no_db_shows_warning(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_dashboard_page

        mock_db_safe.return_value = None
        render_dashboard_page()
        mock_st.warning.assert_called_once()

    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_renders_volume_chart(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_dashboard_page

        _setup_dashboard_page(mock_st, mock_db_safe)
        with _patched_dashboard_chart_data(volume_data=[{"period": "2024-01", "count": 10}]):
            render_dashboard_page()

        mock_st.subheader.assert_any_call("Email Volume Over Time")

    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_renders_heatmap_with_data(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_dashboard_page

        heatmap_grid = [[0] * 24 for _ in range(7)]
        heatmap_grid[0][9] = 5
        _setup_dashboard_page(mock_st, mock_db_safe)
        with _patched_dashboard_chart_data(heatmap_data=heatmap_grid):
            render_dashboard_page()

        mock_st.dataframe.assert_called()

    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_renders_top_contacts(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_dashboard_page

        _setup_dashboard_page(mock_st, mock_db_safe, contacts=[{"partner": "bob@example.test", "total": 10}])
        mock_st.text_input.return_value = "me@example.test"
        with _patched_dashboard_chart_data():
            render_dashboard_page()

        mock_st.bar_chart.assert_called()

    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_no_contacts_for_email(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_dashboard_page

        _setup_dashboard_page(mock_st, mock_db_safe)
        mock_st.text_input.return_value = "nobody@example.test"
        with _patched_dashboard_chart_data():
            render_dashboard_page()

        mock_st.info.assert_any_call("No contacts found for nobody@example.test")

    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_response_times_with_data(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_dashboard_page

        _setup_dashboard_page(mock_st, mock_db_safe)
        with _patched_dashboard_chart_data(response_time_data=[{"pair": "a-b", "avg_hours": 2.5}]):
            render_dashboard_page()

        mock_st.subheader.assert_any_call("Response Times")

    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_volume_no_data(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_dashboard_page

        _setup_dashboard_page(mock_st, mock_db_safe)
        with _patched_dashboard_chart_data():
            render_dashboard_page()

        mock_st.info.assert_any_call("No volume data available.")

    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_heatmap_empty(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_dashboard_page

        _setup_dashboard_page(mock_st, mock_db_safe)
        with _patched_dashboard_chart_data():
            render_dashboard_page()

        mock_st.info.assert_any_call("No activity data available.")

    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_response_times_no_data(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_dashboard_page

        _setup_dashboard_page(mock_st, mock_db_safe)
        with _patched_dashboard_chart_data():
            render_dashboard_page()

        mock_st.info.assert_any_call("No response time data available.")


class TestRenderEntityPage:
    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_no_db_shows_warning(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_entity_page

        mock_db_safe.return_value = None
        render_entity_page()
        mock_st.warning.assert_called_once()

    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_renders_entities(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_entity_page

        db = MagicMock()
        db.top_entities.return_value = [{"entity": "Acme", "type": "organization", "count": 5}]
        db.entity_co_occurrences.return_value = []
        mock_db_safe.return_value = db
        mock_st.selectbox.return_value = "All"
        mock_st.text_input.return_value = ""

        render_entity_page()
        mock_st.dataframe.assert_called()

    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_no_entities(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_entity_page

        db = MagicMock()
        db.top_entities.return_value = []
        mock_db_safe.return_value = db
        mock_st.selectbox.return_value = "person"
        mock_st.text_input.return_value = ""

        render_entity_page()
        mock_st.info.assert_called()

    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_co_occurrences_with_query(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_entity_page

        db = MagicMock()
        db.top_entities.return_value = []
        db.entity_co_occurrences.return_value = [{"entity": "Bob", "count": 3}]
        mock_db_safe.return_value = db
        mock_st.selectbox.return_value = "All"
        mock_st.text_input.return_value = "Acme Corp"

        render_entity_page()
        mock_st.dataframe.assert_called()

    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_co_occurrences_no_results(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_entity_page

        db = MagicMock()
        db.top_entities.return_value = []
        db.entity_co_occurrences.return_value = []
        mock_db_safe.return_value = db
        mock_st.selectbox.return_value = "All"
        mock_st.text_input.return_value = "Nonexistent"

        render_entity_page()
        mock_st.info.assert_any_call("No co-occurrences found for 'Nonexistent'")

    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_entity_type_filter(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_entity_page

        db = MagicMock()
        db.top_entities.return_value = [{"entity": "Bob", "type": "person", "count": 2}]
        mock_db_safe.return_value = db
        mock_st.selectbox.return_value = "person"
        mock_st.text_input.return_value = ""

        render_entity_page()
        db.top_entities.assert_called_with(entity_type="person", limit=30)


class TestRenderNetworkPage:
    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_no_db_shows_warning(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_network_page

        mock_db_safe.return_value = None
        render_network_page()
        mock_st.warning.assert_called_once()

    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_error_in_network_data(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_network_page

        db = MagicMock()
        mock_db_safe.return_value = db

        with patch("mailarium.dashboard_charts.prepare_network_summary") as mock_net:
            mock_net.return_value = {"error": "NetworkX not installed"}
            render_network_page()

        mock_st.warning.assert_called_with("NetworkX not installed")

    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_renders_network_metrics(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_network_page

        db = MagicMock()
        mock_db_safe.return_value = db
        col_mocks = [MagicMock(), MagicMock()]
        mock_st.columns.return_value = col_mocks
        mock_st.expander.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_st.expander.return_value.__exit__ = MagicMock(return_value=False)

        with patch("mailarium.dashboard_charts.prepare_network_summary") as mock_net:
            mock_net.return_value = {
                "total_nodes": 50,
                "total_edges": 200,
                "most_connected": [{"email": "a@example.test", "degree": 20}],
                "communities": [
                    {"members": ["a@example.test", "b@example.test"]},
                    {"members": ["c@example.test"]},
                ],
            }
            render_network_page()

        col_mocks[0].metric.assert_called_with("Total Nodes", 50)
        col_mocks[1].metric.assert_called_with("Total Edges", 200)

    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_renders_no_most_connected(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_network_page

        db = MagicMock()
        mock_db_safe.return_value = db
        mock_st.columns.return_value = [MagicMock(), MagicMock()]

        with patch("mailarium.dashboard_charts.prepare_network_summary") as mock_net:
            mock_net.return_value = {
                "total_nodes": 0,
                "total_edges": 0,
                "most_connected": [],
                "communities": [],
            }
            render_network_page()

        subheader_calls = [str(c) for c in mock_st.subheader.call_args_list]
        assert not any("Most Connected" in c for c in subheader_calls)

    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_communities_capped_at_10(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_network_page

        db = MagicMock()
        mock_db_safe.return_value = db
        mock_st.columns.return_value = [MagicMock(), MagicMock()]
        mock_st.expander.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_st.expander.return_value.__exit__ = MagicMock(return_value=False)

        communities = [{"members": [f"user{j}@x.com" for j in range(5)]} for _ in range(15)]

        with patch("mailarium.dashboard_charts.prepare_network_summary") as mock_net:
            mock_net.return_value = {
                "total_nodes": 100,
                "total_edges": 500,
                "most_connected": [],
                "communities": communities,
            }
            render_network_page()

        expander_calls = mock_st.expander.call_args_list
        community_expanders = [c for c in expander_calls if "Community" in str(c)]
        assert len(community_expanders) == 10


class TestRenderEvidencePage:
    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_no_db_shows_warning(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_evidence_page

        mock_db_safe.return_value = None
        render_evidence_page()
        mock_st.warning.assert_called_once()

    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_renders_evidence_overview(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_evidence_page

        _setup_evidence_page(
            mock_st,
            mock_db_safe,
            stats={"total": 10, "verified": 7, "unverified": 3},
            categories=[
                {"category": "harassment", "count": 5},
                {"category": "bossing", "count": 3},
                {"category": "general", "count": 0},
            ],
            list_response={"items": [], "total": 0},
        )

        render_evidence_page()
        mock_st.info.assert_any_call(
            "This page supports exploratory evidence collection and HTML/CSV downloads. "
            "Use the CLI or MCP evidence tools for repeatable workflows, custody checks, "
            "dossier generation, and PDF export."
        )

    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_renders_evidence_items(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_evidence_page

        _setup_verified_evidence_page(
            mock_st,
            mock_db_safe,
            list_response={
                "items": [
                    {
                        "id": 1,
                        "category": "harassment",
                        "relevance": 4,
                        "verified": True,
                        "date": "2024-01-15",
                        "sender_name": "Boss",
                        "sender_email": "boss@example.com",
                        "subject": "Warning",
                        "key_quote": "You're fired",
                        "summary": "Threatening language",
                        "notes": "Very concerning",
                        "recipients": "victim@example.com",
                        "email_uid": "uid123",
                    }
                ],
                "total": 1,
            },
        )

        render_evidence_page()
        markdown_calls = [str(c) for c in mock_st.markdown.call_args_list]
        assert any("Quote" in c for c in markdown_calls)

    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_search_evidence_with_text_filter(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_evidence_page

        db = _setup_evidence_page(
            mock_st,
            mock_db_safe,
            stats={"total": 1, "verified": 0, "unverified": 1},
            categories=[{"category": "harassment", "count": 1}],
            search_response={"items": [], "total": 0},
            streamlit_options={
                "selectbox_side_effect": ["harassment", "html", 1],
                "slider_val": 3,
                "text_input_val": "search term",
            },
        )

        render_evidence_page()
        db.search_evidence.assert_called_once_with(
            query="search term",
            category="harassment",
            min_relevance=3,
            limit=100,
        )

    @pytest.mark.parametrize(
        ("export_format", "export_method", "export_result"),
        [
            ("html", "export_html", {"html": "<h1>Report</h1>"}),
            ("csv", "export_csv", {"csv": "col1,col2\nval1,val2\n"}),
        ],
    )
    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_export(self, mock_st, mock_db_safe, export_format, export_method, export_result):
        from mailarium.web_app import render_evidence_page

        _setup_verified_evidence_page(
            mock_st,
            mock_db_safe,
            list_response={"items": [], "total": 0},
            streamlit_options={"selectbox_side_effect": ["All", export_format, 1], "button_val": True},
        )

        with patch("mailarium.evidence_exporter.EvidenceExporter") as mock_exporter_cls:
            mock_exporter = MagicMock()
            getattr(mock_exporter, export_method).return_value = export_result
            mock_exporter_cls.return_value = mock_exporter
            render_evidence_page()

        mock_st.download_button.assert_called()

    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_evidence_item_without_notes(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_evidence_page

        _setup_evidence_page(
            mock_st,
            mock_db_safe,
            stats={"total": 1, "verified": 0, "unverified": 1},
            categories=[],
            list_response={
                "items": [
                    {
                        "id": 2,
                        "category": "general",
                        "relevance": 2,
                        "verified": False,
                        "date": "2024-03-01",
                        "sender_name": "X",
                        "sender_email": "x@example.test",
                        "subject": "Subj",
                        "key_quote": "quote",
                        "summary": "summary",
                        "notes": "",
                        "recipients": "",
                        "email_uid": "uid456",
                    }
                ],
                "total": 1,
            },
        )

        render_evidence_page()
        markdown_calls = [str(c) for c in mock_st.markdown.call_args_list]
        assert not any("Notes" in c for c in markdown_calls)

    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_min_relevance_filter_1_passes_none(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_evidence_page

        db = _setup_evidence_page(
            mock_st,
            mock_db_safe,
            stats={"total": 0, "verified": 0, "unverified": 0},
            categories=[],
            list_response={"items": [], "total": 0},
        )

        render_evidence_page()
        db.list_evidence.assert_called_with(category=None, min_relevance=None, limit=100)

    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_no_cats_with_items_no_chart(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_evidence_page

        _setup_evidence_page(
            mock_st,
            mock_db_safe,
            stats={"total": 0, "verified": 0, "unverified": 0},
            categories=[{"category": "general", "count": 0}],
            list_response={"items": [], "total": 0},
        )

        render_evidence_page()
        mock_st.bar_chart.assert_not_called()

    @patch("mailarium.web_app._get_email_db_safe")
    @patch("mailarium.web_app.st")
    def test_no_evidence_items_shows_info(self, mock_st, mock_db_safe):
        from mailarium.web_app import render_evidence_page

        _setup_evidence_page(
            mock_st,
            mock_db_safe,
            stats={"total": 0, "verified": 0, "unverified": 0},
            categories=[],
            list_response={"items": [], "total": 0},
        )

        render_evidence_page()
        mock_st.info.assert_called()
