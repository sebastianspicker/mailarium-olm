"""Search and source workspace for the Streamlit application."""

from __future__ import annotations

import json
import logging
import re
from html import escape as html_escape
from types import SimpleNamespace
from typing import Any

import streamlit as st

from .presentation import build_csv_export, build_export_payload

logger = logging.getLogger(__name__)


def render_search_workspace(
    *,
    retriever: Any,
    results: list[Any],
    page_results: list[Any],
    page: int,
    page_size: int,
    total_pages: int,
    filters: dict[str, Any],
    sort_value: str,
) -> None:
    """Render ranked results beside the selected source and its disclosures."""
    if not page_results:
        st.info("No messages on this page. Search again to inspect a source.")
        return
    selected = _selected_result(page_results)
    columns = st.columns([0.34, 0.66], gap=None)
    with columns[0]:
        _render_result_index(results, page_results, selected, page, page_size, total_pages)
    with columns[1]:
        source = _load_source(selected, retriever)
        _render_document(source, retriever)
        _render_source_inspector(
            source,
            results,
            filters,
            sort_value,
        )


def _selected_result(page_results: list[Any]) -> Any:
    """Resolve a stable selection and fall back to the first visible result."""
    selected_id = str(st.session_state.get("web_selected_chunk_id", ""))
    selected = next((result for result in page_results if str(result.chunk_id) == selected_id), None)
    if selected is None:
        selected = page_results[0]
        st.session_state["web_selected_chunk_id"] = str(selected.chunk_id)
    return selected


def _render_result_index(
    results: list[Any],
    page_results: list[Any],
    selected: Any,
    page: int,
    page_size: int,
    total_pages: int,
) -> None:
    """Render compact selectable correspondence rows."""
    st.markdown("<span class='mailarium-results-marker' aria-hidden='true'></span>", unsafe_allow_html=True)
    selected_id = str(selected.chunk_id)
    for index, result in enumerate(page_results, start=page * page_size + 1):
        metadata = result.metadata
        subject = str(metadata.get("subject") or "(no subject)")
        sender = str(metadata.get("sender_name") or metadata.get("sender_email") or "Unknown sender")
        date = str(metadata.get("date") or "")[:10]
        preview = _compact_text(result.text, 82)
        attachment_count = str(metadata.get("attachment_count") or "0")
        badges = ""
        if attachment_count not in {"", "0", "None"}:
            badges = f"{attachment_count} attachments"
        subject, sender, preview, badges = (_escape_markdown(value) for value in (subject, sender, preview, badges))
        label = f"{index} · **{subject}**\n\n{sender} · {_escape_markdown(date)}\n\n{preview}"
        if badges:
            label += f"\n\n{badges}"
        is_selected = str(result.chunk_id) == selected_id
        if st.button(
            label,
            key=f"workspace-result-{result.chunk_id}",
            type="primary" if is_selected else "secondary",
            use_container_width=True,
        ):
            st.session_state["web_selected_chunk_id"] = str(result.chunk_id)
            st.rerun()

    start = page * page_size + 1
    end = min(start + len(page_results) - 1, len(results))
    st.caption(f"Showing {start} to {end} of {len(results)} results")
    if total_pages > 1:
        nav = st.columns(2, gap="small")
        with nav[0]:
            if st.button("Previous", disabled=page == 0, use_container_width=True):
                st.session_state["web_page"] = page - 1
                st.rerun()
        with nav[1]:
            if st.button("Next", disabled=page >= total_pages - 1, use_container_width=True):
                st.session_state["web_page"] = page + 1
                st.rerun()


def _render_document(result: Any, retriever: Any) -> None:
    """Render the selected result as a readable source document."""
    document_html, conversation_id = _document_markup(result)
    st.markdown("<span class='mailarium-document-marker' aria-hidden='true'></span>", unsafe_allow_html=True)
    st.markdown(document_html, unsafe_allow_html=True)
    uid = str(result.metadata.get("uid") or "").strip()
    if st.button(
        "Capture finding",
        key=f"workspace-evidence-{result.chunk_id}",
        type="primary",
        disabled=not bool(uid) or not getattr(result, "source_available", False),
        help="Open the evidence form with this stored source message.",
    ):
        st.session_state["web_capture_uid"] = uid
        st.session_state["web_route"] = "Evidence"
        st.rerun()
    if conversation_id and retriever is not None:
        if st.button("View full thread", key=f"workspace-thread-{result.chunk_id}", use_container_width=True):
            st.session_state["web_thread_id"] = conversation_id
            st.rerun()


def _document_markup(result: Any) -> tuple[str, str]:
    """Build escaped document markup and return its canonical thread identifier."""
    metadata = result.metadata
    metadata_html, conversation_id = _document_metadata_markup(metadata)
    body = _document_body_html(result.text or "")
    attachment_html = _document_attachment_markup(metadata)
    return (
        "<article class='archive-document'>"
        "<header><span class='workspace-label'>Source message</span>"
        f"<h2>{html_escape(_metadata_text(metadata, 'subject', '(no subject)'))}</h2>"
        "</header>"
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
    date = html_escape(_metadata_text(metadata, "date", "Unknown date").replace("T", " · ").replace("Z", " UTC"))
    source = html_escape(_metadata_text(metadata, "folder", "Archive"))
    conversation_id = _metadata_text(metadata, "conversation_id", "").strip()
    thread_text = "Canonical thread ID recorded" if conversation_id else "No canonical thread ID recorded"
    return (
        "<div class='document-metadata'>"
        f"<span><b>From</b>{sender}</span><span><b>Date</b>{date}</span>"
        f"<span><b>To</b>{recipients}</span><span><b>Source</b>{source}</span>"
        "</div>"
        "<div class='thread-line'>"
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
    value = metadata.get(field) or fallback
    return ", ".join(str(item) for item in value) if isinstance(value, list) else str(value)


def _document_attachment_markup(metadata: dict[str, Any]) -> str:
    """Build the visible attachment list with the existing bounded display policy."""
    attachments = _attachment_names(metadata)
    attachment_html = "".join(
        f"<div class='document-attachment'><span aria-hidden='true'>&#9638;</span>"
        f"<strong>{html_escape(name)}</strong><small>Local attachment</small></div>"
        for name in attachments[:4]
    )
    if not attachment_html:
        return "<div class='document-attachments'>No attachments recorded</div>"
    return f"<div class='document-attachments'><small>{len(attachments)} attachments</small>{attachment_html}</div>"


def _render_source_inspector(
    result: Any,
    results: list[Any],
    filters: dict[str, Any],
    sort_value: str,
) -> None:
    """Render visible provenance and safe export controls for the selected source."""
    metadata = result.metadata
    with st.expander("Source details", expanded=False):
        st.markdown("<span class='mailarium-inspector-marker' aria-hidden='true'></span>", unsafe_allow_html=True)
        fields = {
            "Message UID": metadata.get("uid") or "Not recorded",
            "Chunk ID": result.chunk_id,
            "Conversation ID": metadata.get("conversation_id") or "Not recorded",
            "Folder / Archive": metadata.get("folder") or "Not recorded",
            "Retrieval score": str(result.score),
            "Search mode": "Hybrid" if filters.get("hybrid") else "Semantic",
        }
        st.markdown(
            "<dl class='provenance-list'>"
            + "".join(
                f"<div><dt>{html_escape(label)}</dt><dd>{html_escape(str(value))}</dd></div>" for label, value in fields.items()
            )
            + "</dl>",
            unsafe_allow_html=True,
        )
        st.caption("Retrieval scores rank candidate messages. They do not establish a finding.")
        st.json(metadata)
    with st.expander("Download source and results", expanded=False):
        st.caption(
            "Source JSON includes the stored text when available. CSV contains summaries; "
            "all-result JSON contains retrieval excerpts."
        )
        for label, export_results, prefix in (
            ("this source", [result], "mailarium-source"),
            ("all results", results, "email-search-results"),
        ):
            payload = build_export_payload(
                query=st.session_state.get("web_query", ""),
                results=export_results,
                filters=filters,
                sort_by=sort_value,
            )
            st.download_button(
                f"Download {label} JSON",
                data=json.dumps(payload, indent=2, default=str),
                file_name=f"{prefix}.json",
                mime="application/json",
                use_container_width=True,
            )
            st.download_button(
                f"Download {label} CSV",
                data=build_csv_export(export_results),
                file_name=f"{prefix}.csv",
                mime="text/csv",
                use_container_width=True,
            )


def _compact_text(value: str, limit: int) -> str:
    """Collapse whitespace and return a bounded display string."""
    compact = re.sub(r"\s+", " ", str(value)).strip()
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)].rstrip() + "…"


def _document_body_html(value: str) -> str:
    """Escape the entire stored text while preserving message line breaks."""
    return html_escape(str(value)).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br/>")


def _attachment_names(metadata: dict[str, Any]) -> list[str]:
    """Normalize the existing comma- or semicolon-separated attachment field."""
    names = metadata.get("attachment_names")
    if isinstance(names, list):
        return [str(name) for name in names if name]
    raw = str(names or "")
    return [name.strip() for name in re.split(r"[,;]", raw) if name.strip()]


def _escape_markdown(value: str) -> str:
    """Keep untrusted correspondence labels literal inside Streamlit buttons."""
    return re.sub(r"([\\`*_{}\[\]()<>#+.!|~-])", r"\\\1", value)


def _load_source(result: Any, retriever: Any) -> Any:
    """Read the full stored message through the runtime-owned archive connection."""
    uid = str(result.metadata.get("uid") or "").strip()
    full = None
    archive = getattr(retriever, "email_db", None)
    if uid and archive is not None:
        try:
            full = archive.queries.get_email_full(uid)
        except Exception:
            logger.exception("Stored source lookup failed")
    if not isinstance(full, dict) or str(full.get("uid") or "") != uid:
        st.warning("The full stored source is unavailable. Showing the retrieval excerpt; capture requires a stored source.")
        return SimpleNamespace(
            chunk_id=result.chunk_id,
            score=result.score,
            metadata=result.metadata,
            text=result.text,
            source_available=False,
        )
    metadata = {**result.metadata, **full}
    attachments = full.get("attachments") or []
    if attachments:
        metadata["attachment_names"] = [item.get("name") for item in attachments if isinstance(item, dict) and item.get("name")]
    body = full.get("forensic_body_text") or full.get("body_text") or full.get("raw_body_text") or ""
    return SimpleNamespace(
        chunk_id=result.chunk_id,
        score=result.score,
        metadata=metadata,
        text=str(body),
        source_available=True,
    )
