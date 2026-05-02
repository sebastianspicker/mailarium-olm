"""Local Streamlit UI for browsing and searching indexed emails."""

from __future__ import annotations

from typing import Any

import streamlit as st

try:
    from .formatting import format_date
    from .repo_paths import validate_runtime_path
    from .retriever import EmailRetriever
    from .validation import validate_date_window
    from .web_app_pages import (
        get_email_db_safe_impl,
        render_dashboard_page_impl,
        render_entity_page_impl,
        render_evidence_page_impl,
        render_network_page_impl,
    )
    from .web_app_rendering import (
        _type_badge_html,
        inject_styles_impl,
        render_results_impl,
        render_results_summary_impl,
        render_sidebar_impl,
    )
    from .web_app_search import (
        _as_optional_float,
        _as_optional_str,
        _build_csv_export,
        render_search_page_impl,
    )
    from .web_ui import build_active_filter_labels, build_export_payload, build_filter_chip_html, sort_search_results
except ImportError:  # pragma: no cover
    from src.formatting import format_date
    from src.repo_paths import validate_runtime_path
    from src.retriever import EmailRetriever
    from src.validation import validate_date_window
    from src.web_app_pages import (
        get_email_db_safe_impl,
        render_dashboard_page_impl,
        render_entity_page_impl,
        render_evidence_page_impl,
        render_network_page_impl,
    )
    from src.web_app_rendering import (
        _type_badge_html,
        inject_styles_impl,
        render_results_impl,
        render_results_summary_impl,
        render_sidebar_impl,
    )
    from src.web_app_search import (
        _as_optional_float,
        _as_optional_str,
        _build_csv_export,
        render_search_page_impl,
    )
    from src.web_ui import build_active_filter_labels, build_export_payload, build_filter_chip_html, sort_search_results

st.set_page_config(
    page_title="Email RAG - Email Discovery",
    page_icon="\U0001f50d",
    layout="wide",
    initial_sidebar_state="expanded",
)

SORT_OPTIONS = {
    "Relevance": "relevance",
    "Newest first": "date_desc",
    "Oldest first": "date_asc",
    "Sender A-Z": "sender_asc",
}

PAGE_SIZE = 20


@st.cache_resource
def get_retriever(chromadb_path: str | None, sqlite_path: str | None = None, _cache_version: int = 0):
    if sqlite_path is None:
        return EmailRetriever(chromadb_path=chromadb_path)
    return EmailRetriever(chromadb_path=chromadb_path, sqlite_path=sqlite_path)


def invalidate_retriever_cache() -> None:
    """Invalidate the cached retriever so the next access creates a fresh one."""
    get_retriever.clear()


def render_sidebar(retriever: EmailRetriever) -> None:
    render_sidebar_impl(st_module=st, retriever=retriever)


def render_results(results: list[Any], preview_chars: int, retriever: EmailRetriever | None = None) -> None:
    render_results_impl(
        st_module=st,
        results=results,
        preview_chars=preview_chars,
        retriever=retriever,
        format_date_fn=format_date,
    )


def inject_styles() -> None:
    inject_styles_impl(st_module=st)


def render_results_summary(
    results: list[Any],
    active_filters: list[str],
    sort_label: str,
    search_modes: list[str] | None = None,
) -> None:
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
    render_dashboard_page_impl(st_module=st, get_email_db_safe_fn=lambda: _get_email_db_safe(sqlite_path))


def render_entity_page(sqlite_path: str | None = None) -> None:
    render_entity_page_impl(st_module=st, get_email_db_safe_fn=lambda: _get_email_db_safe(sqlite_path))


def render_network_page(sqlite_path: str | None = None) -> None:
    render_network_page_impl(st_module=st, get_email_db_safe_fn=lambda: _get_email_db_safe(sqlite_path))


def render_evidence_page(sqlite_path: str | None = None) -> None:
    render_evidence_page_impl(
        st_module=st,
        get_email_db_safe_fn=lambda: _get_email_db_safe(sqlite_path),
        type_badge_html_fn=_type_badge_html,
    )


def render_search_page(retriever: EmailRetriever) -> None:
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


def main() -> None:
    inject_styles()
    st.markdown("<h1 class='hero-title'>Email RAG</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p class='hero-subtitle'>Exploratory archive search and lightweight evidence collection"
        " for your Outlook email archive.</p>",
        unsafe_allow_html=True,
    )
    st.info(
        "This Streamlit app is an exploratory archive UI. For prompt-grade legal-support workflows such as "
        "full-pack review, counsel packs, chronology building, or issue matrices, use the CLI or MCP surfaces."
    )

    page = st.sidebar.radio(
        "Navigate",
        ["Search", "Dashboard", "Entities", "Network", "Evidence"],
        index=0,
        captions=[
            "Semantic & filtered search",
            "Volume & activity",
            "People & orgs",
            "Communication graph",
            "Collected evidence",
        ],
    )

    chromadb_path = st.sidebar.text_input("ChromaDB Path", value="") or None
    sqlite_path = st.sidebar.text_input("SQLite Path", value="") or None
    try:
        resolved_chromadb_path = str(validate_runtime_path(chromadb_path, field_name="ChromaDB path")) if chromadb_path else None
        resolved_sqlite_path = str(validate_runtime_path(sqlite_path, field_name="SQLite path")) if sqlite_path else None
    except ValueError as exc:
        st.error(f"Runtime paths are invalid: {exc}")
        return

    if page == "Dashboard":
        render_dashboard_page(resolved_sqlite_path)
        return
    if page == "Entities":
        render_entity_page(resolved_sqlite_path)
        return
    if page == "Network":
        render_network_page(resolved_sqlite_path)
        return
    if page == "Evidence":
        render_evidence_page(resolved_sqlite_path)
        return

    try:
        retriever = get_retriever(resolved_chromadb_path, resolved_sqlite_path)
    except (OSError, RuntimeError, ValueError) as exc:
        st.error(f"Runtime paths are invalid or unreadable: {exc}")
        return
    render_sidebar(retriever)
    render_search_page(retriever)


if __name__ == "__main__":
    main()
