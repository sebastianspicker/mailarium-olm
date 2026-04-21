"""Search-page controller helpers for the Streamlit app."""

from __future__ import annotations

import csv
import io
import json
from html import escape as html_escape
from typing import Any, cast


def render_search_page_impl(
    *,
    st_module: Any,
    retriever: Any,
    sort_options: dict[str, str],
    page_size: int,
    render_results_fn: Any,
    render_results_summary_fn: Any,
    build_csv_export_fn: Any,
    build_active_filter_labels_fn: Any,
    build_export_payload_fn: Any,
    sort_search_results_fn: Any,
    validate_date_window_fn: Any,
    as_optional_str_fn: Any,
    as_optional_float_fn: Any,
) -> None:
    if retriever.collection.count() == 0:
        st_module.warning("No emails indexed yet.")
        st_module.info(
            "To index your Outlook archive, run the ingestion script:\n\n"
            "```\npython -m src.ingest path/to/export.olm\n```\n\n"
            "Or use the **`email_ingest`** MCP tool directly from your MCP client."
        )
        return

    st_module.session_state.setdefault("web_results", [])
    st_module.session_state.setdefault("web_query", "")
    st_module.session_state.setdefault("web_filters", {})
    st_module.session_state.setdefault("web_sort", "relevance")
    st_module.session_state.setdefault("web_page", 0)
    st_module.session_state.setdefault("web_thread_id", None)

    with st_module.form("search_form", clear_on_submit=False):
        query = st_module.text_input(
            "Search Query",
            placeholder="e.g. contract renewal emails from legal department",
            help="Natural language query. The system uses semantic search to find relevant emails.",
        )

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

        with st_module.expander("Metadata Filters", expanded=False):
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

        with st_module.expander("Search Mode", expanded=False):
            mode_col1, mode_col2, mode_col3 = st_module.columns(3)
            with mode_col1:
                use_hybrid = st_module.checkbox(
                    "Hybrid search",
                    help="Combines semantic vectors with BM25 keyword matching for better recall.",
                )
            with mode_col2:
                use_rerank = st_module.checkbox(
                    "Re-rank results",
                    help="Re-ranks using ColBERT/cross-encoder for better precision. Slower but more accurate.",
                )
            with mode_col3:
                use_expand = st_module.checkbox(
                    "Expand query",
                    help="Adds semantically related terms for broader coverage.",
                )

        search_clicked = st_module.form_submit_button("Search", type="primary", use_container_width=True)

    if search_clicked:
        if not query.strip():
            st_module.warning("Please enter a query.")
        else:
            valid_date_from = str(date_from_val) if date_from_val else None
            valid_date_to = str(date_to_val) if date_to_val else None
            try:
                validate_date_window_fn(valid_date_from, valid_date_to)
            except ValueError:
                st_module.error("Date From cannot be later than Date To.")
            else:
                min_score_value = round(float(min_score), 2) if min_score > 0.0 else None
                has_att_value = True if has_attachments else None
                priority_value = int(priority) if priority and priority > 0 else None
                email_type_value = email_type_label if email_type_label != "Any" else None
                filters = {
                    "sender": sender or None,
                    "to": to_filter or None,
                    "subject": subject or None,
                    "folder": folder or None,
                    "cc": cc or None,
                    "bcc": bcc or None,
                    "has_attachments": has_att_value,
                    "priority": priority_value,
                    "email_type": email_type_value,
                    "date_from": valid_date_from,
                    "date_to": valid_date_to,
                    "min_score": min_score_value,
                    "hybrid": use_hybrid,
                    "rerank": use_rerank,
                    "expand_query": use_expand,
                }

                results = retriever.search_filtered(
                    query=query,
                    top_k=int(top_k),
                    sender=filters["sender"],
                    to=filters["to"],
                    subject=filters["subject"],
                    folder=filters["folder"],
                    cc=filters["cc"],
                    bcc=filters["bcc"],
                    has_attachments=filters["has_attachments"],
                    priority=filters["priority"],
                    email_type=filters["email_type"],
                    date_from=filters["date_from"],
                    date_to=filters["date_to"],
                    min_score=filters["min_score"],
                    hybrid=filters["hybrid"],
                    rerank=filters["rerank"],
                    expand_query=filters["expand_query"],
                )
                sort_value = sort_options[sort_label]
                sorted_results = sort_search_results_fn(results, sort_value)

                st_module.session_state["web_results"] = sorted_results
                st_module.session_state["web_query"] = query
                st_module.session_state["web_filters"] = filters
                st_module.session_state["web_sort"] = sort_value
                st_module.session_state["web_page"] = 0

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
        sender=sender_filter,
        to=to_filter_val,
        subject=subject_filter,
        folder=folder_filter,
        cc=cc_filter,
        bcc=bcc_filter,
        has_attachments=has_att_filter if isinstance(has_att_filter, bool) else None,
        priority=int(priority_filter) if isinstance(priority_filter, (int, float)) else None,
        email_type=email_type_filter,
        date_from=date_from_filter,
        date_to=date_to_filter,
        min_score=min_score_filter,
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

    render_results_summary_fn(results, active_filter_labels, sort_label, search_modes=search_modes)

    total_pages = max(1, (len(results) + page_size - 1) // page_size)
    page = max(0, min(int(st_module.session_state.get("web_page", 0)), total_pages - 1))
    page_results = results[page * page_size : (page + 1) * page_size]

    thread_id = st_module.session_state.get("web_thread_id")
    if thread_id:
        st_module.markdown("### Conversation Thread")
        st_module.caption("Canonical conversation view. Inferred thread groups remain available through CLI/MCP workflows.")
        thread_results = retriever.search_by_thread(thread_id)
        if thread_results:
            participants = list(
                dict.fromkeys((tr.metadata.get("sender_name") or tr.metadata.get("sender_email", "?")) for tr in thread_results)
            )
            dates = [str(tr.metadata.get("date", ""))[:10] for tr in thread_results if tr.metadata.get("date")]
            thread_summary = (
                f"<div style='padding:0.6rem 1rem;background:#eef2f7;border-radius:8px;"
                f"font-size:0.82rem;color:#475569;margin-bottom:0.75rem;'>"
                f"<strong>{len(thread_results)} messages</strong> &middot; "
                f"<strong>{len(participants)} participants</strong>"
            )
            if dates:
                thread_summary += f" &middot; {min(dates)} to {max(dates)}"
            thread_summary += (
                f"<br/><span style='color:#94a3b8;'>Participants: "
                f"{html_escape(', '.join(participants[:5]))}"
                + (f" (+{len(participants) - 5})" if len(participants) > 5 else "")
                + "</span></div>"
            )
            st_module.markdown(thread_summary, unsafe_allow_html=True)

            for idx, tr in enumerate(thread_results, 1):
                tm = tr.metadata
                sender_val = tm.get("sender_name") or tm.get("sender_email", "?")
                date_val = str(tm.get("date", "?"))[:10]
                subj_val = tm.get("subject", "?")
                email_type = tm.get("email_type", "original")
                type_indicator = ""
                type_style = "font-size:0.72rem;font-weight:600;margin-left:0.4rem;"
                if email_type == "reply":
                    type_indicator = f"<span style='color:#5b21b6;{type_style}'>REPLY</span>"
                elif email_type == "forward":
                    type_indicator = f"<span style='color:#9d174d;{type_style}'>FWD</span>"
                body_text = tr.text[:800] if len(tr.text) > 800 else tr.text
                border_color = "#2563eb" if idx % 2 == 1 else "#7c3aed"
                st_module.markdown(
                    f"<div class='thread-email' style='border-left-color:{border_color};'>"
                    f"<div class='thread-email-header'>"
                    f"<strong>{idx}. {html_escape(str(sender_val))}</strong>{type_indicator}"
                    f" &middot; {html_escape(str(date_val))}"
                    f"<br/><span style='color:#64748b;font-size:0.78rem;'>{html_escape(str(subj_val))}</span>"
                    f"</div>"
                    f"<div class='thread-email-body'>{html_escape(body_text)}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        else:
            st_module.info("No emails found for this thread.")
        if st_module.button("Close Thread View", type="secondary"):
            del st_module.session_state["web_thread_id"]
            st_module.rerun()
        st_module.divider()

    preview_chars = st_module.slider("Preview Length", min_value=200, max_value=4000, value=1200, step=100)
    render_results_fn(page_results, preview_chars=preview_chars, retriever=retriever)

    if total_pages > 1:
        nav_col1, nav_col2, nav_col3 = st_module.columns([1, 2, 1])
        with nav_col1:
            if st_module.button("◀ Prev", disabled=page == 0):
                st_module.session_state["web_page"] = page - 1
                st_module.rerun()
        with nav_col2:
            st_module.caption(f"Page {page + 1} of {total_pages} ({len(results)} results total)")
        with nav_col3:
            if st_module.button("Next ▶", disabled=page >= total_pages - 1):
                st_module.session_state["web_page"] = page + 1
                st_module.rerun()

    st_module.divider()
    st_module.markdown("#### Export Results")
    export_col1, export_col2, export_col3 = st_module.columns([2, 2, 4])
    payload = build_export_payload_fn(
        query=st_module.session_state.get("web_query", ""),
        results=results,
        filters=filters,
        sort_by=sort_value,
    )
    with export_col1:
        st_module.download_button(
            label="Download JSON",
            data=json.dumps(payload, indent=2),
            file_name="email-search-results.json",
            mime="application/json",
            use_container_width=True,
        )
    with export_col2:
        csv_data = build_csv_export_fn(results)
        st_module.download_button(
            label="Download CSV",
            data=csv_data,
            file_name="email-search-results.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with export_col3:
        query_text = st_module.session_state.get("web_query", "")
        st_module.caption(f'Exporting {len(results)} results for query: "{query_text}"')


_CSV_FORMULA_CHARS = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe_cell(value: str) -> str:
    if value and value[0] in _CSV_FORMULA_CHARS:
        return f"'{value}"
    return value


def _build_csv_export(results: list[Any]) -> str:
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
    if isinstance(value, str):
        return value
    return None


def _as_optional_float(value: Any) -> float | None:
    import math

    if isinstance(value, (int, float)):
        float_value = float(value)
        if math.isnan(float_value) or math.isinf(float_value):
            return None
        return float_value
    return None
