"""Result-card rendering helpers for the Streamlit email browser."""

from __future__ import annotations

from typing import Any

import streamlit as st

from .presentation import build_filter_chip_html


def type_badge_html(email_type: str | None) -> str:
    """Generate HTML for an email type badge (reply, forward, attachment, etc.)."""
    from html import escape as html_escape

    if not email_type or email_type == "original":
        return ""
    css_class = f"type-{email_type}" if email_type in ("reply", "forward") else "type-original"
    return f" <span class='type-badge {css_class}'>{html_escape(str(email_type))}</span>"


def render_results_summary(
    *,
    results: list[Any],
    active_filters: list[str],
    sort_label: str,
    search_modes: list[str] | None,
) -> None:
    """Render one compact results bar plus active modes and filters."""
    from html import escape as html_escape

    mode_html = ""
    if search_modes:
        for mode in search_modes:
            css = "mode-semantic"
            if mode == "hybrid":
                css = "mode-hybrid"
            elif mode == "reranked":
                css = "mode-reranked"
            mode_html += f"<span class='search-mode-indicator is-active {css}'>{html_escape(str(mode))}</span>"
    filter_html = build_filter_chip_html(active_filters)
    st.markdown(
        "<div class='result-summary'>"
        f"<strong>Showing {len(results)} candidate messages</strong>"
        f"<span class='result-sort'>Sorted by {html_escape(sort_label)}</span>"
        f"<span class='result-context'>{mode_html}{filter_html}</span>"
        "</div>",
        unsafe_allow_html=True,
    )
