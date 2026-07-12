"""Rendering helpers for the Streamlit email browser."""
# pylint: disable=too-many-arguments,too-many-locals,too-many-statements

from __future__ import annotations

from typing import Any


def render_sidebar_impl(*, st_module: Any, retriever: Any) -> None:
    """Render the sidebar with archive statistics, folders, and top senders."""
    from html import escape as html_escape

    st_module.sidebar.markdown("#### Archive Overview")

    stats = retriever.stats()
    sidebar_col1, sidebar_col2, sidebar_col3 = st_module.sidebar.columns(3)
    sidebar_col1.metric("Emails", f"{stats.get('total_emails', 0):,}")
    sidebar_col2.metric("Chunks", f"{stats.get('total_chunks', 0):,}")
    sidebar_col3.metric("Senders", f"{stats.get('unique_senders', 0):,}")

    date_range = stats.get("date_range", {})
    earliest = date_range.get("earliest", "?")
    latest = date_range.get("latest", "?")
    st_module.sidebar.caption(f"{earliest}  to  {latest}")

    folders = stats.get("folders", {})
    if folders:
        with st_module.sidebar.expander("Folders", expanded=False):
            sorted_folders = sorted(folders.items(), key=lambda item: item[1], reverse=True)
            for folder_name, count in sorted_folders:
                st_module.sidebar.markdown(
                    f"<div style='display:flex;justify-content:space-between;font-size:0.82rem;padding:0.1rem 0;'>"
                    f"<span>{html_escape(folder_name)}</span><span style='color:#64748b;font-weight:600;'>{count:,}</span></div>",
                    unsafe_allow_html=True,
                )

    with st_module.sidebar.expander("Top Senders", expanded=False):
        senders = retriever.list_senders(limit=15)
        if not senders:
            st_module.caption("No senders indexed yet.")
        else:
            max_count = max(sender["count"] for sender in senders)
            for sender in senders:
                display_name = sender["name"] or sender["email"]
                pct = sender["count"] / max_count if max_count else 0.0
                st_module.sidebar.markdown(
                    f"<div style='font-size:0.8rem;margin-bottom:0.15rem;'>"
                    f"<span style='font-weight:500;'>{html_escape(display_name)}</span> "
                    f"<span style='color:#64748b;'>({sender['count']:,})</span></div>",
                    unsafe_allow_html=True,
                )
                st_module.sidebar.progress(pct)


_STYLE_CSS = """
        <style>
        :root {
            --bg-primary: #f8fafc;
            --bg-surface: #ffffff;
            --bg-muted: #f1f5f9;
            --ink-primary: #0f172a;
            --ink-secondary: #475569;
            --ink-muted: #94a3b8;
            --accent-blue: #2563eb;
            --accent-blue-soft: #dbeafe;
            --accent-green: #059669;
            --accent-green-soft: #d1fae5;
            --accent-amber: #d97706;
            --accent-amber-soft: #fef3c7;
            --accent-red: #dc2626;
            --accent-red-soft: #fee2e2;
            --border-light: #e2e8f0;
            --border-medium: #cbd5e1;
            --radius-sm: 6px;
            --radius-md: 8px;
            --radius-lg: 12px;
        }
        .hero-title {
            font-family: "Inter", "Segoe UI", -apple-system, sans-serif;
            color: var(--ink-primary);
            font-weight: 700;
            font-size: 1.8rem;
            letter-spacing: -0.02em;
            margin-bottom: 0;
        }
        .hero-subtitle {
            font-family: "Inter", "Segoe UI", -apple-system, sans-serif;
            color: var(--ink-secondary);
            font-size: 0.95rem;
            margin-bottom: 1.2rem;
        }
        .filter-chip {
            display: inline-block;
            margin: 0 0.35rem 0.35rem 0;
            padding: 0.2rem 0.55rem;
            border-radius: 999px;
            background: var(--accent-blue-soft);
            border: 1px solid #bfdbfe;
            color: #1e40af;
            font-size: 0.78rem;
            font-weight: 500;
            font-family: "Inter", "Segoe UI", -apple-system, sans-serif;
        }
        .email-field {
            font-size: 0.82rem;
            color: var(--ink-secondary);
            font-family: "Inter", "Segoe UI", -apple-system, sans-serif;
        }
        .email-field strong {
            color: var(--ink-primary);
            font-weight: 600;
        }
        .email-body-preview {
            font-family: "Inter", "Segoe UI", -apple-system, sans-serif;
            font-size: 0.88rem;
            line-height: 1.55;
            color: var(--ink-primary);
            padding: 0.75rem 1rem;
            background: var(--bg-muted);
            border-radius: var(--radius-md);
            border-left: 3px solid var(--border-medium);
            white-space: pre-wrap;
            word-wrap: break-word;
            max-height: 400px;
            overflow-y: auto;
        }
        .email-body-full {
            font-family: "Inter", "Segoe UI", -apple-system, sans-serif;
            font-size: 0.85rem;
            line-height: 1.6;
            color: var(--ink-primary);
            padding: 1rem;
            background: var(--bg-muted);
            border-radius: var(--radius-md);
            border: 1px solid var(--border-light);
            white-space: pre-wrap;
            word-wrap: break-word;
            max-height: 600px;
            overflow-y: auto;
        }
        .score-badge {
            display: inline-block;
            padding: 0.15rem 0.5rem;
            border-radius: var(--radius-sm);
            font-size: 0.78rem;
            font-weight: 600;
            font-family: "SF Mono", "Fira Code", "JetBrains Mono", monospace;
        }
        .score-high { background: var(--accent-green-soft); color: #065f46; }
        .score-mid { background: var(--accent-amber-soft); color: #92400e; }
        .score-low { background: var(--accent-red-soft); color: #991b1b; }
        .type-badge {
            display: inline-block;
            padding: 0.12rem 0.45rem;
            border-radius: var(--radius-sm);
            font-size: 0.72rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }
        .type-reply { background: #ede9fe; color: #5b21b6; }
        .type-forward { background: #fce7f3; color: #9d174d; }
        .type-original { background: var(--accent-blue-soft); color: #1e40af; }
        .type-attachment { background: #fef3c7; color: #92400e; }
        .thread-email {
            padding: 0.75rem 1rem;
            margin-bottom: 0.5rem;
            background: var(--bg-surface);
            border: 1px solid var(--border-light);
            border-radius: var(--radius-md);
            border-left: 3px solid var(--accent-blue);
        }
        .thread-email-header {
            font-size: 0.82rem;
            color: var(--ink-secondary);
            margin-bottom: 0.4rem;
        }
        .thread-email-body {
            font-size: 0.85rem;
            line-height: 1.5;
            color: var(--ink-primary);
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        [data-testid="stSidebar"] .stMetric label {
            font-size: 0.78rem;
            color: var(--ink-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        .search-mode-indicator {
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 0.25rem 0.6rem;
            border-radius: var(--radius-sm);
            font-size: 0.78rem;
            font-weight: 500;
            margin-right: 0.4rem;
        }
        .mode-semantic { background: #dbeafe; color: #1d4ed8; }
        .mode-hybrid { background: #ede9fe; color: #6d28d9; }
        .mode-reranked { background: #d1fae5; color: #047857; }
        .evidence-quote {
            font-family: "Inter", "Segoe UI", -apple-system, sans-serif;
            font-size: 0.88rem;
            line-height: 1.55;
            padding: 0.75rem 1rem;
            background: #fefce8;
            border-radius: var(--radius-md);
            border-left: 4px solid #eab308;
            color: #713f12;
            font-style: italic;
        }
        .pagination-info {
            text-align: center;
            font-size: 0.82rem;
            color: var(--ink-muted);
            padding: 0.5rem 0;
        }
        .empty-state {
            text-align: center;
            padding: 2rem 1rem;
            color: var(--ink-muted);
        }
        </style>
        """


def inject_styles_impl(*, st_module: Any) -> None:
    """Inject custom CSS styles for the Streamlit email browser UI."""
    st_module.markdown(_STYLE_CSS, unsafe_allow_html=True)


def _score_css_class(score: float) -> str:
    """Return the CSS class for a score badge based on the score value."""
    if score >= 0.75:
        return "score-high"
    if score >= 0.45:
        return "score-mid"
    return "score-low"


def _type_badge_html(email_type: str | None) -> str:
    """Generate HTML for an email type badge (reply, forward, attachment, etc.)."""
    if not email_type or email_type == "original":
        return ""
    css_class = f"type-{email_type}" if email_type in ("reply", "forward") else "type-original"
    return f" <span class='type-badge {css_class}'>{email_type}</span>"


def _attachment_badge_html(att_count: str | int) -> str:
    """Generate HTML for an attachment count badge."""
    count = str(att_count)
    if count in ("0", "", "None"):
        return ""
    return f" <span class='type-badge type-attachment'>{count} att.</span>"


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
    preview = body if len(body) <= preview_chars else f"{body[:preview_chars]}..."
    st.markdown(f"<div class='email-body-preview'>{escape(preview)}</div>", unsafe_allow_html=True)
    if len(body) > preview_chars:
        with st.expander("Show full text", expanded=False):
            st.markdown(f"<div class='email-body-full'>{escape(body)}</div>", unsafe_allow_html=True)


def _render_result_actions(st, result, retriever) -> None:
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
    """Render summary metrics and active filters above search results."""
    scores = [float(result.score) for result in results]
    avg_score = sum(scores) / len(scores) if scores else 0.0
    max_score = max(scores) if scores else 0.0
    min_score = min(scores) if scores else 0.0

    metric_col1, metric_col2, metric_col3, metric_col4 = st_module.columns(4)
    metric_col1.metric("Results", len(results))
    metric_col2.metric("Best Match", f"{max_score:.0%}")
    metric_col3.metric("Avg Relevance", f"{avg_score:.0%}")
    metric_col4.metric("Lowest Score", f"{min_score:.0%}")

    mode_html = ""
    if search_modes:
        for mode in search_modes:
            css = "mode-semantic"
            if mode == "hybrid":
                css = "mode-hybrid"
            elif mode == "reranked":
                css = "mode-reranked"
            mode_html += f"<span class='search-mode-indicator {css}'>{mode}</span>"
    mode_html += f"<span style='font-size:0.82rem;color:#64748b;'>Sorted by: {sort_label}</span>"
    st_module.markdown(mode_html, unsafe_allow_html=True)

    if active_filters:
        chips = build_filter_chip_html_fn(active_filters)
        st_module.markdown(chips, unsafe_allow_html=True)
