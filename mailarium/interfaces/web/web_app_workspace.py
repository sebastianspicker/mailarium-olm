"""Three-pane search workspace for the Streamlit application."""

from __future__ import annotations

import json
import re
from html import escape as html_escape
from typing import Any


def render_search_workspace_impl(
    *,
    st_module: Any,
    retriever: Any,
    results: list[Any],
    page_results: list[Any],
    page: int,
    page_size: int,
    total_pages: int,
    filters: dict[str, Any],
    sort_value: str,
    build_export_payload_fn: Any,
    build_csv_export_fn: Any,
) -> None:
    """Render ranked results, the selected message, and its source inspector."""
    selected = _selected_result(st_module, page_results)
    columns = st_module.columns([1.25, 2.05, 1.08], gap=None)
    with columns[0]:
        _render_result_index(st_module, results, page_results, selected, page, page_size, total_pages)
    with columns[1]:
        _render_document(st_module, selected, retriever)
    with columns[2]:
        _render_source_inspector(
            st_module,
            selected,
            results,
            filters,
            sort_value,
            build_export_payload_fn,
            build_csv_export_fn,
        )


def _selected_result(st_module: Any, page_results: list[Any]) -> Any:
    """Resolve a stable selection and fall back to the first visible result."""
    selected_id = str(st_module.session_state.get("web_selected_chunk_id", ""))
    selected = next((result for result in page_results if str(result.chunk_id) == selected_id), None)
    if selected is None:
        selected = page_results[0]
        st_module.session_state["web_selected_chunk_id"] = str(selected.chunk_id)
    return selected


def _render_result_index(
    st_module: Any,
    results: list[Any],
    page_results: list[Any],
    selected: Any,
    page: int,
    page_size: int,
    total_pages: int,
) -> None:
    """Render compact selectable correspondence rows."""
    st_module.markdown("<span class='mailarium-results-marker' aria-hidden='true'></span>", unsafe_allow_html=True)
    st_module.markdown("<div class='workspace-label'>Ranked correspondence</div>", unsafe_allow_html=True)
    selected_id = str(selected.chunk_id)
    for index, result in enumerate(page_results, start=page * page_size + 1):
        metadata = result.metadata
        subject = str(metadata.get("subject") or "(no subject)")
        sender = str(metadata.get("sender_name") or metadata.get("sender_email") or "Unknown sender")
        date = str(metadata.get("date") or "")[:10]
        preview = _compact_text(result.text, 82)
        attachment_count = str(metadata.get("attachment_count") or "0")
        badges = "THREAD"
        if attachment_count not in {"", "0", "None"}:
            badges += f"  ·  {attachment_count} ATT."
        label = f"{index} · {float(result.score):.0%}\n\n**{subject}**\n\n{sender} · {date}\n\n{badges}\n\n{preview}"
        is_selected = str(result.chunk_id) == selected_id
        if st_module.button(
            label,
            key=f"workspace-result-{result.chunk_id}",
            type="primary" if is_selected else "secondary",
            use_container_width=True,
        ):
            st_module.session_state["web_selected_chunk_id"] = str(result.chunk_id)
            st_module.rerun()

    start = page * page_size + 1
    end = min(start + len(page_results) - 1, len(results))
    st_module.caption(f"Showing {start} to {end} of {len(results)} results")
    if total_pages > 1:
        nav = st_module.columns(2, gap="small")
        with nav[0]:
            if st_module.button("Previous", disabled=page == 0, use_container_width=True):
                st_module.session_state["web_page"] = page - 1
                st_module.rerun()
        with nav[1]:
            if st_module.button("Next", disabled=page >= total_pages - 1, use_container_width=True):
                st_module.session_state["web_page"] = page + 1
                st_module.rerun()


def _render_document(st_module: Any, result: Any, retriever: Any) -> None:
    """Render the selected result as a readable source document."""
    document_html, conversation_id = _document_markup(result)
    st_module.markdown("<span class='mailarium-document-marker' aria-hidden='true'></span>", unsafe_allow_html=True)
    st_module.markdown(document_html, unsafe_allow_html=True)
    if conversation_id and retriever is not None:
        if st_module.button("View full thread", key=f"workspace-thread-{result.chunk_id}", use_container_width=True):
            st_module.session_state["web_thread_id"] = conversation_id
            st_module.rerun()


def _document_markup(result: Any) -> tuple[str, str]:
    """Build escaped document markup and return its canonical thread identifier."""
    metadata = result.metadata
    metadata_html, conversation_id = _document_metadata_markup(metadata)
    body = _document_body_html(result.text or "")
    attachment_html = _document_attachment_markup(metadata)
    return (
        "<article class='archive-document'>"
        f"<header><h2>{html_escape(_metadata_text(metadata, 'subject', '(no subject)'))}</h2>"
        "<div class='document-actions' aria-hidden='true'>&#8942;</div></header>"
        f"{metadata_html}"
        f"<div class='document-body'>{body or 'No body text was recovered for this result.'}</div>"
        f"{attachment_html}"
        "</article>",
        conversation_id,
    )


def _document_metadata_markup(metadata: dict[str, Any]) -> tuple[str, str]:
    """Build escaped message metadata and retain the canonical thread identifier."""
    sender = _document_sender_markup(metadata)
    recipients = html_escape(_metadata_text(metadata, "to", "Not recorded"))
    date = html_escape(_metadata_text(metadata, "date", "Unknown date")[:19].replace("T", " · "))
    source = html_escape(_metadata_text(metadata, "folder", "Archive"))
    conversation_id = _metadata_text(metadata, "conversation_id", "").strip()
    thread_text = "Conversation available" if conversation_id else "Single indexed message"
    return (
        "<div class='document-metadata'>"
        f"<span><b>From</b>{sender}</span><span><b>Date</b>{date}</span>"
        f"<span><b>To</b>{recipients}</span><span><b>Source</b>{source}</span>"
        "</div>"
        f"<div class='thread-line'><span class='thread-dots' aria-hidden='true'>&#9679;&mdash;&#9675;&mdash;&#9675;</span>"
        f"<span>{thread_text}</span></div>",
        conversation_id,
    )


def _document_sender_markup(metadata: dict[str, Any]) -> str:
    """Build the escaped sender display, preserving the name-and-email format."""
    sender_name = _metadata_text(metadata, "sender_name", "")
    sender_email = _metadata_text(metadata, "sender_email", "")
    sender = html_escape(sender_name or sender_email or "Unknown sender")
    if sender_name and sender_email:
        return f"{html_escape(sender_name)} &lt;{html_escape(sender_email)}&gt;"
    return sender


def _metadata_text(metadata: dict[str, Any], field: str, fallback: str) -> str:
    """Normalize one optional message metadata field to its established fallback."""
    return str(metadata.get(field) or fallback)


def _document_attachment_markup(metadata: dict[str, Any]) -> str:
    """Build the visible attachment list with the existing bounded display policy."""
    attachments = _attachment_names(metadata)
    attachment_html = "".join(
        f"<div class='document-attachment'><span aria-hidden='true'>&#9638;</span>"
        f"<strong>{html_escape(name)}</strong><small>Local attachment</small></div>"
        for name in attachments[:4]
    )
    if not attachment_html:
        attachment_html = "<div class='document-empty-attachments'>No attachments recorded</div>"
    return f"<div class='document-attachments'><small>{len(attachments)} attachments</small>{attachment_html}</div>"


def _render_source_inspector(
    st_module: Any,
    result: Any,
    results: list[Any],
    filters: dict[str, Any],
    sort_value: str,
    build_export_payload_fn: Any,
    build_csv_export_fn: Any,
) -> None:
    """Render visible provenance and safe export controls for the selected source."""
    metadata = result.metadata
    uid = str(metadata.get("uid") or result.chunk_id)
    conversation_id = str(metadata.get("conversation_id") or "Not recorded")
    folder = str(metadata.get("folder") or "Archive")
    quote = _quoted_proof(result.text or "")
    retrieval_modes = ["Hybrid" if filters.get("hybrid") else "Semantic"]
    if filters.get("rerank"):
        retrieval_modes.append("Rerank")
    st_module.markdown("<span class='mailarium-inspector-marker' aria-hidden='true'></span>", unsafe_allow_html=True)
    st_module.markdown(
        "<div class='inspector-heading'><span>Source</span>"
        "<strong><i aria-hidden='true'>&#10003;</i> Source matched</strong></div>"
        "<div class='inspector-section'><label>Quoted proof</label>"
        f"<blockquote>{html_escape(quote)}</blockquote></div>"
        "<dl class='provenance-list'>"
        f"<div><dt>Message UID</dt><dd>{html_escape(uid)}</dd></div>"
        f"<div><dt>Conversation ID</dt><dd>{html_escape(conversation_id)}</dd></div>"
        f"<div><dt>Folder / Archive</dt><dd>{html_escape(folder)}</dd></div>"
        f"<div><dt>Retrieved by</dt><dd>{html_escape(' + '.join(retrieval_modes))}</dd></div>"
        "</dl>",
        unsafe_allow_html=True,
    )
    st_module.selectbox(
        "Category",
        ["General", "Operations", "Finance", "Customer support", "Decision", "Commitment"],
        key=f"workspace-category-{result.chunk_id}",
    )
    st_module.text_area(
        "Notes",
        key=f"workspace-notes-{result.chunk_id}",
        placeholder="Optional operator notes",
        max_chars=500,
        height=72,
    )
    if st_module.button(
        "Add to evidence",
        key=f"workspace-evidence-{result.chunk_id}",
        type="primary",
        use_container_width=True,
        help="Evidence mutation remains a CLI/MCP workflow in this alpha.",
    ):
        st_module.info("Use the CLI or MCP evidence tools to create a custody-tracked evidence item.")

    selected_payload = build_export_payload_fn(
        query=st_module.session_state.get("web_query", ""),
        results=[result],
        filters=filters,
        sort_by=sort_value,
    )
    st_module.download_button(
        "Export source",
        data=json.dumps(selected_payload, indent=2, default=str),
        file_name="mailarium-source.json",
        mime="application/json",
        use_container_width=True,
    )
    with st_module.expander("Export all results", expanded=False):
        st_module.download_button(
            "Download JSON",
            data=json.dumps(
                build_export_payload_fn(
                    query=st_module.session_state.get("web_query", ""),
                    results=results,
                    filters=filters,
                    sort_by=sort_value,
                ),
                indent=2,
                default=str,
            ),
            file_name="email-search-results.json",
            mime="application/json",
            use_container_width=True,
        )
        st_module.download_button(
            "Download CSV",
            data=build_csv_export_fn(results),
            file_name="email-search-results.csv",
            mime="text/csv",
            use_container_width=True,
        )


def _compact_text(value: str, limit: int) -> str:
    """Collapse whitespace and return a bounded display string."""
    compact = re.sub(r"\s+", " ", str(value)).strip()
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)].rstrip() + "…"


def _quoted_proof(value: str) -> str:
    """Use the first meaningful bounded sentence as visible source proof."""
    compact = re.sub(r"\s+", " ", str(value)).strip()
    if not compact:
        return "No recoverable source text is available for this result."
    sentences = re.split(r"(?<=[.!?])\s+", compact)
    candidate = next((sentence for sentence in sentences if len(sentence) >= 32), sentences[0])
    return _compact_text(candidate, 260)


def _document_body_html(value: str) -> str:
    """Escape source text and mark the quoted proof as the provenance anchor."""
    compact = _compact_text(value, 2400)
    quote = _quoted_proof(compact)
    escaped = html_escape(compact)
    escaped_quote = html_escape(quote)
    if escaped_quote not in escaped:
        return escaped
    return escaped.replace(
        escaped_quote,
        f"<mark class='provenance-highlight'>{escaped_quote}</mark>",
        1,
    )


def _attachment_names(metadata: dict[str, Any]) -> list[str]:
    """Normalize the existing comma- or semicolon-separated attachment field."""
    raw = str(metadata.get("attachment_names") or "")
    return [name.strip() for name in re.split(r"[,;]", raw) if name.strip()]
