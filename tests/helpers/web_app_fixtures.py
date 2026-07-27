"""Streamlit mock setup and result factories for web application tests."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from mailarium.retriever import SearchResult

# ── Helpers ──────────────────────────────────────────────────────────


def _result(**overrides: object) -> SearchResult:
    """Provide deterministic result behavior for focused test setup."""
    defaults: dict[str, object] = {
        "chunk_id": "c1",
        "score_distance": 0.2,
        "date": "2024-01-15",
        "sender_email": "a@example.com",
        "sender_name": "Alice",
        "subject": "Test Subject",
        "folder": "Inbox",
        "text": "Hello world body text",
        "to": "",
        "conversation_id": "",
        "email_type": "original",
        "attachment_count": "0",
        "attachment_names": "",
        "priority": "0",
    }
    unknown = sorted(set(overrides) - set(defaults))
    if unknown:
        raise TypeError(f"_result() got unexpected option(s): {', '.join(unknown)}")
    values = defaults | overrides
    return SearchResult(
        chunk_id=str(values["chunk_id"]),
        text=str(values["text"]),
        metadata={
            key: str(values[key])
            for key in (
                "subject",
                "sender_email",
                "sender_name",
                "date",
                "folder",
                "to",
                "conversation_id",
                "email_type",
                "attachment_count",
                "attachment_names",
                "priority",
            )
        },
        distance=float(str(values["score_distance"])),
    )


def _columns_side_effect(n, **_kwargs):
    """Return a function that produces exactly N MagicMock objects."""
    if isinstance(n, int):
        return [MagicMock() for _ in range(n)]
    if isinstance(n, list):
        return [MagicMock() for _ in n]
    return [MagicMock() for _ in range(3)]


def _sidebar_retriever(mock_st, *, stats, senders):
    """Configure the sidebar containers and return a retriever with supplied data."""
    mock_st.sidebar.expander.return_value.__enter__ = MagicMock(return_value=MagicMock())
    mock_st.sidebar.expander.return_value.__exit__ = MagicMock(return_value=False)
    mock_st.sidebar.columns.return_value = [MagicMock(), MagicMock(), MagicMock()]
    retriever = MagicMock()
    retriever.stats.return_value = stats
    retriever.list_senders.return_value = senders
    return retriever


def _setup_evidence_st(mock_st, *, selectbox_side_effect=None, slider_val=1, text_input_val="", button_val=False):
    """Common setup for evidence page tests."""
    mock_st.columns.side_effect = lambda n: [MagicMock() for _ in range(n)] if isinstance(n, int) else [MagicMock() for _ in n]
    mock_st.selectbox.side_effect = selectbox_side_effect or ["All", "html", 1]
    mock_st.slider.return_value = slider_val
    mock_st.text_input.return_value = text_input_val
    mock_st.button.return_value = button_val
    mock_st.expander.return_value.__enter__ = MagicMock(return_value=MagicMock())
    mock_st.expander.return_value.__exit__ = MagicMock(return_value=False)


def _setup_main_search_st(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    mock_st,
    *,
    search_clicked=False,
    text_inputs=None,
    number_inputs=None,
    selectbox_inputs=None,
    slider_inputs=None,
    date_inputs=None,
    checkbox_inputs=None,
):
    """Common setup for main() search page tests."""
    mock_st.sidebar.radio.return_value = "Search"
    mock_st.sidebar.text_input.return_value = ""
    mock_st.session_state = {}
    mock_st.form.return_value.__enter__ = MagicMock(return_value=MagicMock())
    mock_st.form.return_value.__exit__ = MagicMock(return_value=False)
    mock_st.columns.side_effect = _columns_side_effect
    mock_st.expander.return_value.__enter__ = MagicMock(return_value=MagicMock())
    mock_st.expander.return_value.__exit__ = MagicMock(return_value=False)

    mock_st.text_input.side_effect = text_inputs or ["", "", "", "", "", "", "", ""]
    mock_st.number_input.side_effect = number_inputs or [10, 0]
    mock_st.selectbox.side_effect = [*(selectbox_inputs or ["Relevance", "Any"]), "General"]
    mock_st.slider.side_effect = slider_inputs or [0.0, 1200]
    mock_st.date_input.side_effect = date_inputs or [None, None]
    mock_st.checkbox.side_effect = checkbox_inputs or [False, False, False, False]
    mock_st.form_submit_button.return_value = search_clicked
    mock_st.button.return_value = False


def _setup_main_session_results(
    mock_st,
    *,
    results,
    query="query",
    filters=None,
    sort="relevance",
    page=0,
    thread_id=None,
):
    """Prepare the idle search form around a saved result-set or thread view."""
    _setup_main_search_st(mock_st)
    mock_st.text_input.side_effect = None
    mock_st.text_input.return_value = ""
    mock_st.number_input.side_effect = None
    mock_st.number_input.return_value = 10
    mock_st.selectbox.side_effect = None
    mock_st.selectbox.return_value = "Relevance"
    mock_st.date_input.side_effect = None
    mock_st.date_input.return_value = None
    mock_st.checkbox.side_effect = None
    mock_st.checkbox.return_value = False
    mock_st.session_state = {
        "web_results": results,
        "web_query": query,
        "web_filters": {} if filters is None else filters,
        "web_sort": sort,
        "web_page": page,
        "web_thread_id": thread_id,
    }


def _setup_dashboard_page(mock_st, mock_db_safe, *, contacts=None):
    """Supply the stable dashboard controls and a database double."""
    db = MagicMock()
    db.top_contacts.return_value = [] if contacts is None else contacts
    mock_db_safe.return_value = db
    mock_st.selectbox.return_value = "month"
    mock_st.text_input.return_value = ""
    return db


@contextmanager
def _patched_dashboard_chart_data(*, volume_data=None, heatmap_data=None, response_time_data=None):
    """Patch dashboard chart adapters with explicit test-specific data."""
    with (
        patch("mailarium.dashboard_charts.prepare_volume_chart_data") as volume,
        patch("mailarium.dashboard_charts.prepare_heatmap_data") as heatmap,
        patch("mailarium.dashboard_charts.prepare_response_times_data") as response_times,
        patch("mailarium.temporal_analysis.TemporalAnalyzer"),
    ):
        volume.return_value = [] if volume_data is None else volume_data
        heatmap.return_value = [[0] * 24 for _ in range(7)] if heatmap_data is None else heatmap_data
        response_times.return_value = [] if response_time_data is None else response_time_data
        yield


def _setup_evidence_page(
    mock_st,
    mock_db_safe,
    *,
    stats,
    categories,
    list_response=None,
    search_response=None,
    streamlit_options=None,
):
    """Provide only the evidence repository responses needed by one test."""
    db = MagicMock()
    db.evidence_stats.return_value = stats
    db.evidence_categories.return_value = categories
    if list_response is not None:
        db.list_evidence.return_value = list_response
    if search_response is not None:
        db.search_evidence.return_value = search_response
    mock_db_safe.return_value = db
    _setup_evidence_st(mock_st, **({} if streamlit_options is None else streamlit_options))
    return db


def _setup_verified_evidence_page(mock_st, mock_db_safe, *, list_response, streamlit_options=None):
    """Configure the common single verified harassment-evidence scenario."""
    return _setup_evidence_page(
        mock_st,
        mock_db_safe,
        stats={"total": 1, "verified": 1, "unverified": 0},
        categories=[{"category": "harassment", "count": 1}],
        list_response=list_response,
        streamlit_options=streamlit_options,
    )
