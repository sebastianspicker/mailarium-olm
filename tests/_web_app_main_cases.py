# ruff: noqa: I001
# pylint: disable=unused-wildcard-import,wildcard-import


"""Streamlit main-page routing, search state, filtering, failures, and pagination."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ──────────────────────────────────────────────────────────

from .helpers.web_app_fixtures import _result, _setup_main_search_st, _setup_main_session_results
from ._web_app_aux_cases import *  # noqa


class TestMain:
    @contextmanager
    def _patch_main_deps(self):
        targets = {
            "st": "mailarium.web_app.st",
            "get_retriever": "mailarium.web_app.get_retriever",
            "inject": "mailarium.web_app.inject_styles",
            "sidebar": "mailarium.web_app.render_sidebar_impl",
            "dashboard": "mailarium.web_app.render_dashboard_page",
            "entity": "mailarium.web_app.render_entity_page",
            "network": "mailarium.web_app.render_network_page",
            "evidence": "mailarium.web_app.render_evidence_page",
            "render_results": "mailarium.web_app.render_results",
            "summary": "mailarium.web_app.render_results_summary",
            "workspace": "mailarium.web_app_search.render_search_workspace_impl",
            "labels": "mailarium.web_app.build_active_filter_labels",
            "export": "mailarium.web_app.build_export_payload",
            "csv": "mailarium.web_app._build_csv_export",
        }
        with ExitStack() as stack:
            mocks = {name: stack.enter_context(patch(target)) for name, target in targets.items()}
            mocks["export"].return_value = {}
            mocks["csv"].return_value = ""
            mocks["labels"].return_value = []
            mocks["st"].sidebar.text_input.return_value = ""
            yield SimpleNamespace(**mocks)

    @pytest.mark.parametrize(
        ("page_name", "handler_name"),
        [
            ("Overview", "dashboard"),
            ("People", "entity"),
            ("Connections", "network"),
            ("Evidence", "evidence"),
        ],
    )
    def test_main_routes_to_page(self, page_name, handler_name):
        from mailarium.web_app import main

        with self._patch_main_deps() as m:
            m.st.sidebar.radio.return_value = page_name
            m.get_retriever.return_value = MagicMock()
            main()
            getattr(m, handler_name).assert_called_once()

    def test_main_empty_collection_shows_warning(self):
        from mailarium.web_app import main

        with self._patch_main_deps() as m:
            retriever = MagicMock()
            retriever.collection.count.return_value = 0
            m.get_retriever.return_value = retriever
            main()
            m.st.warning.assert_called_with("No emails indexed yet.")

    def test_main_search_no_query(self):
        from mailarium.web_app import main

        with self._patch_main_deps() as m:
            retriever = MagicMock()
            retriever.collection.count.return_value = 10
            m.get_retriever.return_value = retriever
            _setup_main_search_st(m.st, search_clicked=True)

            main()
            m.st.warning.assert_called_with("Please enter a query.")

    def test_main_search_with_query_and_results(self):
        from mailarium.web_app import main

        with self._patch_main_deps() as m:
            retriever = MagicMock()
            retriever.collection.count.return_value = 10
            retriever.search_filtered.return_value = [_result(), _result(chunk_id="c2")]
            m.get_retriever.return_value = retriever
            _setup_main_search_st(
                m.st,
                search_clicked=True,
                text_inputs=["contract renewal", "", "", "", "", "", "", ""],
            )

            main()
            retriever.search_filtered.assert_called_once()

    def test_main_search_invalid_date_range(self):
        from mailarium.web_app import main

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
                text_inputs=["query", "", "", "", "", "", "", ""],
                date_inputs=[date_from, date_to],
            )

            main()
            m.st.error.assert_called_with("Date From cannot be later than Date To.")

    def test_main_search_no_results_in_session(self):
        from mailarium.web_app import main

        with self._patch_main_deps() as m:
            retriever = MagicMock()
            retriever.collection.count.return_value = 10
            m.get_retriever.return_value = retriever
            _setup_main_search_st(m.st, search_clicked=False)

            main()
            m.st.info.assert_called()

    def test_main_with_existing_results_in_session(self):
        from mailarium.web_app import main

        with self._patch_main_deps() as m:
            m.st.sidebar.radio.return_value = "Search"
            m.st.sidebar.text_input.return_value = ""
            retriever = MagicMock()
            retriever.collection.count.return_value = 10
            m.get_retriever.return_value = retriever

            existing_results = [_result(), _result(chunk_id="c2")]
            _setup_main_session_results(
                m.st,
                results=existing_results,
                query="old query",
                filters={"sender": "alice"},
            )

            main()
            m.workspace.assert_called_once()
            m.summary.assert_called_once()

    def test_main_with_thread_view(self):
        from mailarium.web_app import main

        with self._patch_main_deps() as m:
            retriever = MagicMock()
            retriever.collection.count.return_value = 10
            thread_results = [_result(subject="Thread Email 1")]
            retriever.search_by_thread.return_value = thread_results
            m.get_retriever.return_value = retriever

            _setup_main_session_results(m.st, results=[_result()], thread_id="conv123")

            main()
            retriever.search_by_thread.assert_called_with("conv123")
            markdown_calls = [str(c) for c in m.st.markdown.call_args_list]
            assert any("Conversation Thread" in c for c in markdown_calls)

    def test_main_thread_view_no_results(self):
        from mailarium.web_app import main

        with self._patch_main_deps() as m:
            retriever = MagicMock()
            retriever.collection.count.return_value = 10
            retriever.search_by_thread.return_value = []
            m.get_retriever.return_value = retriever

            _setup_main_session_results(m.st, results=[_result()], thread_id="conv_empty")

            main()
            m.st.info.assert_any_call("No emails found for this thread.")

    def test_main_search_with_all_filters(self):
        from mailarium.web_app import main

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
                    "procurement",
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
            assert call_kwargs["scope"] == "procurement"

    def test_main_search_runtime_error_is_rendered_without_replacing_prior_results(self):
        from mailarium.web_app import main

        with self._patch_main_deps() as m:
            prior_results = [_result(chunk_id="prior")]
            retriever = MagicMock()
            retriever.collection.count.return_value = 10
            retriever.search_filtered.side_effect = RuntimeError("model cache unavailable")
            m.get_retriever.return_value = retriever
            _setup_main_search_st(
                m.st,
                search_clicked=True,
                text_inputs=["new query", "", "", "", "", "", "", "general"],
            )
            m.st.session_state["web_results"] = prior_results

            main()

            assert m.st.session_state["web_results"] == prior_results
            assert m.st.session_state["web_search_error"] == "RuntimeError"
            m.st.error.assert_called_with(
                "Search could not be completed. Check Admin diagnostics and the configured model/runtime paths."
            )

    def test_main_pagination_multiple_pages(self):
        from mailarium.web_app import main

        with self._patch_main_deps() as m:
            retriever = MagicMock()
            retriever.collection.count.return_value = 10
            m.get_retriever.return_value = retriever

            many_results = [_result(chunk_id=f"c{i}") for i in range(25)]
            _setup_main_session_results(m.st, results=many_results)

            main()
            workspace_call = m.workspace.call_args
            page_results = workspace_call.kwargs["page_results"]
            assert len(page_results) == 20
