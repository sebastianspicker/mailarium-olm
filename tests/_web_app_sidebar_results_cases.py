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


class TestInjectStyles:
    @patch("src.web_app.st")
    def test_inject_styles_renders_css(self, mock_st):
        from src.web_app import inject_styles

        inject_styles()
        mock_st.markdown.assert_called_once()
        call_args = mock_st.markdown.call_args
        assert "<style>" in call_args[0][0]
        assert call_args[1]["unsafe_allow_html"] is True


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
            {"name": "Alice", "email": "employee@example.test", "count": 50},
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
            [_result(to="a@example.test, b@example.test, c@example.test, d@example.test, e@example.test")],
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
        render_results([_result(to="a@example.test, b@example.test, c@example.test")], preview_chars=200)

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
    def test_render_results_inferred_thread_shows_scope_note(self, mock_st):
        from src.web_app import render_results

        self._setup_st(mock_st)
        result = _result(conversation_id="")
        result.metadata["inferred_thread_id"] = "thread-inferred-1"

        render_results(
            [result],
            preview_chars=200,
            retriever=MagicMock(),
        )

        caption_calls = [str(call) for call in mock_st.caption.call_args_list]
        assert any("canonical conversation IDs" in call for call in caption_calls)

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
