"""Task navigation and archive utilities shared by every Streamlit screen."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING, Any

import streamlit as st

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase

STEPS = ("Search", "Inspect", "Evidence", "Export")


def _navigate() -> None:
    st.session_state["web_route"] = st.session_state["web_navigation"]


def render_header() -> tuple[Any, str | None, str | None]:
    """Render the masthead and explicit runtime settings before opening resources."""
    with st.container(key="shell-header"):
        brand, status, utilities = st.columns([5, 3, 1.5], vertical_alignment="center")
        with brand:
            st.markdown(
                "<div class='brand'><span class='memory-mark' aria-hidden='true'></span>"
                "<span class='brand-name'>Mailarium</span><span class='brand-context'>Local archive</span></div>",
                unsafe_allow_html=True,
            )
        with status:
            status_slot = st.empty()
        with utilities, st.popover("Sources & tools", use_container_width=True):
            st.caption("Trusted local archive. Remote mailbox access remains separately gated.")
            for page in ("Overview", "People", "Connections", "Mailbox"):
                if st.button(page, key=f"web-tool-{page}", use_container_width=True):
                    st.session_state["web_route"] = page
                    st.rerun()
            st.divider()
            st.markdown("**Runtime paths**")
            vector_path = st.text_input("Vector Index Path", key="web_vector_path", placeholder="Configured default")
            sqlite_path = st.text_input("SQLite Path", key="web_sqlite_path", placeholder="Configured default")
            st.caption("Overrides must stay inside configured runtime roots. Leave blank to use configured defaults.")
            current = st.session_state.get("web_theme", "night")
            label = "Use light theme" if current == "night" else "Use dark theme"
            if st.button(label, key="web-theme-toggle", use_container_width=True):
                st.session_state["web_theme"] = "day" if current == "night" else "night"
                st.rerun()
    return status_slot, vector_path or None, sqlite_path or None


def render_archive_status(status_slot: Any, database: ArchiveDatabase | None) -> None:
    """Report real archive counts without implying that retrieval or EWS is ready."""
    count = database.queries.email_count() if database is not None else 0
    label = f"{count:,} messages in archive" if count else "No messages in archive"
    status_slot.markdown(f"<div class='archive-status'>{escape(label)}</div>", unsafe_allow_html=True)


def render_navigation() -> str:
    """Keep native keyboard-operable task navigation in sync with workflow handoffs."""
    route = st.session_state.setdefault("web_route", "Search")
    st.session_state["web_navigation"] = route if route in STEPS else None
    with st.container(key="shell-navigation"):
        st.radio(
            "Investigation step",
            STEPS,
            key="web_navigation",
            horizontal=True,
            label_visibility="collapsed",
            on_change=_navigate,
        )
    return route


def bind_archive_session(runtime: Any) -> None:
    """Discard archive-specific session content when the user switches path pairs."""
    pair = (str(runtime.vector_index_path), str(runtime.sqlite_path))
    previous = st.session_state.get("web_archive_pair")
    if previous is not None and previous != pair:
        keep = {"web_theme", "web_vector_path", "web_sqlite_path"}
        for key in list(st.session_state):
            if not isinstance(key, str):
                continue
            if (key.startswith("web_") and key not in keep) or key.startswith(
                (
                    "workspace-",
                    "capture-",
                    "export-",
                    "evidence-export-",
                    "quote-",
                    "category-",
                    "summary-",
                    "relevance-",
                    "notes-",
                )
            ):
                del st.session_state[key]
        st.session_state["web_route"] = "Search"
    st.session_state["web_archive_pair"] = pair


def render_footer(database: ArchiveDatabase | None) -> None:
    """Show the saved evidence count and scope of this trusted-local surface."""
    count = database.evidence.evidence_stats()["total"] if database is not None else 0
    with st.container(key="shell-footer"):
        st.markdown(
            f"<div class='shell-footer'><span>Evidence · {count:,} saved</span>"
            "<small>Local archive · Check sources before drawing conclusions</small></div>",
            unsafe_allow_html=True,
        )
