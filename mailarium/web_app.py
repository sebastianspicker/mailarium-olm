from __future__ import annotations

import threading
import weakref

import streamlit as st

from mailarium.interfaces.web.web_app_evidence import render_evidence_page_impl
from mailarium.interfaces.web.web_app_mailbox import render_mailbox_page_impl
from mailarium.interfaces.web.web_app_pages import render_dashboard_page_impl, render_entity_page_impl, render_network_page_impl
from mailarium.interfaces.web.web_app_results import _type_badge_html, render_results_summary_impl
from mailarium.interfaces.web.web_app_search import (
    _as_optional_float,
    _as_optional_str,
    _build_csv_export,
    render_search_page_impl,
)
from mailarium.interfaces.web.web_app_styles import inject_styles_impl
from mailarium.interfaces.web.web_ui import (
    build_active_filter_labels,
    build_export_payload,
    build_filter_chip_html,
    sort_search_results,
)
from mailarium.platform.repo_paths import validate_runtime_path
from mailarium.platform.validation import validate_date_window
from mailarium.runtime import ApplicationRuntime

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
_runtime_cache_lock = threading.Lock()
_runtime_instances: weakref.WeakValueDictionary[tuple[str | None, str | None], ApplicationRuntime] = weakref.WeakValueDictionary()


@st.cache_resource
def get_runtime(vector_index_path: str | None, sqlite_path: str | None = None) -> ApplicationRuntime:
    """Get the cached owner for one Streamlit archive path pair."""
    runtime = ApplicationRuntime(vector_index_path=vector_index_path, sqlite_path=sqlite_path)
    with _runtime_cache_lock:
        _runtime_instances[(vector_index_path, sqlite_path)] = runtime
    return runtime


def invalidate_runtime_cache() -> None:
    """Close and invalidate cached runtime resources before creating replacements."""
    with _runtime_cache_lock:
        runtimes = list(_runtime_instances.values())
        _runtime_instances.clear()
    for runtime in runtimes:
        runtime.close()
    get_runtime.clear()


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


def _render_non_search_page(page: str, runtime: ApplicationRuntime) -> bool:
    """Render a selected non-search page and report whether it was handled."""
    handlers = {
        "Overview": render_dashboard_page_impl,
        "Dashboard": render_dashboard_page_impl,
        "People": render_entity_page_impl,
        "Entities": render_entity_page_impl,
        "Connections": render_network_page_impl,
        "Network": render_network_page_impl,
    }
    handler = handlers.get(page)
    if handler:
        handler(st_module=st, database=runtime.archive_database)
        return True
    if page == "Evidence":
        render_evidence_page_impl(
            st_module=st,
            database=runtime.archive_database,
            type_badge_html_fn=_type_badge_html,
        )
        return True
    if page == "Mailbox":
        service = runtime.mailbox_service(create_archive=True)
        if service is None:  # pragma: no cover - create_archive always supplies the canonical archive.
            st.warning("SQLite database not available. Run ingestion first to enable mailbox state.")
            return True
        render_mailbox_page_impl(st_module=st, service=service)
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
    inject_styles_impl(st_module=st)
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

    try:
        runtime = get_runtime(resolved_vector_index_path, resolved_sqlite_path)
    except (OSError, RuntimeError, ValueError) as exc:
        st.error(f"Runtime paths are invalid or unreadable: {exc}")
        return

    if _render_non_search_page(page, runtime):
        return

    try:
        retriever = runtime.search_engine
    except (OSError, RuntimeError, ValueError) as exc:
        st.error(f"Runtime paths are invalid or unreadable: {exc}")
        return
    render_search_page_impl(
        st_module=st,
        retriever=retriever,
        sort_options=SORT_OPTIONS,
        page_size=PAGE_SIZE,
        render_results_summary_fn=lambda results, active_filters, sort_label, search_modes=None: render_results_summary_impl(
            st_module=st,
            results=results,
            active_filters=active_filters,
            sort_label=sort_label,
            search_modes=search_modes,
            build_filter_chip_html_fn=build_filter_chip_html,
        ),
        build_csv_export_fn=_build_csv_export,
        build_active_filter_labels_fn=build_active_filter_labels,
        build_export_payload_fn=build_export_payload,
        sort_search_results_fn=sort_search_results,
        validate_date_window_fn=validate_date_window,
        as_optional_str_fn=_as_optional_str,
        as_optional_float_fn=_as_optional_float,
    )


if __name__ == "__main__":
    main()
