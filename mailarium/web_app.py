"""Local Streamlit UI for browsing and searching indexed emails."""

from __future__ import annotations

from typing import Any

import streamlit as st

try:
    from .formatting import format_date
    from .repo_paths import validate_runtime_path
    from .retriever import EmailRetriever
    from .validation import validate_date_window
    from .web_app_evidence import render_evidence_page_impl
    from .web_app_mailbox import render_mailbox_page_impl
    from .web_app_pages import (
        get_email_db_safe_impl,
        render_dashboard_page_impl,
        render_entity_page_impl,
        render_network_page_impl,
    )
    from .web_app_rendering import render_sidebar_impl
    from .web_app_results import (
        _type_badge_html,
        render_results_impl,
        render_results_summary_impl,
    )
    from .web_app_search import (
        _as_optional_float,
        _as_optional_str,
        _build_csv_export,
        render_search_page_impl,
    )
    from .web_app_styles import inject_styles_impl
    from .web_ui import build_active_filter_labels, build_export_payload, build_filter_chip_html, sort_search_results
except ImportError:  # pragma: no cover
    from mailarium.formatting import format_date
    from mailarium.repo_paths import validate_runtime_path
    from mailarium.retriever import EmailRetriever
    from mailarium.validation import validate_date_window
    from mailarium.web_app_evidence import render_evidence_page_impl
    from mailarium.web_app_mailbox import render_mailbox_page_impl
    from mailarium.web_app_pages import (
        get_email_db_safe_impl,
        render_dashboard_page_impl,
        render_entity_page_impl,
        render_network_page_impl,
    )
    from mailarium.web_app_rendering import render_sidebar_impl
    from mailarium.web_app_results import (
        _type_badge_html,
        render_results_impl,
        render_results_summary_impl,
    )
    from mailarium.web_app_search import (
        _as_optional_float,
        _as_optional_str,
        _build_csv_export,
        render_search_page_impl,
    )
    from mailarium.web_app_styles import inject_styles_impl
    from mailarium.web_ui import build_active_filter_labels, build_export_payload, build_filter_chip_html, sort_search_results

st.set_page_config(
    page_title="Mailarium - Email Discovery",
    page_icon="\u2709\ufe0f",
    layout="wide",
    initial_sidebar_state="auto",
)

SORT_OPTIONS = {
    "Relevance": "relevance",
    "Newest first": "date_desc",
    "Oldest first": "date_asc",
    "Sender A-Z": "sender_asc",
}

PAGE_SIZE = 20


@st.cache_resource
def get_retriever(vector_index_path: str | None, sqlite_path: str | None = None, _cache_version: int = 0):
    """Get or create a cached EmailRetriever instance."""
    if sqlite_path is None:
        return EmailRetriever(vector_index_path=vector_index_path)
    return EmailRetriever(vector_index_path=vector_index_path, sqlite_path=sqlite_path)


def invalidate_retriever_cache() -> None:
    """Invalidate the cached retriever so the next access creates a fresh one."""
    get_retriever.clear()


def render_sidebar(retriever: EmailRetriever) -> None:
    """Render the sidebar UI component."""
    render_sidebar_impl(st_module=st, retriever=retriever)


def render_results(results: list[Any], preview_chars: int, retriever: EmailRetriever | None = None) -> None:
    """Render search results with the given preview character limit."""
    render_results_impl(
        st_module=st,
        results=results,
        preview_chars=preview_chars,
        retriever=retriever,
        format_date_fn=format_date,
    )


def inject_styles() -> None:
    """Inject custom CSS styles into the Streamlit app."""
    inject_styles_impl(st_module=st)


def _render_brand_lockup() -> None:
    """Render the code-native Mailarium mark above the persistent navigation."""
    sidebar_markdown = getattr(st.sidebar, "markdown", None)
    if not callable(sidebar_markdown):
        return
    sidebar_markdown(
        """
        <div class="mailarium-lockup" aria-label="Mailarium">
          <span>MAILARIUM</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_runtime_status() -> None:
    """Render the accepted local-runtime status without adding a navigation destination."""
    sidebar_markdown = getattr(st.sidebar, "markdown", None)
    if not callable(sidebar_markdown):
        return
    sidebar_markdown(
        "<div class='runtime-status'><span aria-hidden='true'></span>Local archive ready"
        "<small>Runtime paths validated</small></div>",
        unsafe_allow_html=True,
    )


def render_results_summary(
    results: list[Any],
    active_filters: list[str],
    sort_label: str,
    search_modes: list[str] | None = None,
) -> None:
    """Render a summary of the search results."""
    render_results_summary_impl(
        st_module=st,
        results=results,
        active_filters=active_filters,
        sort_label=sort_label,
        search_modes=search_modes,
        build_filter_chip_html_fn=build_filter_chip_html,
    )


@st.cache_resource
def _get_email_db_safe(sqlite_path: str | None, _cache_version: int = 0):
    """Try to get EmailDatabase instance, return None if unavailable."""
    return get_email_db_safe_impl(sqlite_path=sqlite_path)


def render_dashboard_page(sqlite_path: str | None = None) -> None:
    """Render the dashboard page with analytics and metrics."""
    render_dashboard_page_impl(st_module=st, get_email_db_safe_fn=lambda: _get_email_db_safe(sqlite_path))


def render_entity_page(sqlite_path: str | None = None) -> None:
    """Render the entities page showing people and organizations."""
    render_entity_page_impl(st_module=st, get_email_db_safe_fn=lambda: _get_email_db_safe(sqlite_path))


def render_network_page(sqlite_path: str | None = None) -> None:
    """Render the network page showing communication graphs."""
    render_network_page_impl(st_module=st, get_email_db_safe_fn=lambda: _get_email_db_safe(sqlite_path))


def render_evidence_page(sqlite_path: str | None = None) -> None:
    """Render the evidence page showing collected evidence."""
    render_evidence_page_impl(
        st_module=st,
        get_email_db_safe_fn=lambda: _get_email_db_safe(sqlite_path),
        type_badge_html_fn=_type_badge_html,
    )


def render_search_page(retriever: EmailRetriever) -> None:
    """Render the search page UI."""
    render_search_page_impl(
        st_module=st,
        retriever=retriever,
        sort_options=SORT_OPTIONS,
        page_size=PAGE_SIZE,
        render_results_fn=render_results,
        render_results_summary_fn=render_results_summary,
        build_csv_export_fn=_build_csv_export,
        build_active_filter_labels_fn=build_active_filter_labels,
        build_export_payload_fn=build_export_payload,
        sort_search_results_fn=sort_search_results,
        validate_date_window_fn=validate_date_window,
        as_optional_str_fn=_as_optional_str,
        as_optional_float_fn=_as_optional_float,
    )


def render_mailbox_page(sqlite_path: str | None = None, vector_index_path: str | None = None) -> None:
    """Render mailbox status through the same service used by CLI and MCP."""
    from .config import get_settings
    from .mailbox_service import mailbox_service_for_path

    settings = get_settings()
    service = mailbox_service_for_path(
        sqlite_path or settings.sqlite_path,
        vector_index_path=vector_index_path or settings.vector_index_path,
    )
    try:
        render_mailbox_page_impl(st_module=st, service=service)
    finally:
        service.close()


def _render_non_search_page(page: str, sqlite_path: str | None, vector_index_path: str | None) -> bool:
    """Render a selected non-search page and report whether it was handled."""
    handlers = {
        "Overview": render_dashboard_page,
        "Dashboard": render_dashboard_page,
        "People": render_entity_page,
        "Entities": render_entity_page,
        "Connections": render_network_page,
        "Network": render_network_page,
        "Evidence": render_evidence_page,
    }
    handler = handlers.get(page)
    if handler:
        handler(sqlite_path)
        return True
    if page == "Mailbox":
        render_mailbox_page(sqlite_path, vector_index_path)
        return True
    return False


def _resolve_runtime_paths(vector_index_path: str | None, sqlite_path: str | None) -> tuple[str | None, str | None]:
    """Validate optional Streamlit runtime paths before opening application services."""
    resolved_vector_index_path = (
        str(validate_runtime_path(vector_index_path, field_name="vector index path")) if vector_index_path else None
    )
    resolved_sqlite_path = str(validate_runtime_path(sqlite_path, field_name="SQLite path")) if sqlite_path else None
    return resolved_vector_index_path, resolved_sqlite_path


def _render_runtime_path_inputs() -> tuple[str | None, str | None]:
    """Keep optional runtime overrides in a compact sidebar disclosure."""
    expander = getattr(st.sidebar, "expander", None)
    if callable(expander):
        with expander("Runtime paths", expanded=False):
            vector_index_path = st.sidebar.text_input("Vector Index Path", value="") or None
            sqlite_path = st.sidebar.text_input("SQLite Path", value="") or None
    else:  # Minimal Streamlit doubles and older compatible surfaces.
        vector_index_path = st.sidebar.text_input("Vector Index Path", value="") or None
        sqlite_path = st.sidebar.text_input("SQLite Path", value="") or None
    return vector_index_path, sqlite_path


def main() -> None:
    """Main entry point for the Streamlit web application."""
    inject_styles()
    _render_brand_lockup()

    page = st.sidebar.radio(
        "Navigate",
        ["Search", "Overview", "People", "Connections", "Evidence", "Mailbox"],
        index=0,
        label_visibility="collapsed",
    )

    vector_index_path, sqlite_path = _render_runtime_path_inputs()
    try:
        resolved_vector_index_path, resolved_sqlite_path = _resolve_runtime_paths(vector_index_path, sqlite_path)
    except ValueError as exc:
        st.error(f"Runtime paths are invalid: {exc}")
        return
    _render_runtime_status()

    if _render_non_search_page(page, resolved_sqlite_path, resolved_vector_index_path):
        return

    try:
        retriever = get_retriever(resolved_vector_index_path, resolved_sqlite_path)
    except (OSError, RuntimeError, ValueError) as exc:
        st.error(f"Runtime paths are invalid or unreadable: {exc}")
        return
    render_search_page(retriever)


if __name__ == "__main__":
    main()
