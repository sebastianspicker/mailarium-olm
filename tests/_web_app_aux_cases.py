from unittest.mock import MagicMock, patch

from .helpers.web_app_fixtures import _columns_side_effect, _result


class TestGetRetriever:
    @patch("src.web_app.EmailRetriever")
    def test_get_retriever_creates_instance(self, mock_retriever_cls):
        from src.web_app import get_retriever

        mock_retriever_cls.return_value = MagicMock()
        get_retriever.__wrapped__(None)
        mock_retriever_cls.assert_called_with(chromadb_path=None)

    @patch("src.web_app.EmailRetriever")
    def test_get_retriever_with_path(self, mock_retriever_cls):
        from src.web_app import get_retriever

        mock_retriever_cls.return_value = MagicMock()
        get_retriever.__wrapped__("/custom/path")
        mock_retriever_cls.assert_called_with(chromadb_path="/custom/path")


class TestConstants:
    def test_sort_options(self):
        from src.web_app import SORT_OPTIONS

        assert SORT_OPTIONS["Relevance"] == "relevance"
        assert SORT_OPTIONS["Newest first"] == "date_desc"
        assert SORT_OPTIONS["Oldest first"] == "date_asc"
        assert SORT_OPTIONS["Sender A-Z"] == "sender_asc"

    def test_page_size(self):
        from src.web_app import PAGE_SIZE

        assert PAGE_SIZE == 20


class TestBuildCsvExportEdge:
    def test_csv_multiple_results(self):
        from src.web_app import _build_csv_export

        results = [_result(chunk_id=f"c{i}") for i in range(5)]
        csv_text = _build_csv_export(results)
        lines = csv_text.strip().split("\n")
        assert len(lines) == 6


class TestFilterExtraction:
    def test_as_optional_str_with_bool(self):
        from src.web_app import _as_optional_str

        assert _as_optional_str(True) is None
        assert _as_optional_str(False) is None

    def test_as_optional_float_with_bool(self):
        from src.web_app import _as_optional_float

        assert _as_optional_float(True) == 1.0
        assert _as_optional_float(False) == 0.0

    def test_as_optional_str_with_dict(self):
        from src.web_app import _as_optional_str

        assert _as_optional_str({"key": "val"}) is None

    def test_as_optional_float_with_str(self):
        from src.web_app import _as_optional_float

        assert _as_optional_float("3.14") is None


class TestMainSessionStateEdges:
    @patch("src.web_app._build_csv_export")
    @patch("src.web_app._export_results")
    @patch("src.web_app._sort_label_from_value")
    @patch("src.web_app._render_results")
    @patch("src.web_app._results_summary")
    @patch("src.web_app.render_sidebar")
    @patch("src.web_app.inject_styles")
    @patch("src.web_app.get_retriever")
    @patch("src.web_app.st")
    def test_main_sort_label_from_session(
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

        mock_st.session_state = {
            "web_results": [_result()],
            "web_query": "query",
            "web_filters": {},
            "web_sort": "date_desc",
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
        summary_call = mock_summary.call_args
        assert summary_call[0][2] == "Newest first"
