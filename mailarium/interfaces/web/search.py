"""Search-page controller helpers for the Streamlit app."""

from __future__ import annotations

import logging
import math
from html import escape as html_escape
from typing import Any, cast

import streamlit as st

from mailarium.platform.validation import validate_date_window

from .presentation import build_active_filter_labels, sort_search_results
from .results import render_results_summary
from .workspace import render_search_workspace

logger = logging.getLogger(__name__)


def render_search_page(*, retriever: Any, sort_options: dict[str, str], page_size: int, stage: str = "Search") -> None:
    """Render the search page implementation with filters and results display."""
    if stage == "Search":
        st.markdown(
            "<div class='search-heading search-landing-heading'><span class='workspace-label'>"
            "Search your local archive</span><h1 class='page-title'>What are you trying to establish?</h1>"
            "<p class='page-note'>Start with a question or a phrase from the correspondence.</p></div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown("<h1 class='page-title'>Find the reason behind a decision</h1>", unsafe_allow_html=True)
    if retriever.collection.count() == 0:
        st.warning("No emails indexed yet.")
        st.info(
            "To index your Outlook archive, run the ingestion script:\n\n"
            "```\npython -m mailarium.ingest path/to/export.olm\n```\n\n"
            "Or use the **`email_ingest`** MCP tool directly from your MCP client."
        )
        return

    st.session_state.setdefault("web_results", [])
    st.session_state.setdefault("web_query", "")
    st.session_state.setdefault("web_filters", {})
    st.session_state.setdefault("web_sort", "relevance")
    st.session_state.setdefault("web_page", 0)
    st.session_state.setdefault("web_thread_id", None)

    values = _render_search_form(sort_options, compact=stage == "Inspect")
    _handle_search_submission(retriever, sort_options, values)
    if stage == "Search":
        return
    results = st.session_state.get("web_results", [])
    if not results:
        last_query = st.session_state.get("web_query", "")
        if last_query:
            st.warning(
                f'No results found for "{last_query}". '
                "Try broadening your search terms, removing filters, "
                "or enabling hybrid search mode for better keyword coverage."
            )
        else:
            st.info("Enter a search query above and click Search to browse indexed emails with advanced filters.")
        return

    results, sort_value, filters, page, page_results, total_pages = _prepare_search_results(sort_options, page_size, results)
    _render_search_thread(retriever)
    _render_search_footer(retriever, page_size, results, sort_value, filters, page, page_results, total_pages)


def _render_search_form(sort_options: dict[str, str], *, compact: bool = False) -> dict[str, Any]:
    """Render search controls and return every submitted query, filter, and mode value."""
    defaults = st.session_state.get("web_search_form_values", {})
    with st.form("search_form", clear_on_submit=False):
        st.markdown(
            f"<span class='{'search-compact-marker' if compact else 'search-landing-marker'}' aria-hidden='true'></span>",
            unsafe_allow_html=True,
        )
        query_columns = st.columns([6, 1.2]) if compact else [st.container()]
        with query_columns[0]:
            query = st.text_input(
                "Question or phrase",
                value=defaults.get("query", st.session_state.get("web_query", "")),
                placeholder="Search the correspondence…",
                label_visibility="collapsed" if compact else "visible",
            )
        if compact:
            with query_columns[1]:
                search_clicked = st.form_submit_button("Search", type="primary", use_container_width=True)
        if not compact:
            folder, date_from_val, date_to_val = _render_scope_fields(defaults)

        with st.expander("More filters", expanded=False):
            if compact:
                folder, date_from_val, date_to_val = _render_scope_fields(defaults)
            ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns([2, 2, 2, 2])
            with ctrl_col1:
                top_k = st.number_input("Max Results", min_value=1, max_value=50, value=defaults.get("top_k", 10))
            with ctrl_col2:
                sort_label = st.selectbox(
                    "Sort By",
                    list(sort_options.keys()),
                    index=list(sort_options).index(defaults.get("sort_label", next(iter(sort_options)))),
                )
            with ctrl_col3:
                min_score = st.slider(
                    "Min Relevance", min_value=0.0, max_value=1.0, value=defaults.get("min_score", 0.0), step=0.05
                )
            with ctrl_col4:
                email_type_options = ["Any", "reply", "forward", "original"]
                email_type_label = st.selectbox(
                    "Email Type", email_type_options, index=email_type_options.index(defaults.get("email_type_label", "Any"))
                )

            filt_col1, filt_col2, filt_col3 = st.columns(3)
            with filt_col1:
                sender = st.text_input("Sender", value=defaults.get("sender", ""), placeholder="name or email")
                to_filter = st.text_input("To", value=defaults.get("to_filter", ""), placeholder="recipient")
            with filt_col2:
                subject = st.text_input("Subject", value=defaults.get("subject", ""), placeholder="keyword in subject")
            with filt_col3:
                cc = st.text_input("CC", value=defaults.get("cc", ""), placeholder="cc recipient")
                bcc = st.text_input("BCC", value=defaults.get("bcc", ""), placeholder="bcc recipient")

            priority = st.number_input("Min Priority", min_value=0, max_value=5, value=defaults.get("priority", 0), step=1)
            has_attachments = st.checkbox("Has attachments", value=defaults.get("has_attachments", False))
            mode_col1, mode_col2, mode_col3 = st.columns(3)
            with mode_col1:
                use_hybrid = st.checkbox(
                    "Hybrid search",
                    value=defaults.get("use_hybrid", False),
                    help="Combines semantic vectors with BM25 keyword matching for better recall.",
                )
            with mode_col2:
                use_rerank = st.checkbox(
                    "Re-rank results",
                    value=defaults.get("use_rerank", False),
                    help="Re-ranks using the configured maintained reranker. Slower but more precise.",
                )
            with mode_col3:
                use_expand = st.checkbox(
                    "Expand query",
                    value=defaults.get("use_expand", False),
                    help="Adds semantically related terms for broader coverage.",
                )
            scope = st.text_input(
                "Retrieval Scope",
                value=defaults.get("scope", ""),
                placeholder="general, finance, customer support, ...",
                help="Optional relevance context. Hybrid channel weights adapt to each query automatically.",
            )

        if not compact:
            hint, action = st.columns([3, 1], vertical_alignment="center")
            with hint:
                st.caption("Search messages matching these filters.")
            with action:
                search_clicked = st.form_submit_button("Search archive", type="primary", use_container_width=True)

    values = {
        "query": query,
        "top_k": top_k,
        "sort_label": sort_label,
        "min_score": min_score,
        "email_type_label": email_type_label,
        "sender": sender,
        "to_filter": to_filter,
        "subject": subject,
        "folder": folder,
        "cc": cc,
        "bcc": bcc,
        "date_from_val": date_from_val,
        "date_to_val": date_to_val,
        "priority": priority,
        "has_attachments": has_attachments,
        "use_hybrid": use_hybrid,
        "use_rerank": use_rerank,
        "use_expand": use_expand,
        "scope": scope,
        "search_clicked": search_clicked,
    }
    st.session_state["web_search_form_values"] = {key: value for key, value in values.items() if key != "search_clicked"}
    return values


def _render_scope_fields(defaults: dict[str, Any]) -> tuple[Any, Any, Any]:
    """Keep the principal folder/date scope together in both search states."""
    folder_column, from_column, to_column = st.columns(3)
    with folder_column:
        folder = st.text_input("Folder contains", value=defaults.get("folder", ""), placeholder="Any folder")
    with from_column:
        date_from = st.date_input("From date", value=defaults.get("date_from_val"))
    with to_column:
        date_to = st.date_input("To date", value=defaults.get("date_to_val"))
    return folder, date_from, date_to


def _handle_search_submission(retriever: Any, sort_options: dict[str, str], values: dict[str, Any]) -> None:
    """Validate a submitted query and dates, execute filtered search, and reset pagination state."""
    if not values["search_clicked"]:
        return
    query = values["query"]
    if not query.strip():
        st.warning("Please enter a query.")
        return
    dates = _validated_search_dates(values)
    if dates is None:
        return
    filters = _build_search_filters(values, *dates)
    try:
        with st.spinner("Searching the archive…"):
            results = retriever.search_filtered(query=query, top_k=int(values["top_k"]), **filters)
    except Exception as exc:
        logger.exception("Search request failed")
        st.session_state["web_search_error"] = type(exc).__name__
        st.error("Search could not be completed. Check the configured model and runtime paths under Sources & tools.")
        return
    sort_value = sort_options[values["sort_label"]]
    st.session_state["web_results"] = sort_search_results(results, sort_value)
    st.session_state["web_query"] = query
    st.session_state["web_filters"] = filters
    st.session_state["web_sort"] = sort_value
    st.session_state["web_page"] = 0
    st.session_state.pop("web_search_error", None)
    st.session_state["web_thread_id"] = None
    st.session_state["web_route"] = "Inspect"
    st.rerun()


def _validated_search_dates(values) -> tuple[str | None, str | None] | None:
    """Normalize date inputs and surface an ordered-window validation error in the UI."""
    date_from = str(values["date_from_val"]) if values["date_from_val"] else None
    date_to = str(values["date_to_val"]) if values["date_to_val"] else None
    try:
        validate_date_window(date_from, date_to)
    except ValueError:
        st.error("Date From cannot be later than Date To.")
        return None
    return date_from, date_to


def _build_search_filters(values, date_from: str | None, date_to: str | None) -> dict[str, Any]:
    """Convert form values into optional retriever filters and search-mode flags."""
    return {
        **_text_search_filters(values),
        "has_attachments": True if values["has_attachments"] else None,
        "priority": _optional_priority(values["priority"]),
        "email_type": _optional_email_type(values["email_type_label"]),
        "date_from": date_from,
        "date_to": date_to,
        "min_score": _optional_minimum_score(values["min_score"]),
        "hybrid": values["use_hybrid"],
        "rerank": values["use_rerank"],
        "expand_query": values["use_expand"],
        "scope": values["scope"] or None,
    }


def _text_search_filters(values: dict[str, Any]) -> dict[str, str | None]:
    """Normalize optional text metadata filters from submitted form values."""
    fields = {
        "sender": "sender",
        "to": "to_filter",
        "subject": "subject",
        "folder": "folder",
        "cc": "cc",
        "bcc": "bcc",
    }
    return {filter_name: values[value_name] or None for filter_name, value_name in fields.items()}


def _optional_priority(priority: Any) -> int | None:
    """Return a positive priority filter, otherwise omit it."""
    return int(priority) if priority and priority > 0 else None


def _optional_email_type(email_type: Any) -> Any:
    """Omit the UI's unrestricted email-type sentinel."""
    return email_type if email_type != "Any" else None


def _optional_minimum_score(minimum: Any) -> float | None:
    """Return a rounded positive relevance threshold, otherwise omit it."""
    return round(float(minimum), 2) if minimum > 0.0 else None


def _prepare_search_results(sort_options: dict[str, str], page_size: int, results: list[Any]) -> tuple[Any, ...]:
    """Render summary state and clamp pagination before slicing the current result page."""
    sort_value = st.session_state.get("web_sort", "relevance")
    sort_label = next((label for label, value in sort_options.items() if value == sort_value), "Relevance")
    filters = cast(dict[str, Any], st.session_state.get("web_filters", {}))
    sender_filter = _as_optional_str(filters.get("sender"))
    to_filter_val = _as_optional_str(filters.get("to"))
    subject_filter = _as_optional_str(filters.get("subject"))
    folder_filter = _as_optional_str(filters.get("folder"))
    cc_filter = _as_optional_str(filters.get("cc"))
    bcc_filter = _as_optional_str(filters.get("bcc"))
    has_att_filter = filters.get("has_attachments")
    priority_filter = filters.get("priority")
    email_type_filter = _as_optional_str(filters.get("email_type"))
    date_from_filter = _as_optional_str(filters.get("date_from"))
    date_to_filter = _as_optional_str(filters.get("date_to"))
    min_score_filter = _as_optional_float(filters.get("min_score"))
    active_filter_labels = build_active_filter_labels(
        {
            "sender": sender_filter,
            "to": to_filter_val,
            "subject": subject_filter,
            "folder": folder_filter,
            "cc": cc_filter,
            "bcc": bcc_filter,
            "has_attachments": has_att_filter if isinstance(has_att_filter, bool) else None,
            "priority": int(priority_filter) if isinstance(priority_filter, int | float) else None,
            "email_type": email_type_filter,
            "date_from": date_from_filter,
            "date_to": date_to_filter,
            "min_score": min_score_filter,
        }
    )

    search_modes: list[str] = []
    if filters.get("hybrid"):
        search_modes.append("hybrid")
    elif not filters.get("hybrid"):
        search_modes.append("semantic")
    if filters.get("rerank"):
        search_modes.append("reranked")
    if filters.get("expand_query"):
        search_modes.append("expanded")
    if filters.get("scope"):
        search_modes.append(f"scope:{filters['scope']}")

    render_results_summary(results=results, active_filters=active_filter_labels, sort_label=sort_label, search_modes=search_modes)

    total_pages = max(1, (len(results) + page_size - 1) // page_size)
    page = max(0, min(int(st.session_state.get("web_page", 0)), total_pages - 1))
    page_results = results[page * page_size : (page + 1) * page_size]

    return results, sort_value, filters, page, page_results, total_pages


def _render_search_thread(retriever: Any) -> None:
    """Render and close the canonical conversation selected in session state."""
    thread_id = st.session_state.get("web_thread_id")
    if thread_id:
        st.markdown("### Conversation Thread")
        st.caption("Canonical conversation view. Inferred thread groups remain available through CLI/MCP workflows.")
        thread_results = retriever.search_by_thread(thread_id)
        if thread_results:
            st.markdown(_thread_summary_html(thread_results), unsafe_allow_html=True)

            for idx, tr in enumerate(thread_results, 1):
                st.markdown(_thread_email_html(idx, tr), unsafe_allow_html=True)
        else:
            st.info("No emails found for this thread.")
        if st.button("Close Thread View", type="secondary"):
            del st.session_state["web_thread_id"]
            st.rerun()
        st.divider()


def _thread_summary_html(results: list[Any]) -> str:
    """Build escaped thread counts, date range, and a bounded participant summary."""
    participants = list(dict.fromkeys(_thread_sender(result) for result in results))
    dates = [str(result.metadata.get("date", ""))[:10] for result in results if result.metadata.get("date")]
    date_range = f" &middot; {min(dates)} to {max(dates)}" if dates else ""
    overflow = f" (+{len(participants) - 5})" if len(participants) > 5 else ""
    return (
        "<div class='thread-summary'>"
        f"<strong>{len(results)} messages</strong> &middot; <strong>{len(participants)} participants</strong>"
        f"{date_range}<br/><span>Participants: "
        f"{html_escape(', '.join(participants[:5]))}{overflow}</span></div>"
    )


def _thread_sender(result: Any) -> str:
    """Prefer sender display name and fall back to email or an unknown marker."""
    return str(result.metadata.get("sender_name") or result.metadata.get("sender_email", "?"))


def _thread_email_html(index: int, result: Any) -> str:
    """Render one escaped thread message with type badge and bounded body text."""
    metadata = result.metadata
    email_type = metadata.get("email_type", "original")
    indicators = {"reply": ("#d8b4fe", "REPLY"), "forward": ("#f9a8d4", "FWD")}
    indicator = indicators.get(email_type)
    badge = (
        f"<span style='color:{indicator[0]};font-size:0.72rem;font-weight:600;margin-left:0.4rem;'>{indicator[1]}</span>"
        if indicator
        else ""
    )
    body = result.text[:800] if len(result.text) > 800 else result.text
    border = "#64d8d6" if index % 2 == 1 else "#d8b4fe"
    return (
        f"<div class='thread-email' style='border-left-color:{border};'><div class='thread-email-header'>"
        f"<strong>{index}. {html_escape(_thread_sender(result))}</strong>{badge} &middot; "
        f"{html_escape(str(metadata.get('date', '?'))[:10])}<br/>"
        f"<span style='color:#9aa9b6;font-size:0.78rem;'>{html_escape(str(metadata.get('subject', '?')))}</span>"
        f"</div><div class='thread-email-body'>{html_escape(body)}</div></div>"
    )


def _render_search_footer(
    retriever: Any,
    page_size: int,
    results: list[Any],
    sort_value: str,
    filters: dict[str, Any],
    page: int,
    page_results: list[Any],
    total_pages: int,
) -> None:
    """Render the search workspace with pagination and export controls."""
    render_search_workspace(
        retriever=retriever,
        results=results,
        page_results=page_results,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        filters=filters,
        sort_value=sort_value,
    )


def _as_optional_str(value: Any) -> str | None:
    """Return string values unchanged and reject other filter types."""
    if isinstance(value, str):
        return value
    return None


def _as_optional_float(value: Any) -> float | None:
    """Return finite numeric values as floats and reject NaN or infinity."""
    if isinstance(value, int | float):
        float_value = float(value)
        if math.isnan(float_value) or math.isinf(float_value):
            return None
        return float_value
    return None
