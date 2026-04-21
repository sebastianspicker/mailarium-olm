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


# ── inject_styles ────────────────────────────────────────────────────


class TestInjectStyles:
    @patch("src.web_app.st")
    def test_inject_styles_renders_css(self, mock_st):
        from src.web_app import inject_styles

        inject_styles()
        mock_st.markdown.assert_called_once()
        call_args = mock_st.markdown.call_args
        assert "<style>" in call_args[0][0]
        assert call_args[1]["unsafe_allow_html"] is True


# ── render_sidebar ───────────────────────────────────────────────────


class TestRenderSidebar:
    @patch("src.web_app.st")
    def test_render_sidebar_with_stats_and_folders(self, mock_st):
        from src.web_app import render_sidebar

        mock_st.sidebar.expander.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_st.sidebar.expander.return_value.__exit__ = MagicMock(return_value=False)
        mock_st.sidebar.columns.return_value = [MagicMock(), MagicMock(), MagicMock()]

        retriever = MagicMock()
        retriever.stats.return_value = {
            "total_emails": 100,
            "total_chunks": 500,
            "unique_senders": 25,
            "date_range": {"earliest": "2020-01-01", "latest": "2024-06-15"},
            "folders": {"Inbox": 80, "Sent": 20},
        }
        retriever.list_senders.return_value = [
            {"name": "Alice", "email": "alice@example.com", "count": 50},
            {"name": "Bob", "email": "bob@example.com", "count": 30},
        ]

        render_sidebar(retriever)

        mock_st.sidebar.markdown.assert_any_call("#### Archive Overview")
        # Uses columns for metrics
        mock_st.sidebar.columns.assert_called()

    @patch("src.web_app.st")
    def test_render_sidebar_no_folders(self, mock_st):
        from src.web_app import render_sidebar

        mock_st.sidebar.expander.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_st.sidebar.expander.return_value.__exit__ = MagicMock(return_value=False)
        mock_st.sidebar.columns.return_value = [MagicMock(), MagicMock(), MagicMock()]

        retriever = MagicMock()
        retriever.stats.return_value = {
            "total_emails": 0,
            "total_chunks": 0,
            "unique_senders": 0,
            "date_range": {},
            "folders": {},
        }
        retriever.list_senders.return_value = []

        render_sidebar(retriever)

        mock_st.sidebar.caption.assert_called()

    @patch("src.web_app.st")
    def test_render_sidebar_sender_with_no_name(self, mock_st):
        from src.web_app import render_sidebar

        mock_st.sidebar.expander.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_st.sidebar.expander.return_value.__exit__ = MagicMock(return_value=False)
        mock_st.sidebar.columns.return_value = [MagicMock(), MagicMock(), MagicMock()]

        retriever = MagicMock()
        retriever.stats.return_value = {
            "total_emails": 1,
            "total_chunks": 1,
            "unique_senders": 1,
            "date_range": {"earliest": "2024-01-01", "latest": "2024-01-01"},
            "folders": {},
        }
        retriever.list_senders.return_value = [
            {"name": "", "email": "anon@example.com", "count": 5},
        ]

        render_sidebar(retriever)

        # Sender with empty name now uses email as fallback
        markdown_calls = [str(c) for c in mock_st.sidebar.markdown.call_args_list]
        assert any("anon@example.com" in c for c in markdown_calls)


# ── render_results ───────────────────────────────────────────────────


class TestRenderResults:
    def _setup_st(self, mock_st):
        mock_st.expander.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_st.expander.return_value.__exit__ = MagicMock(return_value=False)
        mock_st.columns.side_effect = _columns_side_effect

    @patch("src.web_app.st")
    def test_render_results_basic(self, mock_st):
        from src.web_app import render_results

        self._setup_st(mock_st)
        render_results([_result()], preview_chars=200)
        # Uses markdown header instead of subheader
        markdown_calls = [str(c) for c in mock_st.markdown.call_args_list]
        assert any("Matching Emails" in c for c in markdown_calls)

    @patch("src.web_app.st")
    def test_render_results_long_body_shows_full_expander(self, mock_st):
        from src.web_app import render_results

        self._setup_st(mock_st)
        render_results([_result(text="x" * 500)], preview_chars=200)
        assert mock_st.expander.call_count >= 2

    @patch("src.web_app.st")
    def test_render_results_with_to_recipients_truncated(self, mock_st):
        from src.web_app import render_results

        self._setup_st(mock_st)
        render_results(
            [_result(to="a@x.com, b@x.com, c@x.com, d@x.com, e@x.com")],
            preview_chars=200,
        )
        # Verify columns were called
        mock_st.columns.assert_called()

    @patch("src.web_app.st")
    def test_render_results_type_badge_and_att_badge(self, mock_st):
        from src.web_app import render_results

        self._setup_st(mock_st)
        render_results(
            [_result(email_type="reply", attachment_count="3")],
            preview_chars=200,
        )
        # Badges are now rendered as HTML inside the expander, not in the title
        markdown_calls = [str(c) for c in mock_st.markdown.call_args_list]
        assert any("reply" in c.lower() for c in markdown_calls)
        assert any("3 att" in c for c in markdown_calls)

    @patch("src.web_app.st")
    def test_render_results_attachment_names_shown(self, mock_st):
        from src.web_app import render_results

        self._setup_st(mock_st)
        render_results([_result(attachment_names="doc.pdf")], preview_chars=200)
        # Attachment names are now rendered via st.markdown
        markdown_calls = [str(c) for c in mock_st.markdown.call_args_list]
        assert any("doc.pdf" in c for c in markdown_calls)

    @patch("src.web_app.st")
    def test_render_results_priority_shown(self, mock_st):
        from src.web_app import render_results

        self._setup_st(mock_st)
        render_results([_result(priority="3")], preview_chars=200)
        # Priority is now rendered via st.markdown
        markdown_calls = [str(c) for c in mock_st.markdown.call_args_list]
        assert any("Priority" in c for c in markdown_calls)

    @patch("src.web_app.st")
    def test_render_results_thread_button(self, mock_st):
        from src.web_app import render_results

        self._setup_st(mock_st)
        mock_st.button.return_value = False
        mock_st.session_state = {}
        render_results(
            [_result(conversation_id="conv123")],
            preview_chars=200,
            retriever=MagicMock(),
        )
        mock_st.button.assert_called()

    @patch("src.web_app.st")
    def test_render_results_no_subject(self, mock_st):
        from src.web_app import render_results

        self._setup_st(mock_st)
        result = SearchResult(chunk_id="c1", text="body", metadata={}, distance=0.1)
        render_results([result], preview_chars=200)
        expander_title = mock_st.expander.call_args_list[0][0][0]
        assert "(no subject)" in expander_title

    @patch("src.web_app.st")
    def test_render_results_short_body_no_full_expander(self, mock_st):
        from src.web_app import render_results

        self._setup_st(mock_st)
        render_results([_result(text="short")], preview_chars=200)
        assert mock_st.expander.call_count == 1

    @patch("src.web_app.st")
    def test_render_results_no_to_recipients(self, mock_st):
        from src.web_app import render_results

        self._setup_st(mock_st)
        render_results([_result(to="")], preview_chars=200)
        # Verify it doesn't crash

    @patch("src.web_app.st")
    def test_render_results_exactly_3_recipients(self, mock_st):
        from src.web_app import render_results

        self._setup_st(mock_st)
        render_results([_result(to="a@x.com, b@x.com, c@x.com")], preview_chars=200)

    @patch("src.web_app.st")
    def test_render_results_empty_attachment_names(self, mock_st):
        from src.web_app import render_results

        self._setup_st(mock_st)
        render_results([_result(attachment_names="")], preview_chars=200)
        caption_calls = [str(c) for c in mock_st.caption.call_args_list]
        assert not any("Attachments:" in c for c in caption_calls)

    @patch("src.web_app.st")
    def test_render_results_priority_zero_not_shown(self, mock_st):
        from src.web_app import render_results

        self._setup_st(mock_st)
        render_results([_result(priority="0")], preview_chars=200)
        caption_calls = [str(c) for c in mock_st.caption.call_args_list]
        assert not any("Priority:" in c for c in caption_calls)

    @patch("src.web_app.st")
    def test_render_results_empty_priority_not_shown(self, mock_st):
        from src.web_app import render_results

        self._setup_st(mock_st)
        render_results([_result(priority="")], preview_chars=200)
        caption_calls = [str(c) for c in mock_st.caption.call_args_list]
        assert not any("Priority:" in c for c in caption_calls)

    @patch("src.web_app.st")
    def test_render_results_no_conversation_id_no_button(self, mock_st):
        from src.web_app import render_results

        self._setup_st(mock_st)
        render_results(
            [_result(conversation_id="")],
            preview_chars=200,
            retriever=MagicMock(),
        )
        mock_st.button.assert_not_called()

    @patch("src.web_app.st")
    def test_render_results_no_retriever_no_button(self, mock_st):
        from src.web_app import render_results

        self._setup_st(mock_st)
        render_results(
            [_result(conversation_id="conv123")],
            preview_chars=200,
            retriever=None,
        )
        mock_st.button.assert_not_called()

    @patch("src.web_app.st")
    def test_render_results_thread_button_clicked(self, mock_st):
        from src.web_app import render_results

        self._setup_st(mock_st)
        mock_st.button.return_value = True
        mock_st.session_state = {}

        render_results(
            [_result(conversation_id="conv_click")],
            preview_chars=200,
            retriever=MagicMock(),
        )
        assert mock_st.session_state.get("web_thread_id") == "conv_click"
        mock_st.rerun.assert_called()

    @patch("src.web_app.st")
    def test_render_results_original_email_type_no_badge(self, mock_st):
        from src.web_app import render_results

        self._setup_st(mock_st)
        render_results([_result(email_type="original")], preview_chars=200)
        expander_title = mock_st.expander.call_args_list[0][0][0]
        assert "[ORIGINAL]" not in expander_title

    @patch("src.web_app.st")
    def test_render_results_zero_att_no_badge(self, mock_st):
        from src.web_app import render_results

        self._setup_st(mock_st)
        render_results([_result(attachment_count="0")], preview_chars=200)
        expander_title = mock_st.expander.call_args_list[0][0][0]
        assert "att." not in expander_title

    @patch("src.web_app.st")
    def test_render_results_multiple(self, mock_st):
        from src.web_app import render_results

        self._setup_st(mock_st)
        render_results([_result(chunk_id=f"c{i}") for i in range(3)], preview_chars=200)
        assert mock_st.expander.call_count == 3

    @patch("src.web_app.st")
    def test_render_results_score_clamped(self, mock_st):
        from src.web_app import render_results

        self._setup_st(mock_st)
        # A negative distance yields a high score (>1.0) which should be rendered safely
        render_results([_result(score_distance=-0.5)], preview_chars=200)
        # Score is rendered as a styled badge via st.markdown, not st.progress
        markdown_calls = [str(c) for c in mock_st.markdown.call_args_list]
        assert any("score-badge" in c for c in markdown_calls)


# ── render_results_summary ───────────────────────────────────────────


class TestRenderResultsSummary:
    @patch("src.web_app.st")
    def test_renders_metrics(self, mock_st):
        from src.web_app import render_results_summary

        mock_st.columns.side_effect = _columns_side_effect
        render_results_summary(
            [_result(score_distance=0.2), _result(score_distance=0.4)],
            ["Sender: alice"],
            "Relevance",
        )

    @patch("src.web_app.st")
    def test_renders_filter_chips(self, mock_st):
        from src.web_app import render_results_summary

        mock_st.columns.side_effect = _columns_side_effect
        render_results_summary([_result()], ["Sender: alice", "Folder: Inbox"], "Relevance")
        mock_st.markdown.assert_called()

    @patch("src.web_app.st")
    def test_empty_results(self, mock_st):
        from src.web_app import render_results_summary

        cols = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
        mock_st.columns.return_value = cols
        render_results_summary([], [], "Relevance")
        cols[0].metric.assert_called_with("Results", 0)

    @patch("src.web_app.st")
    def test_no_filter_chips_when_empty(self, mock_st):
        from src.web_app import render_results_summary

        mock_st.columns.side_effect = _columns_side_effect
        render_results_summary([_result()], [], "Relevance")
        chip_calls = [c for c in mock_st.markdown.call_args_list if "filter-chip" in str(c)]
        assert len(chip_calls) == 0


# ── render_dashboard_page ────────────────────────────────────────────


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
        db.top_contacts.return_value = [{"partner": "bob@x.com", "total": 10}]
        mock_db_safe.return_value = db
        mock_st.selectbox.return_value = "month"
        mock_st.text_input.return_value = "me@x.com"

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
        mock_st.text_input.return_value = "nobody@x.com"

        with (
            patch("src.dashboard_charts.prepare_volume_chart_data", return_value=[]),
            patch("src.dashboard_charts.prepare_heatmap_data", return_value=[[0] * 24 for _ in range(7)]),
            patch("src.dashboard_charts.prepare_response_times_data", return_value=[]),
            patch("src.temporal_analysis.TemporalAnalyzer"),
        ):
            render_dashboard_page()

        mock_st.info.assert_any_call("No contacts found for nobody@x.com")

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


# ── render_entity_page ───────────────────────────────────────────────


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


# ── render_network_page ──────────────────────────────────────────────


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
                "most_connected": [{"email": "a@x.com", "degree": 20}],
                "communities": [
                    {"members": ["a@x.com", "b@x.com"]},
                    {"members": ["c@x.com"]},
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


# ── render_evidence_page ─────────────────────────────────────────────


def _setup_evidence_st(mock_st, *, selectbox_side_effect=None, slider_val=1, text_input_val="", button_val=False):
    """Common setup for evidence page tests."""
    mock_st.columns.side_effect = lambda n: [MagicMock() for _ in range(n)] if isinstance(n, int) else [MagicMock() for _ in n]
    mock_st.selectbox.side_effect = selectbox_side_effect or ["All", "html", 1]
    mock_st.slider.return_value = slider_val
    mock_st.text_input.return_value = text_input_val
    mock_st.button.return_value = button_val
    mock_st.expander.return_value.__enter__ = MagicMock(return_value=MagicMock())
    mock_st.expander.return_value.__exit__ = MagicMock(return_value=False)


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
        # Verify metrics were rendered

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
                    "sender_email": "x@x.com",
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


# ── main() ───────────────────────────────────────────────────────────


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
            text_inputs=["important query", "alice@x.com", "bob@x.com", "Contract", "Legal", "carol@x.com", "dave@x.com"],
            number_inputs=[10, 3],
            selectbox_inputs=["Newest first", "reply"],
            slider_inputs=[0.5, 1200],
            checkbox_inputs=[True, True, True, True],
        )

        main()
        call_kwargs = retriever.search_filtered.call_args[1]
        assert call_kwargs["sender"] == "alice@x.com"
        assert call_kwargs["to"] == "bob@x.com"
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

    @patch("src.web_app._build_csv_export")
    @patch("src.web_app.build_export_payload")
    @patch("src.web_app.build_active_filter_labels")
    @patch("src.web_app.render_results")
    @patch("src.web_app.render_results_summary")
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


# ── get_retriever ────────────────────────────────────────────────────


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


# ── Constants ────────────────────────────────────────────────────────


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


# ── _build_csv_export edge cases ─────────────────────────────────────


class TestBuildCsvExportEdge:
    def test_csv_multiple_results(self):
        from src.web_app import _build_csv_export

        results = [_result(chunk_id=f"c{i}") for i in range(5)]
        csv_text = _build_csv_export(results)
        lines = csv_text.strip().split("\n")
        assert len(lines) == 6


# ── Filter helper edge cases ────────────────────────────────────────


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
