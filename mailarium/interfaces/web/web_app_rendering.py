"""Rendering helpers for the Streamlit email browser."""

from __future__ import annotations

from typing import Any


def render_sidebar_impl(*, st_module: Any, retriever: Any, container: Any | None = None) -> None:
    """Render archive statistics, folders, and senders in a sidebar or overview rail."""
    from html import escape as html_escape

    target = container if container is not None else st_module.sidebar
    if container is not None:
        target.markdown("<span class='archive-overview-anchor' aria-hidden='true'></span>", unsafe_allow_html=True)
    target.markdown("#### Archive Overview")

    stats = retriever.stats()
    sidebar_col1, sidebar_col2, sidebar_col3 = target.columns(3)
    sidebar_col1.metric("Emails", f"{stats.get('total_emails', 0):,}")
    sidebar_col2.metric("Chunks", f"{stats.get('total_chunks', 0):,}")
    sidebar_col3.metric("Senders", f"{stats.get('unique_senders', 0):,}")

    date_range = stats.get("date_range", {})
    earliest = date_range.get("earliest")
    latest = date_range.get("latest")
    if earliest and latest:
        target.caption(f"{earliest}  to  {latest}")
    else:
        target.caption("No dated messages indexed.")

    folders = stats.get("folders", {})
    if folders:
        with target.expander("Folders", expanded=False):
            sorted_folders = sorted(folders.items(), key=lambda item: item[1], reverse=True)
            for folder_name, count in sorted_folders:
                st_module.markdown(
                    f"<div class='archive-stat-row'>"
                    f"<span>{html_escape(folder_name)}</span>"
                    f"<span class='archive-stat-count'>{count:,}</span></div>",
                    unsafe_allow_html=True,
                )

    with target.expander("Top Senders", expanded=False):
        senders = retriever.list_senders(limit=15)
        if not senders:
            st_module.caption("No senders indexed yet.")
        else:
            max_count = max(sender["count"] for sender in senders)
            for sender in senders:
                display_name = sender["name"] or sender["email"]
                pct = sender["count"] / max_count if max_count else 0.0
                st_module.markdown(
                    f"<div class='archive-sender-row'>"
                    f"<span class='archive-sender-name'>{html_escape(display_name)}</span> "
                    f"<span class='archive-stat-count'>({sender['count']:,})</span></div>",
                    unsafe_allow_html=True,
                )
                st_module.progress(pct)
