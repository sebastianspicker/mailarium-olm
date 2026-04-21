# ruff: noqa: F401
"""Extended tests for web_app.py — targeting >=80% coverage.

Every test mocks Streamlit calls and database dependencies to avoid
requiring real databases or a running Streamlit server.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.retriever import SearchResult

# ── Helpers ──────────────────────────────────────────────────────────


def _result(
    chunk_id: str = "c1",
    score_distance: float = 0.2,
    date: str = "2024-01-15",
    sender_email: str = "a@example.com",
    sender_name: str = "Alice",
    subject: str = "Test Subject",
    folder: str = "Inbox",
    text: str = "Hello world body text",
    to: str = "",
    conversation_id: str = "",
    email_type: str = "original",
    attachment_count: str = "0",
    attachment_names: str = "",
    priority: str = "0",
) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        text=text,
        metadata={
            "subject": subject,
            "sender_email": sender_email,
            "sender_name": sender_name,
            "date": date,
            "folder": folder,
            "to": to,
            "conversation_id": conversation_id,
            "email_type": email_type,
            "attachment_count": attachment_count,
            "attachment_names": attachment_names,
            "priority": priority,
        },
        distance=score_distance,
    )


def _columns_side_effect(n):
    """Return a function that produces exactly N MagicMock objects."""
    if isinstance(n, int):
        return [MagicMock() for _ in range(n)]
    if isinstance(n, list):
        return [MagicMock() for _ in n]
    return [MagicMock() for _ in range(3)]


def _setup_evidence_st(mock_st, *, selectbox_side_effect=None, slider_val=1, text_input_val="", button_val=False):
    """Common setup for evidence page tests."""
    mock_st.columns.side_effect = lambda n: [MagicMock() for _ in range(n)] if isinstance(n, int) else [MagicMock() for _ in n]
    mock_st.selectbox.side_effect = selectbox_side_effect or ["All", "html", 1]
    mock_st.slider.return_value = slider_val
    mock_st.text_input.return_value = text_input_val
    mock_st.button.return_value = button_val
    mock_st.expander.return_value.__enter__ = MagicMock(return_value=MagicMock())
    mock_st.expander.return_value.__exit__ = MagicMock(return_value=False)


def _setup_main_search_st(
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

    mock_st.text_input.side_effect = text_inputs or ["", "", "", "", "", "", ""]
    mock_st.number_input.side_effect = number_inputs or [10, 0]
    mock_st.selectbox.side_effect = selectbox_inputs or ["Relevance", "Any"]
    mock_st.slider.side_effect = slider_inputs or [0.0, 1200]
    mock_st.date_input.side_effect = date_inputs or [None, None]
    mock_st.checkbox.side_effect = checkbox_inputs or [False, False, False, False]
    mock_st.form_submit_button.return_value = search_clicked
    mock_st.button.return_value = False
