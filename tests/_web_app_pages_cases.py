# ruff: noqa: F401,I001
"""Extended tests for web_app.py — targeting >=80% coverage.

Every test mocks Streamlit calls and database dependencies to avoid
requiring real databases or a running Streamlit server.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.retriever import SearchResult

# ── Helpers ──────────────────────────────────────────────────────────

from .helpers.web_app_fixtures import _columns_side_effect, _result, _setup_evidence_st, _setup_main_search_st


class TestGetEmailDbSafeImpl:
    def test_prefers_explicit_sqlite_path(self, tmp_path):
        from src import web_app_pages

        db_path = tmp_path / "archive.db"
        db_path.touch()

        with patch("src.email_db.EmailDatabase") as mock_db:
            result = web_app_pages.get_email_db_safe_impl(str(db_path))

        mock_db.assert_called_once_with(str(db_path))
        assert result is mock_db.return_value

    def test_returns_none_for_invalid_sqlite_runtime(self, tmp_path):
        from src import web_app_pages

        db_path = tmp_path / "archive.db"
        db_path.touch()

        with patch("src.email_db.EmailDatabase", side_effect=RuntimeError("malformed sqlite header")):
            result = web_app_pages.get_email_db_safe_impl(str(db_path))

        assert result is None


class TestRenderDashboardPage:
    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_no_db_shows_warning(self, mock_st, mock_db_safe):
        from src.web_app import render_dashboard_page

        mock_db_safe.return_value = None
        render_dashboard_page()
        mock_st.warning.assert_called_once()

    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_renders_volume_chart(self, mock_st, mock_db_safe):
        from src.web_app import render_dashboard_page

        db = MagicMock()
        db.top_contacts.return_value = []
        mock_db_safe.return_value = db
        mock_st.selectbox.return_value = "month"
        mock_st.text_input.return_value = ""

        with (
            patch("src.dashboard_charts.prepare_volume_chart_data") as mock_vol,
            patch("src.dashboard_charts.prepare_heatmap_data") as mock_heat,
            patch("src.dashboard_charts.prepare_response_times_data") as mock_resp,
            patch("src.temporal_analysis.TemporalAnalyzer"),
        ):
            mock_vol.return_value = [{"period": "2024-01", "count": 10}]
            mock_heat.return_value = [[0] * 24 for _ in range(7)]
            mock_resp.return_value = []

            render_dashboard_page()

        mock_st.subheader.assert_any_call("Email Volume Over Time")

    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_renders_heatmap_with_data(self, mock_st, mock_db_safe):
        from src.web_app import render_dashboard_page

        db = MagicMock()
        db.top_contacts.return_value = []
        mock_db_safe.return_value = db
        mock_st.selectbox.return_value = "month"
        mock_st.text_input.return_value = ""

        heatmap_grid = [[0] * 24 for _ in range(7)]
        heatmap_grid[0][9] = 5

        with (
            patch("src.dashboard_charts.prepare_volume_chart_data", return_value=[]),
            patch("src.dashboard_charts.prepare_heatmap_data", return_value=heatmap_grid),
            patch("src.dashboard_charts.prepare_response_times_data", return_value=[]),
            patch("src.temporal_analysis.TemporalAnalyzer"),
        ):
            render_dashboard_page()

        mock_st.dataframe.assert_called()

    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_renders_top_contacts(self, mock_st, mock_db_safe):
        from src.web_app import render_dashboard_page

        db = MagicMock()
        db.top_contacts.return_value = [{"partner": "bob@example.test", "total": 10}]
        mock_db_safe.return_value = db
        mock_st.selectbox.return_value = "month"
        mock_st.text_input.return_value = "me@example.test"

        with (
            patch("src.dashboard_charts.prepare_volume_chart_data", return_value=[]),
            patch("src.dashboard_charts.prepare_heatmap_data", return_value=[[0] * 24 for _ in range(7)]),
            patch("src.dashboard_charts.prepare_response_times_data", return_value=[]),
            patch("src.temporal_analysis.TemporalAnalyzer"),
        ):
            render_dashboard_page()

        mock_st.bar_chart.assert_called()

    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_no_contacts_for_email(self, mock_st, mock_db_safe):
        from src.web_app import render_dashboard_page

        db = MagicMock()
        db.top_contacts.return_value = []
        mock_db_safe.return_value = db
        mock_st.selectbox.return_value = "month"
        mock_st.text_input.return_value = "nobody@example.test"

        with (
            patch("src.dashboard_charts.prepare_volume_chart_data", return_value=[]),
            patch("src.dashboard_charts.prepare_heatmap_data", return_value=[[0] * 24 for _ in range(7)]),
            patch("src.dashboard_charts.prepare_response_times_data", return_value=[]),
            patch("src.temporal_analysis.TemporalAnalyzer"),
        ):
            render_dashboard_page()

        mock_st.info.assert_any_call("No contacts found for nobody@example.test")

    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_response_times_with_data(self, mock_st, mock_db_safe):
        from src.web_app import render_dashboard_page

        db = MagicMock()
        db.top_contacts.return_value = []
        mock_db_safe.return_value = db
        mock_st.selectbox.return_value = "month"
        mock_st.text_input.return_value = ""

        with (
            patch("src.dashboard_charts.prepare_volume_chart_data", return_value=[]),
            patch("src.dashboard_charts.prepare_heatmap_data", return_value=[[0] * 24 for _ in range(7)]),
            patch("src.dashboard_charts.prepare_response_times_data", return_value=[{"pair": "a-b", "avg_hours": 2.5}]),
            patch("src.temporal_analysis.TemporalAnalyzer"),
        ):
            render_dashboard_page()

        mock_st.subheader.assert_any_call("Response Times")

    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_volume_no_data(self, mock_st, mock_db_safe):
        from src.web_app import render_dashboard_page

        db = MagicMock()
        db.top_contacts.return_value = []
        mock_db_safe.return_value = db
        mock_st.selectbox.return_value = "month"
        mock_st.text_input.return_value = ""

        with (
            patch("src.dashboard_charts.prepare_volume_chart_data", return_value=[]),
            patch("src.dashboard_charts.prepare_heatmap_data", return_value=[[0] * 24 for _ in range(7)]),
            patch("src.dashboard_charts.prepare_response_times_data", return_value=[]),
            patch("src.temporal_analysis.TemporalAnalyzer"),
        ):
            render_dashboard_page()

        mock_st.info.assert_any_call("No volume data available.")

    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_heatmap_empty(self, mock_st, mock_db_safe):
        from src.web_app import render_dashboard_page

        db = MagicMock()
        db.top_contacts.return_value = []
        mock_db_safe.return_value = db
        mock_st.selectbox.return_value = "month"
        mock_st.text_input.return_value = ""

        with (
            patch("src.dashboard_charts.prepare_volume_chart_data", return_value=[]),
            patch("src.dashboard_charts.prepare_heatmap_data", return_value=[[0] * 24 for _ in range(7)]),
            patch("src.dashboard_charts.prepare_response_times_data", return_value=[]),
            patch("src.temporal_analysis.TemporalAnalyzer"),
        ):
            render_dashboard_page()

        mock_st.info.assert_any_call("No activity data available.")

    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_response_times_no_data(self, mock_st, mock_db_safe):
        from src.web_app import render_dashboard_page

        db = MagicMock()
        db.top_contacts.return_value = []
        mock_db_safe.return_value = db
        mock_st.selectbox.return_value = "month"
        mock_st.text_input.return_value = ""

        with (
            patch("src.dashboard_charts.prepare_volume_chart_data", return_value=[]),
            patch("src.dashboard_charts.prepare_heatmap_data", return_value=[[0] * 24 for _ in range(7)]),
            patch("src.dashboard_charts.prepare_response_times_data", return_value=[]),
            patch("src.temporal_analysis.TemporalAnalyzer"),
        ):
            render_dashboard_page()

        mock_st.info.assert_any_call("No response time data available.")


class TestRenderEntityPage:
    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_no_db_shows_warning(self, mock_st, mock_db_safe):
        from src.web_app import render_entity_page

        mock_db_safe.return_value = None
        render_entity_page()
        mock_st.warning.assert_called_once()

    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_renders_entities(self, mock_st, mock_db_safe):
        from src.web_app import render_entity_page

        db = MagicMock()
        db.top_entities.return_value = [{"entity": "Acme", "type": "organization", "count": 5}]
        db.entity_co_occurrences.return_value = []
        mock_db_safe.return_value = db
        mock_st.selectbox.return_value = "All"
        mock_st.text_input.return_value = ""

        render_entity_page()
        mock_st.dataframe.assert_called()

    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_no_entities(self, mock_st, mock_db_safe):
        from src.web_app import render_entity_page

        db = MagicMock()
        db.top_entities.return_value = []
        mock_db_safe.return_value = db
        mock_st.selectbox.return_value = "person"
        mock_st.text_input.return_value = ""

        render_entity_page()
        mock_st.info.assert_called()

    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_co_occurrences_with_query(self, mock_st, mock_db_safe):
        from src.web_app import render_entity_page

        db = MagicMock()
        db.top_entities.return_value = []
        db.entity_co_occurrences.return_value = [{"entity": "Bob", "count": 3}]
        mock_db_safe.return_value = db
        mock_st.selectbox.return_value = "All"
        mock_st.text_input.return_value = "Acme Corp"

        render_entity_page()
        mock_st.dataframe.assert_called()

    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_co_occurrences_no_results(self, mock_st, mock_db_safe):
        from src.web_app import render_entity_page

        db = MagicMock()
        db.top_entities.return_value = []
        db.entity_co_occurrences.return_value = []
        mock_db_safe.return_value = db
        mock_st.selectbox.return_value = "All"
        mock_st.text_input.return_value = "Nonexistent"

        render_entity_page()
        mock_st.info.assert_any_call("No co-occurrences found for 'Nonexistent'")

    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_entity_type_filter(self, mock_st, mock_db_safe):
        from src.web_app import render_entity_page

        db = MagicMock()
        db.top_entities.return_value = [{"entity": "Bob", "type": "person", "count": 2}]
        mock_db_safe.return_value = db
        mock_st.selectbox.return_value = "person"
        mock_st.text_input.return_value = ""

        render_entity_page()
        db.top_entities.assert_called_with(entity_type="person", limit=30)


class TestRenderNetworkPage:
    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_no_db_shows_warning(self, mock_st, mock_db_safe):
        from src.web_app import render_network_page

        mock_db_safe.return_value = None
        render_network_page()
        mock_st.warning.assert_called_once()

    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_error_in_network_data(self, mock_st, mock_db_safe):
        from src.web_app import render_network_page

        db = MagicMock()
        mock_db_safe.return_value = db

        with patch("src.dashboard_charts.prepare_network_summary") as mock_net:
            mock_net.return_value = {"error": "NetworkX not installed"}
            render_network_page()

        mock_st.warning.assert_called_with("NetworkX not installed")

    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_renders_network_metrics(self, mock_st, mock_db_safe):
        from src.web_app import render_network_page

        db = MagicMock()
        mock_db_safe.return_value = db
        col_mocks = [MagicMock(), MagicMock()]
        mock_st.columns.return_value = col_mocks
        mock_st.expander.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_st.expander.return_value.__exit__ = MagicMock(return_value=False)

        with patch("src.dashboard_charts.prepare_network_summary") as mock_net:
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

    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_renders_no_most_connected(self, mock_st, mock_db_safe):
        from src.web_app import render_network_page

        db = MagicMock()
        mock_db_safe.return_value = db
        mock_st.columns.return_value = [MagicMock(), MagicMock()]

        with patch("src.dashboard_charts.prepare_network_summary") as mock_net:
            mock_net.return_value = {
                "total_nodes": 0,
                "total_edges": 0,
                "most_connected": [],
                "communities": [],
            }
            render_network_page()

        subheader_calls = [str(c) for c in mock_st.subheader.call_args_list]
        assert not any("Most Connected" in c for c in subheader_calls)

    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_communities_capped_at_10(self, mock_st, mock_db_safe):
        from src.web_app import render_network_page

        db = MagicMock()
        mock_db_safe.return_value = db
        mock_st.columns.return_value = [MagicMock(), MagicMock()]
        mock_st.expander.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_st.expander.return_value.__exit__ = MagicMock(return_value=False)

        communities = [{"members": [f"user{j}@x.com" for j in range(5)]} for _ in range(15)]

        with patch("src.dashboard_charts.prepare_network_summary") as mock_net:
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
    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_no_db_shows_warning(self, mock_st, mock_db_safe):
        from src.web_app import render_evidence_page

        mock_db_safe.return_value = None
        render_evidence_page()
        mock_st.warning.assert_called_once()

    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_renders_evidence_overview(self, mock_st, mock_db_safe):
        from src.web_app import render_evidence_page

        db = MagicMock()
        db.evidence_stats.return_value = {"total": 10, "verified": 7, "unverified": 3}
        db.evidence_categories.return_value = [
            {"category": "harassment", "count": 5},
            {"category": "bossing", "count": 3},
            {"category": "general", "count": 0},
        ]
        db.list_evidence.return_value = {"items": [], "total": 0}
        mock_db_safe.return_value = db
        _setup_evidence_st(mock_st)

        render_evidence_page()
        mock_st.info.assert_any_call(
            "Exploratory evidence collection only. For authoritative lawyer-ready evidence indexes, chronology, and "
            "counsel-facing matter review, use the MCP legal-support tools. CLI `case full-pack` / `case counsel-pack` "
            "remain local operator wrappers for preparation and exporter checks. Web downloads here stay intentionally "
            "limited to HTML and CSV; use CLI or MCP when you need PDF evidence export."
        )

    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_renders_evidence_items(self, mock_st, mock_db_safe):
        from src.web_app import render_evidence_page

        db = MagicMock()
        db.evidence_stats.return_value = {"total": 1, "verified": 1, "unverified": 0}
        db.evidence_categories.return_value = [{"category": "harassment", "count": 1}]
        db.list_evidence.return_value = {
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
        }
        mock_db_safe.return_value = db
        _setup_evidence_st(mock_st)

        render_evidence_page()
        markdown_calls = [str(c) for c in mock_st.markdown.call_args_list]
        assert any("Quote" in c for c in markdown_calls)

    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_search_evidence_with_text_filter(self, mock_st, mock_db_safe):
        from src.web_app import render_evidence_page

        db = MagicMock()
        db.evidence_stats.return_value = {"total": 1, "verified": 0, "unverified": 1}
        db.evidence_categories.return_value = [{"category": "harassment", "count": 1}]
        db.search_evidence.return_value = {"items": [], "total": 0}
        mock_db_safe.return_value = db
        _setup_evidence_st(
            mock_st,
            selectbox_side_effect=["harassment", "html", 1],
            slider_val=3,
            text_input_val="search term",
        )

        render_evidence_page()
        db.search_evidence.assert_called_once_with(
            query="search term",
            category="harassment",
            min_relevance=3,
            limit=100,
        )

    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_export_html(self, mock_st, mock_db_safe):
        from src.web_app import render_evidence_page

        db = MagicMock()
        db.evidence_stats.return_value = {"total": 1, "verified": 1, "unverified": 0}
        db.evidence_categories.return_value = [{"category": "harassment", "count": 1}]
        db.list_evidence.return_value = {"items": [], "total": 0}
        mock_db_safe.return_value = db
        _setup_evidence_st(mock_st, selectbox_side_effect=["All", "html", 1], button_val=True)

        with patch("src.evidence_exporter.EvidenceExporter") as mock_exporter_cls:
            mock_exporter = MagicMock()
            mock_exporter.export_html.return_value = {"html": "<h1>Report</h1>"}
            mock_exporter_cls.return_value = mock_exporter
            render_evidence_page()

        mock_st.download_button.assert_called()

    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_export_csv(self, mock_st, mock_db_safe):
        from src.web_app import render_evidence_page

        db = MagicMock()
        db.evidence_stats.return_value = {"total": 1, "verified": 1, "unverified": 0}
        db.evidence_categories.return_value = [{"category": "harassment", "count": 1}]
        db.list_evidence.return_value = {"items": [], "total": 0}
        mock_db_safe.return_value = db
        _setup_evidence_st(mock_st, selectbox_side_effect=["All", "csv", 1], button_val=True)

        with patch("src.evidence_exporter.EvidenceExporter") as mock_exporter_cls:
            mock_exporter = MagicMock()
            mock_exporter.export_csv.return_value = {"csv": "col1,col2\nval1,val2\n"}
            mock_exporter_cls.return_value = mock_exporter
            render_evidence_page()

        mock_st.download_button.assert_called()

    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_evidence_item_without_notes(self, mock_st, mock_db_safe):
        from src.web_app import render_evidence_page

        db = MagicMock()
        db.evidence_stats.return_value = {"total": 1, "verified": 0, "unverified": 1}
        db.evidence_categories.return_value = []
        db.list_evidence.return_value = {
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
        }
        mock_db_safe.return_value = db
        _setup_evidence_st(mock_st)

        render_evidence_page()
        markdown_calls = [str(c) for c in mock_st.markdown.call_args_list]
        assert not any("Notes" in c for c in markdown_calls)

    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_min_relevance_filter_1_passes_none(self, mock_st, mock_db_safe):
        from src.web_app import render_evidence_page

        db = MagicMock()
        db.evidence_stats.return_value = {"total": 0, "verified": 0, "unverified": 0}
        db.evidence_categories.return_value = []
        db.list_evidence.return_value = {"items": [], "total": 0}
        mock_db_safe.return_value = db
        _setup_evidence_st(mock_st)

        render_evidence_page()
        db.list_evidence.assert_called_with(category=None, min_relevance=None, limit=100)

    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_no_cats_with_items_no_chart(self, mock_st, mock_db_safe):
        from src.web_app import render_evidence_page

        db = MagicMock()
        db.evidence_stats.return_value = {"total": 0, "verified": 0, "unverified": 0}
        db.evidence_categories.return_value = [{"category": "general", "count": 0}]
        db.list_evidence.return_value = {"items": [], "total": 0}
        mock_db_safe.return_value = db
        _setup_evidence_st(mock_st)

        render_evidence_page()
        mock_st.bar_chart.assert_not_called()

    @patch("src.web_app._get_email_db_safe")
    @patch("src.web_app.st")
    def test_no_evidence_items_shows_info(self, mock_st, mock_db_safe):
        from src.web_app import render_evidence_page

        db = MagicMock()
        db.evidence_stats.return_value = {"total": 0, "verified": 0, "unverified": 0}
        db.evidence_categories.return_value = []
        db.list_evidence.return_value = {"items": [], "total": 0}
        mock_db_safe.return_value = db
        _setup_evidence_st(mock_st)

        render_evidence_page()
        mock_st.info.assert_called()
