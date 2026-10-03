"""Streamlit application composition: page configuration, cached runtime, and page routing."""

from __future__ import annotations

import threading
import weakref

import streamlit as st

from mailarium.interfaces.runtime import ApplicationRuntime
from mailarium.platform.repo_paths import validate_runtime_path

from .analytics import render_dashboard_page, render_entity_page, render_network_page
from .evidence import render_evidence_page
from .mailbox import render_mailbox_page
from .search import render_search_page
from .shell import bind_archive_session, render_archive_status, render_footer, render_header, render_navigation
from .styles import inject_styles

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


def _render_non_search_page(page: str, runtime: ApplicationRuntime) -> bool:
    """Render a selected non-search page and report whether it was handled."""
    handlers = {
        "Overview": render_dashboard_page,
        "Dashboard": render_dashboard_page,
        "People": render_entity_page,
        "Entities": render_entity_page,
        "Connections": render_network_page,
        "Network": render_network_page,
    }
    handler = handlers.get(page)
    if handler:
        handler(database=runtime.archive_database)
        return True
    if page == "Evidence":
        render_evidence_page(database=runtime.archive_database)
        return True
    if page == "Export":
        from .export import render_evidence_export_page

        render_evidence_export_page(database=runtime.archive_database)
        return True
    if page == "Mailbox":
        service = runtime.mailbox_service(create_archive=True)
        if service is None:  # pragma: no cover - create_archive always supplies the canonical archive.
            st.warning("SQLite database not available. Run ingestion first to enable mailbox state.")
            return True
        render_mailbox_page(service=service)
        return True
    return False


def _resolve_runtime_paths(vector_index_path: str | None, sqlite_path: str | None) -> tuple[str | None, str | None]:
    """Validate optional Streamlit runtime paths before opening application services."""
    resolved_vector_index_path = (
        str(validate_runtime_path(vector_index_path, field_name="vector index path")) if vector_index_path else None
    )
    resolved_sqlite_path = str(validate_runtime_path(sqlite_path, field_name="SQLite path")) if sqlite_path else None
    return resolved_vector_index_path, resolved_sqlite_path


def main() -> None:
    """Main entry point for the Streamlit web application."""
    st.set_page_config(
        page_title="Mailarium - Email Discovery",
        page_icon="✉️",
        layout="wide",
        initial_sidebar_state="auto",
    )
    inject_styles(theme=st.session_state.setdefault("web_theme", "night"))
    status_slot, vector_index_path, sqlite_path = render_header()
    try:
        resolved_vector_index_path, resolved_sqlite_path = _resolve_runtime_paths(vector_index_path, sqlite_path)
        runtime = get_runtime(resolved_vector_index_path, resolved_sqlite_path)
        bind_archive_session(runtime)
        render_archive_status(status_slot, runtime.archive_database)
    except (OSError, RuntimeError, ValueError) as exc:
        st.error(f"Runtime paths are invalid or unreadable: {exc}")
        return

    page = render_navigation()
    _render_page(page, runtime)
    render_footer(runtime.archive_database)


def _render_page(page: str, runtime: ApplicationRuntime) -> None:
    """Render one destination while keeping the shared shell and runtime intact."""
    if _render_non_search_page(page, runtime):
        return

    try:
        retriever = runtime.search_engine
    except (OSError, RuntimeError, ValueError) as exc:
        st.error(f"Runtime paths are invalid or unreadable: {exc}")
        return
    render_search_page(retriever=retriever, sort_options=SORT_OPTIONS, page_size=PAGE_SIZE, stage=page)
