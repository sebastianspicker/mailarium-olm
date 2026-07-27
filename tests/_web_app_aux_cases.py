"""Web-app retrieval, session state, CSV export, and filter edge-case behavior."""

from unittest.mock import MagicMock, patch

from .helpers.web_app_fixtures import _result, _setup_main_session_results


class TestGetRetriever:
    @patch("mailarium.web_app.EmailRetriever")
    def test_get_retriever_creates_instance(self, mock_retriever_cls):
        from mailarium.web_app import get_retriever

        mock_retriever_cls.return_value = MagicMock()
        get_retriever.__wrapped__(None)
        mock_retriever_cls.assert_called_with(vector_index_path=None)

    @patch("mailarium.web_app.EmailRetriever")
    def test_get_retriever_with_path(self, mock_retriever_cls):
        from mailarium.web_app import get_retriever

        mock_retriever_cls.return_value = MagicMock()
        get_retriever.__wrapped__("/custom/path")
        mock_retriever_cls.assert_called_with(vector_index_path="/custom/path")


class TestConstants:
    def test_sort_options(self):
        from mailarium.web_app import SORT_OPTIONS

        assert SORT_OPTIONS["Relevance"] == "relevance"
        assert SORT_OPTIONS["Newest first"] == "date_desc"
        assert SORT_OPTIONS["Oldest first"] == "date_asc"
        assert SORT_OPTIONS["Sender A-Z"] == "sender_asc"

    def test_page_size(self):
        from mailarium.web_app import PAGE_SIZE

        assert PAGE_SIZE == 20


class TestBuildCsvExportEdge:
    def test_csv_multiple_results(self):
        from mailarium.web_app import _build_csv_export

        results = [_result(chunk_id=f"c{i}") for i in range(5)]
        csv_text = _build_csv_export(results)
        lines = csv_text.strip().split("\n")
        assert len(lines) == 6


class TestFilterExtraction:
    def test_as_optional_str_with_bool(self):
        from mailarium.web_app import _as_optional_str

        assert _as_optional_str(True) is None
        assert _as_optional_str(False) is None

    def test_as_optional_float_with_bool(self):
        from mailarium.web_app import _as_optional_float

        assert _as_optional_float(True) == 1.0
        assert _as_optional_float(False) == 0.0

    def test_as_optional_str_with_dict(self):
        from mailarium.web_app import _as_optional_str

        assert _as_optional_str({"key": "val"}) is None

    def test_as_optional_float_with_str(self):
        from mailarium.web_app import _as_optional_float

        assert _as_optional_float("3.14") is None


class TestMainSessionStateEdges:
    @patch("mailarium.web_app._build_csv_export")
    @patch("mailarium.web_app.build_export_payload")
    @patch("mailarium.web_app.build_active_filter_labels")
    @patch("mailarium.web_app.render_results")
    @patch("mailarium.web_app.render_results_summary")
    @patch("mailarium.web_app.render_sidebar")
    @patch("mailarium.web_app.inject_styles")
    @patch("mailarium.web_app.get_retriever")
    @patch("mailarium.web_app.st")
    def test_main_sort_label_from_session(  # pylint: disable=too-many-arguments,too-many-positional-arguments
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
        from mailarium.web_app import main

        retriever = MagicMock()
        retriever.collection.count.return_value = 10
        mock_get_retriever.return_value = retriever
        _setup_main_session_results(mock_st, results=[_result()], sort="date_desc")
        mock_labels.return_value = []
        mock_export.return_value = {}
        mock_csv.return_value = ""

        main()
        summary_call = mock_summary.call_args
        assert summary_call[0][2] == "Newest first"
