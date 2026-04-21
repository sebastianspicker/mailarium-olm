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
from ._web_app_aux_cases import *  # noqa: F403


class TestMain:
    @patch("src.web_app.render_evidence_page")
    @patch("src.web_app.render_network_page")
    @patch("src.web_app.render_entity_page")
    @patch("src.web_app.render_dashboard_page")
    @patch("src.web_app.render_sidebar")
    @patch("src.web_app.inject_styles")
    @patch("src.web_app.get_retriever")
    @patch("src.web_app.st")
    def test_main_routes_to_dashboard(
        self,
        mock_st,
        mock_get_retriever,
        mock_inject,
        mock_sidebar,
        mock_dashboard,
        mock_entity,
        mock_network,
        mock_evidence,
    ):
        from src.web_app import main

        mock_st.sidebar.radio.return_value = "Dashboard"
        mock_st.sidebar.text_input.return_value = ""
        mock_get_retriever.return_value = MagicMock()
        main()
        mock_dashboard.assert_called_once()

    @patch("src.web_app.render_evidence_page")
    @patch("src.web_app.render_network_page")
    @patch("src.web_app.render_entity_page")
    @patch("src.web_app.render_dashboard_page")
    @patch("src.web_app.render_sidebar")
    @patch("src.web_app.inject_styles")
    @patch("src.web_app.get_retriever")
    @patch("src.web_app.st")
    def test_main_routes_to_entities(
        self,
        mock_st,
        mock_get_retriever,
        mock_inject,
        mock_sidebar,
        mock_dashboard,
        mock_entity,
        mock_network,
        mock_evidence,
    ):
        from src.web_app import main

        mock_st.sidebar.radio.return_value = "Entities"
        mock_st.sidebar.text_input.return_value = ""
        mock_get_retriever.return_value = MagicMock()
        main()
        mock_entity.assert_called_once()

    @patch("src.web_app.render_evidence_page")
    @patch("src.web_app.render_network_page")
    @patch("src.web_app.render_entity_page")
    @patch("src.web_app.render_dashboard_page")
    @patch("src.web_app.render_sidebar")
    @patch("src.web_app.inject_styles")
    @patch("src.web_app.get_retriever")
    @patch("src.web_app.st")
    def test_main_routes_to_network(
        self,
        mock_st,
        mock_get_retriever,
        mock_inject,
        mock_sidebar,
        mock_dashboard,
        mock_entity,
        mock_network,
        mock_evidence,
    ):
        from src.web_app import main

        mock_st.sidebar.radio.return_value = "Network"
        mock_st.sidebar.text_input.return_value = ""
        mock_get_retriever.return_value = MagicMock()
        main()
        mock_network.assert_called_once()

    @patch("src.web_app.render_evidence_page")
    @patch("src.web_app.render_network_page")
    @patch("src.web_app.render_entity_page")
    @patch("src.web_app.render_dashboard_page")
    @patch("src.web_app.render_sidebar")
    @patch("src.web_app.inject_styles")
    @patch("src.web_app.get_retriever")
    @patch("src.web_app.st")
    def test_main_routes_to_evidence(
        self,
        mock_st,
        mock_get_retriever,
        mock_inject,
        mock_sidebar,
        mock_dashboard,
        mock_entity,
        mock_network,
        mock_evidence,
    ):
        from src.web_app import main

        mock_st.sidebar.radio.return_value = "Evidence"
        mock_st.sidebar.text_input.return_value = ""
        mock_get_retriever.return_value = MagicMock()
        main()
        mock_evidence.assert_called_once()

    @patch("src.web_app.render_sidebar")
    @patch("src.web_app.inject_styles")
    @patch("src.web_app.get_retriever")
    @patch("src.web_app.st")
    def test_main_empty_collection_shows_warning(
        self,
        mock_st,
        mock_get_retriever,
        mock_inject,
        mock_sidebar,
    ):
        from src.web_app import main

        mock_st.sidebar.radio.return_value = "Search"
        mock_st.sidebar.text_input.return_value = ""
        retriever = MagicMock()
        retriever.collection.count.return_value = 0
        mock_get_retriever.return_value = retriever
        main()
        mock_st.warning.assert_called_with("No emails indexed yet.")

    @patch("src.web_app.render_results")
    @patch("src.web_app.render_results_summary")
    @patch("src.web_app.render_sidebar")
    @patch("src.web_app.inject_styles")
    @patch("src.web_app.get_retriever")
    @patch("src.web_app.st")
    def test_main_search_no_query(
        self,
        mock_st,
        mock_get_retriever,
        mock_inject,
        mock_sidebar,
        mock_summary,
        mock_render_results,
    ):
        from src.web_app import main

        retriever = MagicMock()
        retriever.collection.count.return_value = 10
        mock_get_retriever.return_value = retriever
        _setup_main_search_st(mock_st, search_clicked=True)

        main()
        mock_st.warning.assert_called_with("Please enter a query.")

    @patch("src.web_app.render_results")
    @patch("src.web_app.render_results_summary")
    @patch("src.web_app.render_sidebar")
    @patch("src.web_app.inject_styles")
    @patch("src.web_app.get_retriever")
    @patch("src.web_app.st")
    def test_main_search_with_query_and_results(
        self,
        mock_st,
        mock_get_retriever,
        mock_inject,
        mock_sidebar,
        mock_summary,
        mock_render_results,
    ):
        from src.web_app import main

        retriever = MagicMock()
        retriever.collection.count.return_value = 10
        retriever.search_filtered.return_value = [_result(), _result(chunk_id="c2")]
        mock_get_retriever.return_value = retriever
        _setup_main_search_st(
            mock_st,
            search_clicked=True,
            text_inputs=["contract renewal", "", "", "", "", "", ""],
        )

        main()
        retriever.search_filtered.assert_called_once()

    @patch("src.web_app.render_results")
    @patch("src.web_app.render_results_summary")
    @patch("src.web_app.render_sidebar")
    @patch("src.web_app.inject_styles")
    @patch("src.web_app.get_retriever")
    @patch("src.web_app.st")
    def test_main_search_invalid_date_range(
        self,
        mock_st,
        mock_get_retriever,
        mock_inject,
        mock_sidebar,
        mock_summary,
        mock_render_results,
    ):
        from src.web_app import main

        retriever = MagicMock()
        retriever.collection.count.return_value = 10
        mock_get_retriever.return_value = retriever

        date_from = MagicMock()
        date_from.__str__ = MagicMock(return_value="2025-06-01")
        date_from.__bool__ = MagicMock(return_value=True)
        date_to = MagicMock()
        date_to.__str__ = MagicMock(return_value="2024-01-01")
        date_to.__bool__ = MagicMock(return_value=True)

        _setup_main_search_st(
            mock_st,
            search_clicked=True,
            text_inputs=["query", "", "", "", "", "", ""],
            date_inputs=[date_from, date_to],
        )

        main()
        mock_st.error.assert_called_with("Date From cannot be later than Date To.")

    @patch("src.web_app.render_results")
    @patch("src.web_app.render_results_summary")
    @patch("src.web_app.render_sidebar")
    @patch("src.web_app.inject_styles")
    @patch("src.web_app.get_retriever")
    @patch("src.web_app.st")
    def test_main_search_no_results_in_session(
        self,
        mock_st,
        mock_get_retriever,
        mock_inject,
        mock_sidebar,
        mock_summary,
        mock_render_results,
    ):
        from src.web_app import main

        retriever = MagicMock()
        retriever.collection.count.return_value = 10
        mock_get_retriever.return_value = retriever
        _setup_main_search_st(mock_st, search_clicked=False)

        main()
        mock_st.info.assert_called()

    @patch("src.web_app._build_csv_export")
    @patch("src.web_app.build_export_payload")
    @patch("src.web_app.build_active_filter_labels")
    @patch("src.web_app.render_results")
    @patch("src.web_app.render_results_summary")
    @patch("src.web_app.render_sidebar")
    @patch("src.web_app.inject_styles")
    @patch("src.web_app.get_retriever")
    @patch("src.web_app.st")
    def test_main_with_existing_results_in_session(
        self,
        mock_st,
        mock_get_retriever,
        mock_inject,
        mock_sidebar,
        mock_summary,
        mock_render_results,
        mock_labels,
        mock_export,
        mock_csv,
    ):
        from src.web_app import main

        mock_st.sidebar.radio.return_value = "Search"
        mock_st.sidebar.text_input.return_value = ""
        retriever = MagicMock()
        retriever.collection.count.return_value = 10
        mock_get_retriever.return_value = retriever

        existing_results = [_result(), _result(chunk_id="c2")]
        mock_st.session_state = {
            "web_results": existing_results,
            "web_query": "old query",
            "web_filters": {"sender": "alice"},
            "web_sort": "relevance",
            "web_page": 0,
            "web_thread_id": None,
        }
        mock_st.form.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_st.form.return_value.__exit__ = MagicMock(return_value=False)
        mock_st.columns.side_effect = _columns_side_effect
        mock_st.expander.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_st.expander.return_value.__exit__ = MagicMock(return_value=False)
        mock_st.text_input.return_value = ""
        mock_st.number_input.return_value = 10
        mock_st.selectbox.return_value = "Relevance"
        mock_st.slider.side_effect = [0.0, 1200]
        mock_st.date_input.return_value = None
        mock_st.checkbox.return_value = False
        mock_st.form_submit_button.return_value = False
        mock_st.button.return_value = False
        mock_labels.return_value = []
        mock_export.return_value = {}
        mock_csv.return_value = ""

        main()
        mock_render_results.assert_called_once()
        mock_summary.assert_called_once()

    @patch("src.web_app._build_csv_export")
    @patch("src.web_app.build_export_payload")
    @patch("src.web_app.build_active_filter_labels")
    @patch("src.web_app.render_results")
    @patch("src.web_app.render_results_summary")
    @patch("src.web_app.render_sidebar")
    @patch("src.web_app.inject_styles")
    @patch("src.web_app.get_retriever")
    @patch("src.web_app.st")
    def test_main_with_thread_view(
        self,
        mock_st,
        mock_get_retriever,
        mock_inject,
        mock_sidebar,
        mock_summary,
        mock_render_results,
        mock_labels,
        mock_export,
        mock_csv,
    ):
        from src.web_app import main

        mock_st.sidebar.radio.return_value = "Search"
        mock_st.sidebar.text_input.return_value = ""
        retriever = MagicMock()
        retriever.collection.count.return_value = 10
        thread_results = [_result(subject="Thread Email 1")]
        retriever.search_by_thread.return_value = thread_results
        mock_get_retriever.return_value = retriever

        mock_st.session_state = {
            "web_results": [_result()],
            "web_query": "query",
            "web_filters": {},
            "web_sort": "relevance",
            "web_page": 0,
            "web_thread_id": "conv123",
        }
        mock_st.form.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_st.form.return_value.__exit__ = MagicMock(return_value=False)
        mock_st.columns.side_effect = _columns_side_effect
        mock_st.expander.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_st.expander.return_value.__exit__ = MagicMock(return_value=False)
        mock_st.text_input.return_value = ""
        mock_st.number_input.return_value = 10
        mock_st.selectbox.return_value = "Relevance"
        mock_st.slider.side_effect = [0.0, 1200]
        mock_st.date_input.return_value = None
        mock_st.checkbox.return_value = False
        mock_st.form_submit_button.return_value = False
        mock_st.button.return_value = False
        mock_labels.return_value = []
        mock_export.return_value = {}
        mock_csv.return_value = ""

        main()
        retriever.search_by_thread.assert_called_with("conv123")
        # Thread view header is rendered via st.markdown
        markdown_calls = [str(c) for c in mock_st.markdown.call_args_list]
        assert any("Conversation Thread" in c for c in markdown_calls)

    @patch("src.web_app._build_csv_export")
    @patch("src.web_app.build_export_payload")
    @patch("src.web_app.build_active_filter_labels")
    @patch("src.web_app.render_results")
    @patch("src.web_app.render_results_summary")
    @patch("src.web_app.render_sidebar")
    @patch("src.web_app.inject_styles")
    @patch("src.web_app.get_retriever")
    @patch("src.web_app.st")
    def test_main_thread_view_no_results(
        self,
        mock_st,
        mock_get_retriever,
        mock_inject,
        mock_sidebar,
        mock_summary,
        mock_render_results,
        mock_labels,
        mock_export,
        mock_csv,
    ):
        from src.web_app import main

        mock_st.sidebar.radio.return_value = "Search"
        mock_st.sidebar.text_input.return_value = ""
        retriever = MagicMock()
        retriever.collection.count.return_value = 10
        retriever.search_by_thread.return_value = []
        mock_get_retriever.return_value = retriever

        mock_st.session_state = {
            "web_results": [_result()],
            "web_query": "query",
            "web_filters": {},
            "web_sort": "relevance",
            "web_page": 0,
            "web_thread_id": "conv_empty",
        }
        mock_st.form.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_st.form.return_value.__exit__ = MagicMock(return_value=False)
        mock_st.columns.side_effect = _columns_side_effect
        mock_st.expander.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_st.expander.return_value.__exit__ = MagicMock(return_value=False)
        mock_st.text_input.return_value = ""
        mock_st.number_input.return_value = 10
        mock_st.selectbox.return_value = "Relevance"
        mock_st.slider.side_effect = [0.0, 1200]
        mock_st.date_input.return_value = None
        mock_st.checkbox.return_value = False
        mock_st.form_submit_button.return_value = False
        mock_st.button.return_value = False
        mock_labels.return_value = []
        mock_export.return_value = {}
        mock_csv.return_value = ""

        main()
        mock_st.info.assert_any_call("No emails found for this thread.")

    @patch("src.web_app.render_results")
    @patch("src.web_app.render_results_summary")
    @patch("src.web_app.render_sidebar")
    @patch("src.web_app.inject_styles")
    @patch("src.web_app.get_retriever")
    @patch("src.web_app.st")
    def test_main_search_with_all_filters(
        self,
        mock_st,
        mock_get_retriever,
        mock_inject,
        mock_sidebar,
        mock_summary,
        mock_render_results,
    ):
        from src.web_app import main

        retriever = MagicMock()
        retriever.collection.count.return_value = 10
        retriever.search_filtered.return_value = [_result()]
        mock_get_retriever.return_value = retriever

        _setup_main_search_st(
            mock_st,
            search_clicked=True,
            text_inputs=[
                "important query",
                "alice@example.test",
                "bob@example.test",
                "Contract",
                "Legal",
                "carol@example.test",
                "dave@example.test",
            ],
            number_inputs=[10, 3],
            selectbox_inputs=["Newest first", "reply"],
            slider_inputs=[0.5, 1200],
            checkbox_inputs=[True, True, True, True],
        )

        main()
        call_kwargs = retriever.search_filtered.call_args[1]
        assert call_kwargs["sender"] == "alice@example.test"
        assert call_kwargs["to"] == "bob@example.test"
        assert call_kwargs["has_attachments"] is True
        assert call_kwargs["priority"] == 3
        assert call_kwargs["email_type"] == "reply"
        assert call_kwargs["min_score"] == 0.5
        assert call_kwargs["hybrid"] is True
        assert call_kwargs["rerank"] is True
        assert call_kwargs["expand_query"] is True

    @patch("src.web_app._build_csv_export")
    @patch("src.web_app.build_export_payload")
    @patch("src.web_app.build_active_filter_labels")
    @patch("src.web_app.render_results")
    @patch("src.web_app.render_results_summary")
    @patch("src.web_app.render_sidebar")
    @patch("src.web_app.inject_styles")
    @patch("src.web_app.get_retriever")
    @patch("src.web_app.st")
    def test_main_pagination_multiple_pages(
        self,
        mock_st,
        mock_get_retriever,
        mock_inject,
        mock_sidebar,
        mock_summary,
        mock_render_results,
        mock_labels,
        mock_export,
        mock_csv,
    ):
        from src.web_app import main

        mock_st.sidebar.radio.return_value = "Search"
        mock_st.sidebar.text_input.return_value = ""
        retriever = MagicMock()
        retriever.collection.count.return_value = 10
        mock_get_retriever.return_value = retriever

        many_results = [_result(chunk_id=f"c{i}") for i in range(25)]
        mock_st.session_state = {
            "web_results": many_results,
            "web_query": "query",
            "web_filters": {},
            "web_sort": "relevance",
            "web_page": 0,
            "web_thread_id": None,
        }
        mock_st.form.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_st.form.return_value.__exit__ = MagicMock(return_value=False)
        mock_st.columns.side_effect = _columns_side_effect
        mock_st.expander.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_st.expander.return_value.__exit__ = MagicMock(return_value=False)
        mock_st.text_input.return_value = ""
        mock_st.number_input.return_value = 10
        mock_st.selectbox.return_value = "Relevance"
        mock_st.slider.side_effect = [0.0, 1200]
        mock_st.date_input.return_value = None
        mock_st.checkbox.return_value = False
        mock_st.form_submit_button.return_value = False
        mock_st.button.return_value = False
        mock_labels.return_value = []
        mock_export.return_value = {}
        mock_csv.return_value = ""

        main()
        render_call_args = mock_render_results.call_args
        page_results = render_call_args[0][0]
        assert len(page_results) == 20
