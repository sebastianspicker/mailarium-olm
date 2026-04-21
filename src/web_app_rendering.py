"""Rendering helpers for the Streamlit email browser."""

from __future__ import annotations

from typing import Any


def render_sidebar_impl(*, st_module: Any, retriever: Any) -> None:
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


def inject_styles_impl(*, st_module: Any) -> None:
    st_module.markdown(
        """
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
        """,
        unsafe_allow_html=True,
    )


def _score_css_class(score: float) -> str:
    if score >= 0.75:
        return "score-high"
    if score >= 0.45:
        return "score-mid"
    return "score-low"


def _type_badge_html(email_type: str | None) -> str:
    if not email_type or email_type == "original":
        return ""
    css_class = f"type-{email_type}" if email_type in ("reply", "forward") else "type-original"
    return f" <span class='type-badge {css_class}'>{email_type}</span>"


def _attachment_badge_html(att_count: str | int) -> str:
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
    from html import escape as html_escape

    st_module.markdown("### Matching Emails")

    for index, result in enumerate(results, 1):
        metadata = result.metadata
        title = html_escape(metadata.get("subject", "(no subject)"))
        sender_name = html_escape(metadata.get("sender_name", ""))
        sender_email_val = html_escape(metadata.get("sender_email", ""))
        sender_display = sender_name or sender_email_val or "?"
        date_value = str(metadata.get("date", "?"))[:10]
        folder = html_escape(metadata.get("folder", "Unknown"))
        body = result.text or ""
        preview = body if len(body) <= preview_chars else f"{body[:preview_chars]}..."
        score = float(result.score)

        email_type = metadata.get("email_type", "original")
        att_count = metadata.get("attachment_count", "0")
        score_pct = f"{score:.0%}"
        expander_label = f"{index}. {title}  --  {sender_display}  |  {date_value}  |  {score_pct}"

        with st_module.expander(expander_label, expanded=index == 1):
            score_class = _score_css_class(score)
            badges_html = f"<span class='score-badge {score_class}'>{score_pct}</span>"
            badges_html += _type_badge_html(email_type)
            badges_html += _attachment_badge_html(att_count)
            st_module.markdown(badges_html, unsafe_allow_html=True)

            meta_col1, meta_col2, meta_col3, meta_col4 = st_module.columns(4)
            with meta_col1:
                st_module.markdown(
                    f"<div class='email-field'><strong>From:</strong> {sender_display}</div>",
                    unsafe_allow_html=True,
                )
            with meta_col2:
                to_value = metadata.get("to", "")
                if to_value:
                    to_list = [t.strip() for t in str(to_value).split(",") if t.strip()]
                    to_display = html_escape(", ".join(to_list[:3]))
                    if len(to_list) > 3:
                        to_display += f" (+{len(to_list) - 3})"
                    st_module.markdown(
                        f"<div class='email-field'><strong>To:</strong> {to_display}</div>",
                        unsafe_allow_html=True,
                    )
            with meta_col3:
                st_module.markdown(
                    f"<div class='email-field'><strong>Folder:</strong> {folder}</div>",
                    unsafe_allow_html=True,
                )
            with meta_col4:
                formatted_date = format_date_fn(str(metadata.get("date", "")))
                st_module.markdown(
                    f"<div class='email-field'><strong>Date:</strong> {formatted_date or date_value}</div>",
                    unsafe_allow_html=True,
                )

            att_names = metadata.get("attachment_names", "")
            if att_names and str(att_names).strip():
                st_module.markdown(
                    f"<div class='email-field'><strong>Attachments:</strong> {html_escape(str(att_names))}</div>",
                    unsafe_allow_html=True,
                )

            priority = metadata.get("priority", "0")
            if priority and str(priority) not in ("0", ""):
                st_module.markdown(
                    f"<div class='email-field'><strong>Priority:</strong> {html_escape(str(priority))}</div>",
                    unsafe_allow_html=True,
                )

            st_module.markdown(
                f"<div class='email-body-preview'>{html_escape(preview)}</div>",
                unsafe_allow_html=True,
            )

            if len(body) > preview_chars:
                with st_module.expander("Show full text", expanded=False):
                    st_module.markdown(
                        f"<div class='email-body-full'>{html_escape(body)}</div>",
                        unsafe_allow_html=True,
                    )

            btn_col1, btn_col2 = st_module.columns([1, 5])
            conv_id = str(metadata.get("conversation_id", "") or "").strip()
            with btn_col1:
                if conv_id and retriever is not None:
                    if st_module.button("View Thread", key=f"thread_{result.chunk_id}", type="secondary"):
                        st_module.session_state["web_thread_id"] = conv_id
                        st_module.rerun()
            with btn_col2:
                uid = metadata.get("uid", "")
                uid_short = uid[:12] + "..." if len(uid) > 12 else uid
                st_module.caption(f"UID: {uid_short} | Chunk: {result.chunk_id}")


def render_results_summary_impl(
    *,
    st_module: Any,
    results: list[Any],
    active_filters: list[str],
    sort_label: str,
    search_modes: list[str] | None,
    build_filter_chip_html_fn: Any,
) -> None:
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
