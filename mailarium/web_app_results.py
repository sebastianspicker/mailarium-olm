"""Result-card rendering helpers for the Streamlit email browser."""

from __future__ import annotations

from typing import Any


def _score_css_class(score: float) -> str:
    if score >= 0.75:
        return "score-high"
    if score >= 0.45:
        return "score-mid"
    return "score-low"


def _type_badge_html(email_type: str | None) -> str:
    """Generate HTML for an email type badge (reply, forward, attachment, etc.)."""
    from html import escape as html_escape

    if not email_type or email_type == "original":
        return ""
    css_class = f"type-{email_type}" if email_type in ("reply", "forward") else "type-original"
    return f" <span class='type-badge {css_class}'>{html_escape(str(email_type))}</span>"


def _attachment_badge_html(att_count: str | int) -> str:
    """Generate HTML for an attachment count badge."""
    from html import escape as html_escape

    count = str(att_count)
    if count in ("0", "", "None"):
        return ""
    return f" <span class='type-badge type-attachment'>{html_escape(count)} att.</span>"


def render_results_impl(
    *,
    st_module: Any,
    results: list[Any],
    preview_chars: int,
    retriever: Any | None,
    format_date_fn: Any,
) -> None:
    """Render search results as expandable cards with metadata and preview text."""
    from html import escape as html_escape

    st_module.markdown("### Matching Emails")

    for index, result in enumerate(results, 1):
        _render_result_card(st_module, result, index, preview_chars, retriever, format_date_fn, html_escape)


def _render_result_card(st, result, index: int, preview_chars: int, retriever, format_date, escape) -> None:
    """Render one escaped result card with relevance badges, metadata, body, and actions."""
    metadata = result.metadata
    sender = escape(metadata.get("sender_name", "")) or escape(metadata.get("sender_email", "")) or "?"
    date = str(metadata.get("date", "?"))[:10]
    score = float(result.score)
    label = f"{index}. {escape(metadata.get('subject', '(no subject)'))}  --  {sender}  |  {date}  |  {score:.0%}"
    with st.expander(label, expanded=index == 1):
        badges = f"<span class='score-badge {_score_css_class(score)}'>{score:.0%}</span>"
        badges += _type_badge_html(metadata.get("email_type", "original"))
        badges += _attachment_badge_html(metadata.get("attachment_count", "0"))
        st.markdown(badges, unsafe_allow_html=True)
        _render_result_metadata(st, metadata, sender, date, format_date, escape)
        _render_result_body(st, result.text or "", preview_chars, escape)
        _render_result_actions(st, result, retriever)


def _render_result_metadata(st, metadata: dict, sender: str, date: str, format_date, escape) -> None:
    """Render sender, recipients, folder, date, attachment, and priority fields safely."""
    columns = st.columns(4)
    with columns[0]:
        st.markdown(f"<div class='email-field'><strong>From:</strong> {sender}</div>", unsafe_allow_html=True)
    with columns[1]:
        recipients = [item.strip() for item in str(metadata.get("to", "")).split(",") if item.strip()]
        if recipients:
            display = escape(", ".join(recipients[:3])) + (f" (+{len(recipients) - 3})" if len(recipients) > 3 else "")
            st.markdown(f"<div class='email-field'><strong>To:</strong> {display}</div>", unsafe_allow_html=True)
    with columns[2]:
        st.markdown(
            f"<div class='email-field'><strong>Folder:</strong> {escape(metadata.get('folder', 'Unknown'))}</div>",
            unsafe_allow_html=True,
        )
    with columns[3]:
        formatted = format_date(str(metadata.get("date", "")))
        st.markdown(f"<div class='email-field'><strong>Date:</strong> {formatted or date}</div>", unsafe_allow_html=True)
    for label, value in (("Attachments", metadata.get("attachment_names", "")), ("Priority", metadata.get("priority", "0"))):
        if value and str(value).strip() not in ("0", ""):
            st.markdown(f"<div class='email-field'><strong>{label}:</strong> {escape(str(value))}</div>", unsafe_allow_html=True)


def _render_result_body(st, body: str, preview_chars: int, escape) -> None:
    """Show a bounded escaped preview and expose full text only when truncated."""
    preview = body if len(body) <= preview_chars else f"{body[:preview_chars]}..."
    st.markdown(f"<div class='email-body-preview'>{escape(preview)}</div>", unsafe_allow_html=True)
    if len(body) > preview_chars:
        with st.expander("Show full text", expanded=False):
            st.markdown(f"<div class='email-body-full'>{escape(body)}</div>", unsafe_allow_html=True)


def _render_result_actions(st, result, retriever) -> None:
    """Open canonical threads and display stable UID and chunk diagnostics."""
    columns = st.columns([1, 5])
    conversation_id = str(result.metadata.get("conversation_id", "") or "").strip()
    with columns[0]:
        if (
            conversation_id
            and retriever is not None
            and st.button("View Thread", key=f"thread_{result.chunk_id}", type="secondary")
        ):
            st.session_state["web_thread_id"] = conversation_id
            st.rerun()
    with columns[1]:
        uid = result.metadata.get("uid", "")
        uid_short = uid[:12] + "..." if len(uid) > 12 else uid
        st.caption(f"UID: {uid_short} | Chunk: {result.chunk_id}")
        inferred = str(result.metadata.get("inferred_thread_id", "") or "").strip()
        if not conversation_id and inferred:
            st.caption(
                "Thread view in Streamlit is currently limited to canonical conversation IDs. "
                "Use CLI or MCP answer-context workflows for inferred-thread review."
            )


def render_results_summary_impl(
    *,
    st_module: Any,
    results: list[Any],
    active_filters: list[str],
    sort_label: str,
    search_modes: list[str] | None,
    build_filter_chip_html_fn: Any,
) -> None:
    """Render one compact results bar plus active modes and filters."""
    from html import escape as html_escape

    scores = [float(result.score) for result in results]
    avg_score = sum(scores) / len(scores) if scores else 0.0
    max_score = max(scores) if scores else 0.0

    mode_html = ""
    if search_modes:
        for mode in search_modes:
            css = "mode-semantic"
            if mode == "hybrid":
                css = "mode-hybrid"
            elif mode == "reranked":
                css = "mode-reranked"
            mode_html += f"<span class='search-mode-indicator is-active {css}'>{html_escape(str(mode))}</span>"
    filter_html = build_filter_chip_html_fn(active_filters) if active_filters else ""
    st_module.markdown(
        "<div class='result-summary'>"
        f"<strong>{len(results)} results</strong>"
        f"<span>{max_score:.0%} best &middot; {avg_score:.0%} average relevance</span>"
        f"<span class='result-sort'>Sorted by {html_escape(sort_label)}</span>"
        f"<span class='result-context'>{mode_html}{filter_html}</span>"
        "</div>",
        unsafe_allow_html=True,
    )
