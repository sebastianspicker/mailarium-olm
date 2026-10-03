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
from .workspace import _document_body_html, render_search_workspace

logger = logging.getLogger(__name__)


def render_search_page(*, retriever: Any, sort_options: dict[str, str], page_size: int, stage: str = "Search") -> None:
    """Render the search page implementation with filters and results display."""
    indexed = retriever.collection.count()
    if stage == "Search":
        with st.container(key="search-desk"):
            main_column, margin_column = st.columns([0.64, 0.36])
            with margin_column:
                st.markdown(_search_margin_html(indexed), unsafe_allow_html=True)
            with main_column:
                st.markdown(
                    "<div class='search-heading search-landing-heading'>"
                    "<h1 class='page-title'>What are you trying to establish?</h1>"
                    "<p class='page-note'>Ask in plain words, or paste a phrase you remember from the correspondence.</p>"
                    "</div>",
                    unsafe_allow_html=True,
                )
                if indexed == 0:
                    _render_empty_archive()
                    return
                _init_search_state()
                values = _render_search_form(sort_options)
                _handle_search_submission(retriever, sort_options, values)
        return

    st.markdown("<h1 class='page-title is-quiet'>Read the candidates</h1>", unsafe_allow_html=True)
    if indexed == 0:
        _render_empty_archive()
        return
    _init_search_state()
    values = _render_search_form(sort_options, compact=True)
    _handle_search_submission(retriever, sort_options, values)
    results = st.session_state.get("web_results", [])
    if not results:
        last_query = st.session_state.get("web_query", "")
        if last_query:
            st.warning(
                f'No candidates for "{last_query}" within these filters. Remove a filter, widen the dates, '
                "or turn on Hybrid search under More filters to match exact words."
            )
        else:
            st.info("Ask a question on the Search step. Candidate messages appear here beside their stored source.")
        return

    results, sort_value, filters, page, page_results, total_pages = _prepare_search_results(sort_options, page_size, results)
    _render_search_thread(retriever)
    _render_search_footer(retriever, page_size, results, sort_value, filters, page, page_results, total_pages)


def _init_search_state() -> None:
    """Seed the session keys every search stage reads."""
    st.session_state.setdefault("web_results", [])
    st.session_state.setdefault("web_query", "")
    st.session_state.setdefault("web_filters", {})
    st.session_state.setdefault("web_sort", "relevance")
    st.session_state.setdefault("web_page", 0)
    st.session_state.setdefault("web_thread_id", None)


def _search_margin_html(indexed: int) -> str:
    """Explain, in the margin, what a ranked search can and cannot establish."""
    scope = (
        f"<span class='num'>{indexed:,}</span> indexed {'message' if indexed == 1 else 'messages'}, held on this machine."
        if indexed
        else "Nothing is indexed yet."
    )
    return (
        "<aside class='search-margin' aria-label='How search works'><span class='register'>How this search reads</span><dl>"
        "<dt>Meaning first</dt><dd>Semantic search finds messages about your question even when the wording differs.</dd>"
        "<dt>Exact words</dt><dd>Turn on Hybrid search under More filters to add keyword matching.</dd>"
        "<dt>Candidates, not answers</dt><dd>Ranking decides what to read first. Only the stored text can support a finding.</dd>"
        f"<dt>Scope</dt><dd>{scope}</dd>"
        "</dl></aside>"
    )


def _render_empty_archive() -> None:
    """Name the missing prerequisite and the one command that resolves it."""
    st.markdown(
        "<div class='ledger-empty'><strong>This archive is empty.</strong>"
        "Import an Outlook <code>.olm</code> export first. Search opens as soon as messages are indexed.</div>",
        unsafe_allow_html=True,
    )
    st.code("mailarium-ingest path/to/archive.olm", language=None)
    st.caption("MCP clients can run the same import with the email_ingest tool.")


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
                top_k = st.number_input("Maximum results", min_value=1, max_value=50, value=defaults.get("top_k", 10))
            with ctrl_col2:
                sort_label = st.selectbox(
                    "Sort by",
                    list(sort_options.keys()),
                    index=list(sort_options).index(defaults.get("sort_label", next(iter(sort_options)))),
                )
            with ctrl_col3:
                min_score = st.slider(
                    "Minimum retrieval score",
                    min_value=0.0,
                    max_value=1.0,
                    value=defaults.get("min_score", 0.0),
                    step=0.05,
                    help="Hides lower-ranked candidates. A score orders reading; it is not a probability.",
                )
            with ctrl_col4:
                email_type_options = ["Any", "reply", "forward", "original"]
                email_type_label = st.selectbox(
                    "Message type", email_type_options, index=email_type_options.index(defaults.get("email_type_label", "Any"))
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

            priority = st.number_input("Minimum priority", min_value=0, max_value=5, value=defaults.get("priority", 0), step=1)
            has_attachments = st.checkbox("Has attachments", value=defaults.get("has_attachments", False))
            mode_col1, mode_col2, mode_col3 = st.columns(3)
            with mode_col1:
                use_hybrid = st.checkbox(
                    "Hybrid search",
                    value=defaults.get("use_hybrid", False),
                    help="Adds keyword matching to semantic search, so exact names and phrases rank higher.",
                )
            with mode_col2:
                use_rerank = st.checkbox(
                    "Re-rank results",
                    value=defaults.get("use_rerank", False),
                    help="Reorders the top candidates with the configured reranker. Slower, usually sharper.",
                )
            with mode_col3:
                use_expand = st.checkbox(
                    "Expand query",
                    value=defaults.get("use_expand", False),
                    help="Adds related terms to the question for broader coverage.",
                )
            scope = st.text_input(
                "Retrieval scope",
                value=defaults.get("scope", ""),
                placeholder="general, finance, customer support, ...",
                help="Optional relevance context. Hybrid channel weights adapt to each query automatically.",
            )

        if not compact:
            hint, action = st.columns([3, 1], vertical_alignment="center")
            with hint:
                st.caption("Scope is optional. Folder matches any part of the folder path.")
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
        st.warning("Enter a question or phrase to search.")
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
        st.error("The From date is after the To date. Swap them or clear one.")
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
        st.markdown("<h2 class='thread-heading'>Conversation thread</h2>", unsafe_allow_html=True)
        st.caption("Canonical conversation view. Inferred thread groups remain available through CLI and MCP workflows.")
        thread_results = retriever.search_by_thread(thread_id)
        if thread_results:
            st.markdown(_thread_summary_html(thread_results), unsafe_allow_html=True)

            for idx, tr in enumerate(thread_results, 1):
                st.markdown(_thread_email_html(idx, tr), unsafe_allow_html=True)
        else:
            st.info("No stored messages carry this thread identifier.")
        if st.button("Close thread view", type="secondary"):
            del st.session_state["web_thread_id"]
            st.rerun()
        st.divider()


def _thread_summary_html(results: list[Any]) -> str:
    """Build escaped thread counts, date range, and a bounded participant summary."""
    participants = list(dict.fromkeys(_thread_sender(result) for result in results))
    dates = [str(result.metadata.get("date", ""))[:10] for result in results if result.metadata.get("date")]
    date_range = f" &middot; <span class='num'>{min(dates)}</span> to <span class='num'>{max(dates)}</span>" if dates else ""
    overflow = f" (+{len(participants) - 5})" if len(participants) > 5 else ""
    return (
        "<div class='thread-summary'>"
        f"<span class='num'>{len(results)}</span> messages &middot; <span class='num'>{len(participants)}</span> participants"
        f"{date_range}<br/><span>Participants: "
        f"{html_escape(', '.join(participants[:5]))}{overflow}</span></div>"
    )


def _thread_sender(result: Any) -> str:
    """Prefer sender display name and fall back to email or an unknown marker."""
    return str(result.metadata.get("sender_name") or result.metadata.get("sender_email", "?"))


def _thread_email_html(index: int, result: Any) -> str:
    """Render one escaped thread message with its type and bounded body text."""
    metadata = result.metadata
    email_type = metadata.get("email_type", "original")
    kind = {"reply": "Reply", "forward": "Forward"}.get(email_type, "")
    kind_html = f"<span class='register'>{kind}</span>" if kind else ""
    body = result.text[:800] if len(result.text) > 800 else result.text
    truncated = "<span class='register'>Excerpt · first 800 characters</span>" if len(result.text) > 800 else ""
    return (
        f"<div class='thread-email{' is-reply' if kind else ''}'><div class='thread-email-header'>"
        f"<span class='register'>{index:02d}</span><strong>{html_escape(_thread_sender(result))}</strong>{kind_html}"
        f"<span class='num'>{html_escape(str(metadata.get('date', '?'))[:10])}</span>"
        f"<span class='thread-email-subject'>{html_escape(str(metadata.get('subject', '?')))}</span>"
        f"</div><div class='thread-email-body'>{_document_body_html(body)}</div>{truncated}</div>"
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
