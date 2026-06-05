# ruff: noqa: F401,I001
# pylint: disable=unused-wildcard-import,wildcard-import


"""Extended tests for web_app.py — targeting >=80% coverage.

Every test mocks Streamlit calls and database dependencies to avoid
requiring real databases or a running Streamlit server.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.retriever import SearchResult

# ── Helpers ──────────────────────────────────────────────────────────

from .helpers.web_app_fixtures import _columns_side_effect, _result, _setup_evidence_st, _setup_main_search_st
from ._web_app_aux_cases import *  # noqa: F403


class TestMain:
    @contextmanager
    def _patch_main_deps(self):
        targets = {
            "st": "src.web_app.st",
            "get_retriever": "src.web_app.get_retriever",
            "inject": "src.web_app.inject_styles",
            "sidebar": "src.web_app.render_sidebar",
            "dashboard": "src.web_app.render_dashboard_page",
            "entity": "src.web_app.render_entity_page",
            "network": "src.web_app.render_network_page",
            "evidence": "src.web_app.render_evidence_page",
            "render_results": "src.web_app.render_results",
            "summary": "src.web_app.render_results_summary",
            "labels": "src.web_app.build_active_filter_labels",
            "export": "src.web_app.build_export_payload",
            "csv": "src.web_app._build_csv_export",
        }
        with ExitStack() as stack:
            mocks = {name: stack.enter_context(patch(target)) for name, target in targets.items()}
            mocks["export"].return_value = {}
            mocks["csv"].return_value = ""
            mocks["labels"].return_value = []
            yield SimpleNamespace(**mocks)

    def test_main_routes_to_dashboard(self):
        from src.web_app import main

        with self._patch_main_deps() as m:
            m.st.sidebar.radio.return_value = "Dashboard"
            m.st.sidebar.text_input.return_value = ""
            m.get_retriever.return_value = MagicMock()
            main()
            m.dashboard.assert_called_once()

    def test_main_routes_to_entities(self):
        from src.web_app import main

        with self._patch_main_deps() as m:
            m.st.sidebar.radio.return_value = "Entities"
            m.st.sidebar.text_input.return_value = ""
            m.get_retriever.return_value = MagicMock()
            main()
            m.entity.assert_called_once()

    def test_main_routes_to_network(self):
        from src.web_app import main

        with self._patch_main_deps() as m:
            m.st.sidebar.radio.return_value = "Network"
            m.st.sidebar.text_input.return_value = ""
            m.get_retriever.return_value = MagicMock()
            main()
            m.network.assert_called_once()

    def test_main_routes_to_evidence(self):
        from src.web_app import main

        with self._patch_main_deps() as m:
            m.st.sidebar.radio.return_value = "Evidence"
            m.st.sidebar.text_input.return_value = ""
            m.get_retriever.return_value = MagicMock()
            main()
            m.evidence.assert_called_once()

    def test_main_empty_collection_shows_warning(self):
        from src.web_app import main

        with self._patch_main_deps() as m:
            m.st.sidebar.radio.return_value = "Search"
            m.st.sidebar.text_input.return_value = ""
            retriever = MagicMock()
            retriever.collection.count.return_value = 0
            m.get_retriever.return_value = retriever
            main()
            m.st.warning.assert_called_with("No emails indexed yet.")

    def test_main_search_no_query(self):
        from src.web_app import main

        with self._patch_main_deps() as m:
            retriever = MagicMock()
            retriever.collection.count.return_value = 10
            m.get_retriever.return_value = retriever
            _setup_main_search_st(m.st, search_clicked=True)

            main()
            m.st.warning.assert_called_with("Please enter a query.")

    def test_main_search_with_query_and_results(self):
        from src.web_app import main

        with self._patch_main_deps() as m:
            retriever = MagicMock()
            retriever.collection.count.return_value = 10
            retriever.search_filtered.return_value = [_result(), _result(chunk_id="c2")]
            m.get_retriever.return_value = retriever
            _setup_main_search_st(
                m.st,
                search_clicked=True,
                text_inputs=["contract renewal", "", "", "", "", "", ""],
            )

            main()
            retriever.search_filtered.assert_called_once()

    def test_main_search_invalid_date_range(self):
        from src.web_app import main

        with self._patch_main_deps() as m:
            retriever = MagicMock()
            retriever.collection.count.return_value = 10
            m.get_retriever.return_value = retriever

            date_from = MagicMock()
            date_from.__str__ = MagicMock(return_value="2025-06-01")
            date_from.__bool__ = MagicMock(return_value=True)
            date_to = MagicMock()
            date_to.__str__ = MagicMock(return_value="2024-01-01")
            date_to.__bool__ = MagicMock(return_value=True)

            _setup_main_search_st(
                m.st,
                search_clicked=True,
                text_inputs=["query", "", "", "", "", "", ""],
                date_inputs=[date_from, date_to],
            )

            main()
            m.st.error.assert_called_with("Date From cannot be later than Date To.")

    def test_main_search_no_results_in_session(self):
        from src.web_app import main

        with self._patch_main_deps() as m:
            retriever = MagicMock()
            retriever.collection.count.return_value = 10
            m.get_retriever.return_value = retriever
            _setup_main_search_st(m.st, search_clicked=False)

            main()
            m.st.info.assert_called()

    def test_main_with_existing_results_in_session(self):
        from src.web_app import main

        with self._patch_main_deps() as m:
            m.st.sidebar.radio.return_value = "Search"
            m.st.sidebar.text_input.return_value = ""
            retriever = MagicMock()
            retriever.collection.count.return_value = 10
            m.get_retriever.return_value = retriever

            existing_results = [_result(), _result(chunk_id="c2")]
            m.st.session_state = {
                "web_results": existing_results,
                "web_query": "old query",
                "web_filters": {"sender": "alice"},
                "web_sort": "relevance",
                "web_page": 0,
                "web_thread_id": None,
            }
            m.st.form.return_value.__enter__ = MagicMock(return_value=MagicMock())
            m.st.form.return_value.__exit__ = MagicMock(return_value=False)
            m.st.columns.side_effect = _columns_side_effect
            m.st.expander.return_value.__enter__ = MagicMock(return_value=MagicMock())
            m.st.expander.return_value.__exit__ = MagicMock(return_value=False)
            m.st.text_input.return_value = ""
            m.st.number_input.return_value = 10
            m.st.selectbox.return_value = "Relevance"
            m.st.slider.side_effect = [0.0, 1200]
            m.st.date_input.return_value = None
            m.st.checkbox.return_value = False
            m.st.form_submit_button.return_value = False
            m.st.button.return_value = False
            m.labels.return_value = []
            m.export.return_value = {}
            m.csv.return_value = ""

            main()
            m.render_results.assert_called_once()
            m.summary.assert_called_once()

    def test_main_with_thread_view(self):
        from src.web_app import main

        with self._patch_main_deps() as m:
            m.st.sidebar.radio.return_value = "Search"
            m.st.sidebar.text_input.return_value = ""
            retriever = MagicMock()
            retriever.collection.count.return_value = 10
            thread_results = [_result(subject="Thread Email 1")]
            retriever.search_by_thread.return_value = thread_results
            m.get_retriever.return_value = retriever

            m.st.session_state = {
                "web_results": [_result()],
                "web_query": "query",
                "web_filters": {},
                "web_sort": "relevance",
                "web_page": 0,
                "web_thread_id": "conv123",
            }
            m.st.form.return_value.__enter__ = MagicMock(return_value=MagicMock())
            m.st.form.return_value.__exit__ = MagicMock(return_value=False)
            m.st.columns.side_effect = _columns_side_effect
            m.st.expander.return_value.__enter__ = MagicMock(return_value=MagicMock())
            m.st.expander.return_value.__exit__ = MagicMock(return_value=False)
            m.st.text_input.return_value = ""
            m.st.number_input.return_value = 10
            m.st.selectbox.return_value = "Relevance"
            m.st.slider.side_effect = [0.0, 1200]
            m.st.date_input.return_value = None
            m.st.checkbox.return_value = False
            m.st.form_submit_button.return_value = False
            m.st.button.return_value = False
            m.labels.return_value = []
            m.export.return_value = {}
            m.csv.return_value = ""

            main()
            retriever.search_by_thread.assert_called_with("conv123")
            markdown_calls = [str(c) for c in m.st.markdown.call_args_list]
            assert any("Conversation Thread" in c for c in markdown_calls)

    def test_main_thread_view_no_results(self):
        from src.web_app import main

        with self._patch_main_deps() as m:
            m.st.sidebar.radio.return_value = "Search"
            m.st.sidebar.text_input.return_value = ""
            retriever = MagicMock()
            retriever.collection.count.return_value = 10
            retriever.search_by_thread.return_value = []
            m.get_retriever.return_value = retriever

            m.st.session_state = {
                "web_results": [_result()],
                "web_query": "query",
                "web_filters": {},
                "web_sort": "relevance",
                "web_page": 0,
                "web_thread_id": "conv_empty",
            }
            m.st.form.return_value.__enter__ = MagicMock(return_value=MagicMock())
            m.st.form.return_value.__exit__ = MagicMock(return_value=False)
            m.st.columns.side_effect = _columns_side_effect
            m.st.expander.return_value.__enter__ = MagicMock(return_value=MagicMock())
            m.st.expander.return_value.__exit__ = MagicMock(return_value=False)
            m.st.text_input.return_value = ""
            m.st.number_input.return_value = 10
            m.st.selectbox.return_value = "Relevance"
            m.st.slider.side_effect = [0.0, 1200]
            m.st.date_input.return_value = None
            m.st.checkbox.return_value = False
            m.st.form_submit_button.return_value = False
            m.st.button.return_value = False
            m.labels.return_value = []
            m.export.return_value = {}
            m.csv.return_value = ""

            main()
            m.st.info.assert_any_call("No emails found for this thread.")

    def test_main_search_with_all_filters(self):
        from src.web_app import main

        with self._patch_main_deps() as m:
            retriever = MagicMock()
            retriever.collection.count.return_value = 10
            retriever.search_filtered.return_value = [_result()]
            m.get_retriever.return_value = retriever

            _setup_main_search_st(
                m.st,
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

    def test_main_pagination_multiple_pages(self):
        from src.web_app import main

        with self._patch_main_deps() as m:
            m.st.sidebar.radio.return_value = "Search"
            m.st.sidebar.text_input.return_value = ""
            retriever = MagicMock()
            retriever.collection.count.return_value = 10
            m.get_retriever.return_value = retriever

            many_results = [_result(chunk_id=f"c{i}") for i in range(25)]
            m.st.session_state = {
                "web_results": many_results,
                "web_query": "query",
                "web_filters": {},
                "web_sort": "relevance",
                "web_page": 0,
                "web_thread_id": None,
            }
            m.st.form.return_value.__enter__ = MagicMock(return_value=MagicMock())
            m.st.form.return_value.__exit__ = MagicMock(return_value=False)
            m.st.columns.side_effect = _columns_side_effect
            m.st.expander.return_value.__enter__ = MagicMock(return_value=MagicMock())
            m.st.expander.return_value.__exit__ = MagicMock(return_value=False)
            m.st.text_input.return_value = ""
            m.st.number_input.return_value = 10
            m.st.selectbox.return_value = "Relevance"
            m.st.slider.side_effect = [0.0, 1200]
            m.st.date_input.return_value = None
            m.st.checkbox.return_value = False
            m.st.form_submit_button.return_value = False
            m.st.button.return_value = False
            m.labels.return_value = []
            m.export.return_value = {}
            m.csv.return_value = ""

            main()
            render_call_args = m.render_results.call_args
            page_results = render_call_args[0][0]
            assert len(page_results) == 20
