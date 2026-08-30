"""Search-page controller helpers for the Streamlit app."""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass
from html import escape as html_escape
from typing import Any, cast

from .web_app_workspace import render_search_workspace_impl

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _SearchPageDeps:
    """Group search-page configuration and render hooks for the UI boundary."""

    sort_options: dict[str, str]
    page_size: int
    render_results_summary_fn: Any
    build_csv_export_fn: Any
    build_active_filter_labels_fn: Any
    build_export_payload_fn: Any
    sort_search_results_fn: Any
    validate_date_window_fn: Any
    as_optional_str_fn: Any
    as_optional_float_fn: Any

    @classmethod
    def bind(cls, options: dict[str, Any]) -> _SearchPageDeps:
        """Validate dependency names exactly before constructing the search-page dependency bundle."""
        expected = set(cls.__dataclass_fields__)
        unknown = sorted(set(options) - expected)
        missing = sorted(expected - set(options))
        if unknown:
            raise TypeError(f"render_search_page_impl() got unexpected option(s): {', '.join(unknown)}")
        if missing:
            raise TypeError(f"render_search_page_impl() missing required option(s): {', '.join(missing)}")
        return cls(**options)


def render_search_page_impl(*, st_module: Any, retriever: Any, **options: Any) -> None:
    """Render the search page implementation with filters and results display."""
    st_module.markdown(
        "<div class='search-heading'><h1 class='page-title'>Search the archive</h1></div>",
        unsafe_allow_html=True,
    )
    if retriever.collection.count() == 0:
        st_module.warning("No emails indexed yet.")
        st_module.info(
            "To index your Outlook archive, run the ingestion script:\n\n"
            "```\npython -m mailarium.ingest path/to/export.olm\n```\n\n"
            "Or use the **`email_ingest`** MCP tool directly from your MCP client."
        )
        return

    st_module.session_state.setdefault("web_results", [])
    st_module.session_state.setdefault("web_query", "")
    st_module.session_state.setdefault("web_filters", {})
    st_module.session_state.setdefault("web_sort", "relevance")
    st_module.session_state.setdefault("web_page", 0)
    st_module.session_state.setdefault("web_thread_id", None)

    deps = _SearchPageDeps.bind(options)
    values = _render_search_form(st_module, deps.sort_options)
    _handle_search_submission(st_module, retriever, deps, values)
    results = st_module.session_state.get("web_results", [])
    if not results:
        last_query = st_module.session_state.get("web_query", "")
        if last_query:
            st_module.warning(
                f'No results found for "{last_query}". '
                "Try broadening your search terms, removing filters, "
                "or enabling hybrid search mode for better keyword coverage."
            )
        else:
            st_module.info("Enter a search query above and click Search to browse indexed emails with advanced filters.")
        return

    results, sort_value, filters, page, page_results, total_pages = _prepare_search_results(st_module, deps, results)
    _render_search_thread(st_module, retriever)
    _render_search_footer(st_module, retriever, deps, results, sort_value, filters, page, page_results, total_pages)


def _render_search_form(st_module: Any, sort_options: dict[str, str]) -> dict[str, Any]:
    """Render search controls and return every submitted query, filter, and mode value."""
    with st_module.form("search_form", clear_on_submit=False):
        query_col, submit_col = st_module.columns([6, 1.2])
        with query_col:
            query = st_module.text_input(
                "Search Query",
                value=st_module.session_state.get("web_query", ""),
                placeholder="What changed in the Northstar handoff?",
                help="Natural language query. The system uses semantic search to find relevant emails.",
                label_visibility="collapsed",
            )
        with submit_col:
            search_clicked = st_module.form_submit_button("Search", type="primary", use_container_width=True)

        with st_module.expander("Search Mode and filters", expanded=False):
            ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st_module.columns([2, 2, 2, 2])
            with ctrl_col1:
                top_k = st_module.number_input("Max Results", min_value=1, max_value=50, value=10)
            with ctrl_col2:
                sort_label = st_module.selectbox("Sort By", list(sort_options.keys()), index=0)
            with ctrl_col3:
                min_score = st_module.slider("Min Relevance", min_value=0.0, max_value=1.0, value=0.0, step=0.05)
            with ctrl_col4:
                email_type_options = ["Any", "reply", "forward", "original"]
                email_type_label = st_module.selectbox("Email Type", email_type_options, index=0)

            filt_col1, filt_col2, filt_col3 = st_module.columns(3)
            with filt_col1:
                sender = st_module.text_input("Sender", placeholder="name or email")
                to_filter = st_module.text_input("To", placeholder="recipient")
            with filt_col2:
                subject = st_module.text_input("Subject", placeholder="keyword in subject")
                folder = st_module.text_input("Folder", placeholder="Inbox, Sent, etc.")
            with filt_col3:
                cc = st_module.text_input("CC", placeholder="cc recipient")
                bcc = st_module.text_input("BCC", placeholder="bcc recipient")

            extra_col1, extra_col2, extra_col3 = st_module.columns(3)
            with extra_col1:
                date_from_val = st_module.date_input("Date From", value=None)
            with extra_col2:
                date_to_val = st_module.date_input("Date To", value=None)
            with extra_col3:
                priority = st_module.number_input("Min Priority", min_value=0, max_value=5, value=0, step=1)
                has_attachments = st_module.checkbox("Has attachments")
            mode_col1, mode_col2, mode_col3 = st_module.columns(3)
            with mode_col1:
                use_hybrid = st_module.checkbox(
                    "Hybrid search",
                    help="Combines semantic vectors with BM25 keyword matching for better recall.",
                )
            with mode_col2:
                use_rerank = st_module.checkbox(
                    "Re-rank results",
                    help="Re-ranks using the configured maintained reranker. Slower but more precise.",
                )
            with mode_col3:
                use_expand = st_module.checkbox(
                    "Expand query",
                    help="Adds semantically related terms for broader coverage.",
                )
            scope = st_module.text_input(
                "Retrieval Scope",
                placeholder="general, finance, customer support, ...",
                help="Optional relevance context. Hybrid channel weights adapt to each query automatically.",
            )

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
    _render_active_filter_chips(st_module, values)
    return values


def _render_active_filter_chips(st_module: Any, values: dict[str, Any]) -> None:
    """Surface selected modes and filters as chips next to the filters control (mockup)."""
    chips: list[tuple[str, bool]] = []
    if values.get("use_hybrid"):
        chips.append(("Hybrid", True))
    if values.get("use_rerank"):
        chips.append(("Reranked", True))
    if values.get("use_expand"):
        chips.append(("Expanded", True))
    scope = str(values.get("scope") or "").strip()
    if scope:
        chips.append((f"Scope: {scope}", True))
    folder = str(values.get("folder") or "").strip()
    if folder:
        chips.append((f"Folder: {folder}", False))
    date_from = values.get("date_from_val")
    if date_from:
        chips.append((f"After {date_from}", False))
    date_to = values.get("date_to_val")
    if date_to:
        chips.append((f"Before {date_to}", False))
    if values.get("has_attachments"):
        chips.append(("Has attachments", False))
    if not chips:
        return
    chip_html = "".join(f"<span class='{'is-active' if active else ''}'>{html_escape(label)}</span>" for label, active in chips)
    st_module.markdown(f"<div class='search-control-chips'>{chip_html}</div>", unsafe_allow_html=True)


def _handle_search_submission(st_module: Any, retriever: Any, deps: Any, values: dict[str, Any]) -> None:
    """Validate a submitted query and dates, execute filtered search, and reset pagination state."""
    if not values["search_clicked"]:
        return
    query = values["query"]
    if not query.strip():
        st_module.warning("Please enter a query.")
        return
    dates = _validated_search_dates(st_module, deps.validate_date_window_fn, values)
    if dates is None:
        return
    filters = _build_search_filters(values, *dates)
    try:
        results = retriever.search_filtered(query=query, top_k=int(values["top_k"]), **filters)
    except Exception as exc:
        logger.exception("Search request failed")
        st_module.session_state["web_search_error"] = type(exc).__name__
        st_module.error("Search could not be completed. Check Admin diagnostics and the configured model/runtime paths.")
        return
    sort_value = deps.sort_options[values["sort_label"]]
    st_module.session_state["web_results"] = deps.sort_search_results_fn(results, sort_value)
    st_module.session_state["web_query"] = query
    st_module.session_state["web_filters"] = filters
    st_module.session_state["web_sort"] = sort_value
    st_module.session_state["web_page"] = 0
    st_module.session_state.pop("web_search_error", None)


def _validated_search_dates(st, validator, values) -> tuple[str | None, str | None] | None:
    """Normalize date inputs and surface an ordered-window validation error in the UI."""
    date_from = str(values["date_from_val"]) if values["date_from_val"] else None
    date_to = str(values["date_to_val"]) if values["date_to_val"] else None
    try:
        validator(date_from, date_to)
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


def _prepare_search_results(st_module: Any, deps: Any, results: list[Any]) -> tuple[Any, ...]:
    """Render summary state and clamp pagination before slicing the current result page."""
    sort_options = deps.sort_options
    as_optional_str_fn = deps.as_optional_str_fn
    as_optional_float_fn = deps.as_optional_float_fn
    build_active_filter_labels_fn = deps.build_active_filter_labels_fn
    render_results_summary_fn = deps.render_results_summary_fn
    page_size = deps.page_size
    sort_value = st_module.session_state.get("web_sort", "relevance")
    sort_label = next((label for label, value in sort_options.items() if value == sort_value), "Relevance")
    filters = cast(dict[str, Any], st_module.session_state.get("web_filters", {}))
    sender_filter = as_optional_str_fn(filters.get("sender"))
    to_filter_val = as_optional_str_fn(filters.get("to"))
    subject_filter = as_optional_str_fn(filters.get("subject"))
    folder_filter = as_optional_str_fn(filters.get("folder"))
    cc_filter = as_optional_str_fn(filters.get("cc"))
    bcc_filter = as_optional_str_fn(filters.get("bcc"))
    has_att_filter = filters.get("has_attachments")
    priority_filter = filters.get("priority")
    email_type_filter = as_optional_str_fn(filters.get("email_type"))
    date_from_filter = as_optional_str_fn(filters.get("date_from"))
    date_to_filter = as_optional_str_fn(filters.get("date_to"))
    min_score_filter = as_optional_float_fn(filters.get("min_score"))
    active_filter_labels = build_active_filter_labels_fn(
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

    render_results_summary_fn(results, active_filter_labels, sort_label, search_modes=search_modes)

    total_pages = max(1, (len(results) + page_size - 1) // page_size)
    page = max(0, min(int(st_module.session_state.get("web_page", 0)), total_pages - 1))
    page_results = results[page * page_size : (page + 1) * page_size]

    return results, sort_value, filters, page, page_results, total_pages


def _render_search_thread(st_module: Any, retriever: Any) -> None:
    """Render and close the canonical conversation selected in session state."""
    thread_id = st_module.session_state.get("web_thread_id")
    if thread_id:
        st_module.markdown("### Conversation Thread")
        st_module.caption("Canonical conversation view. Inferred thread groups remain available through CLI/MCP workflows.")
        thread_results = retriever.search_by_thread(thread_id)
        if thread_results:
            st_module.markdown(_thread_summary_html(thread_results), unsafe_allow_html=True)

            for idx, tr in enumerate(thread_results, 1):
                st_module.markdown(_thread_email_html(idx, tr), unsafe_allow_html=True)
        else:
            st_module.info("No emails found for this thread.")
        if st_module.button("Close Thread View", type="secondary"):
            del st_module.session_state["web_thread_id"]
            st_module.rerun()
        st_module.divider()


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
    st_module: Any,
    retriever: Any,
    deps: Any,
    results: list[Any],
    sort_value: str,
    filters: dict[str, Any],
    page: int,
    page_results: list[Any],
    total_pages: int,
) -> None:
    """Render the three-pane workspace with pagination and export controls."""
    render_search_workspace_impl(
        st_module=st_module,
        retriever=retriever,
        results=results,
        page_results=page_results,
        page=page,
        page_size=deps.page_size,
        total_pages=total_pages,
        filters=filters,
        sort_value=sort_value,
        build_export_payload_fn=deps.build_export_payload_fn,
        build_csv_export_fn=deps.build_csv_export_fn,
    )


_CSV_FORMULA_CHARS = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe_cell(value: str) -> str:
    """Make a cell value safe for CSV export by prefixing with quote if it starts with formula characters."""
    if value and value[0] in _CSV_FORMULA_CHARS:
        return f"'{value}"
    return value


def _build_csv_export(results: list[Any]) -> str:
    """Serialize result summaries to formula-safe CSV text."""
    output = io.StringIO()
    fieldnames = ["date", "sender", "subject", "folder", "score", "text_preview"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for result in results:
        meta = result.metadata
        text = result.text or ""
        writer.writerow(
            {
                "date": str(meta.get("date", ""))[:10],
                "sender": _csv_safe_cell(meta.get("sender_name") or meta.get("sender_email", "")),
                "subject": _csv_safe_cell(meta.get("subject", "")),
                "folder": _csv_safe_cell(meta.get("folder", "")),
                "score": f"{result.score:.2f}",
                "text_preview": _csv_safe_cell(text[:300]),
            }
        )
    return output.getvalue()


def _as_optional_str(value: Any) -> str | None:
    """Return string values unchanged and reject other filter types."""
    if isinstance(value, str):
        return value
    return None


def _as_optional_float(value: Any) -> float | None:
    """Return finite numeric values as floats and reject NaN or infinity."""
    import math

    if isinstance(value, int | float):
        float_value = float(value)
        if math.isnan(float_value) or math.isinf(float_value):
            return None
        return float_value
    return None
