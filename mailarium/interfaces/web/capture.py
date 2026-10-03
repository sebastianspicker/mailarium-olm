"""Source-linked evidence capture through the canonical archive repository."""

from __future__ import annotations

import hashlib
import json
import logging
from html import escape
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import streamlit as st

from .workspace import _document_markup

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase

logger = logging.getLogger(__name__)


def render_evidence_capture(*, database: ArchiveDatabase, uid: str) -> None:
    """Render the stored source beside a persistent native evidence draft."""
    st.markdown("<h1 class='page-title'>Record what the source supports</h1>", unsafe_allow_html=True)
    query = str(st.session_state.get("web_query") or "")
    filters = st.session_state.get("web_filters", {})
    context = [query] if query else []
    for key, label in (("folder", "Folder contains"), ("date_from", "From"), ("date_to", "To")):
        if filters.get(key):
            context.append(f"{label}: {filters[key]}")
    if context:
        st.markdown(
            "<div class='search-control-chips'>" + "".join(f"<span>{escape(value)}</span>" for value in context) + "</div>",
            unsafe_allow_html=True,
        )
    try:
        source = database.queries.get_email_full(uid)
    except Exception:
        logger.exception("Capture source lookup failed")
        st.error("The stored source could not be loaded. Check archive diagnostics and try again.")
        return
    if not source or str(source.get("uid") or "") != uid:
        st.warning("This source message is no longer available in the archive. Return to Inspect to select a source.")
        _capture_navigation()
        return
    source_column, form_column = st.columns([0.48, 0.52], gap="small")
    with source_column, st.container(key="capture-source"):
        render_capture_source(source)
    with form_column, st.container(key="capture-form"):
        _render_capture_controls(database, uid)


def render_capture_source(source: dict[str, Any]) -> None:
    """Render stored source text and metadata with the same escaping as Inspect."""
    body = source.get("forensic_body_text") or source.get("body_text") or source.get("raw_body_text") or ""
    metadata = dict(source)
    attachments = source.get("attachments") or []
    metadata["attachment_names"] = [item["name"] for item in attachments if isinstance(item, dict) and item.get("name")]
    markup, _ = _document_markup(SimpleNamespace(metadata=metadata, text=str(body)))
    st.markdown(markup, unsafe_allow_html=True)
    with st.expander("Source details"):
        st.json(source)


def _render_capture_controls(db: ArchiveDatabase, uid: str) -> None:
    """Keep editable draft values separate from widget lifecycle and saved records."""
    draft_key = f"capture-draft-{uid}"
    draft = st.session_state.get(draft_key, {})
    key_prefix = hashlib.sha256(uid.encode()).hexdigest()[:20]
    quote = st.text_area("Exact quote", value=draft.get("key_quote", ""), key=f"quote-{key_prefix}", height=110)
    _render_quote_status(db, uid, quote)
    category = st.text_input("Category", value=draft.get("category", ""), max_chars=80, key=f"category-{key_prefix}")
    summary = st.text_area("Why this matters", value=draft.get("summary", ""), key=f"summary-{key_prefix}", height=100)
    relevance = st.selectbox(
        "Relevance",
        [1, 2, 3, 4, 5],
        index=int(draft.get("relevance", 3)) - 1,
        format_func=lambda value: f"{value} · {['Tangential', 'Background', 'Supporting', 'Significant', 'Critical'][value - 1]}",
        key=f"relevance-{key_prefix}",
    )
    notes = st.text_area("Analyst notes (optional)", value=draft.get("notes", ""), key=f"notes-{key_prefix}", height=100)
    values = {
        "email_uid": uid,
        "category": category,
        "key_quote": quote,
        "summary": summary,
        "relevance": relevance,
        "notes": notes,
    }
    st.session_state[draft_key] = values
    token = _capture_token(db, values)
    saved = st.session_state.get("web_capture_saved", {})
    if saved.get("token") == token:
        _render_saved_finding(saved["item"])
    elif st.button("Save finding", type="primary", key="capture-save"):
        _save_finding(db, values, token)
    _capture_navigation()


def _capture_token(db: ArchiveDatabase, values: dict[str, Any]) -> str:
    """Identify one submitted draft within this session's archive instance."""
    payload = json.dumps(values, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(f"{id(db)}:{payload}".encode()).hexdigest()


def _save_finding(db: ArchiveDatabase, values: dict[str, Any], token: str) -> None:
    """Validate required fields and save once per submitted draft in this session."""
    if not all(str(values[field]).strip() for field in ("key_quote", "category", "summary")):
        st.error("Enter an exact quote, category, and explanation of why this matters.")
        return
    if len(values["category"].strip()) > 80 or not 1 <= int(values["relevance"]) <= 5:
        st.error("Use a category of at most 80 characters and relevance from 1 to 5.")
        return
    saved_submissions = st.session_state.setdefault("web_capture_submissions", {})
    if token in saved_submissions:
        st.session_state["web_capture_saved"] = {"token": token, "item": saved_submissions[token]}
        st.rerun()
        return
    try:
        item = db.evidence.add_evidence(**values)
    except Exception:
        logger.exception("Evidence capture failed")
        st.error("The finding could not be saved. Check that its source remains available and try again.")
        return
    saved_submissions[token] = item
    st.session_state["web_capture_saved"] = {"token": token, "item": item}
    st.rerun()


def _render_quote_status(db: ArchiveDatabase, uid: str, quote: str) -> None:
    """Describe canonical exact and near matching without factual-verification claims."""
    if not quote.strip():
        st.caption("Paste a passage from the stored message to check its text match.")
        return
    try:
        match = db.evidence.quote_verification_state(email_uid=uid, quote=quote)
    except Exception:
        logger.exception("Evidence quote precheck failed")
        st.warning("The text-match preview is unavailable. Saving still runs the canonical quote check.")
        return
    state = match.get("state")
    if state == "exact_verified":
        label = "Text match in stored message"
    elif state == "near_exact_verified":
        label = "Near text match in stored message; recorded as unverified"
    else:
        label = "No text match in stored message; you can save this as unverified"
    status_class = "quote-status" if state == "exact_verified" else "quote-status is-unmatched"
    st.markdown(f"<div class='{status_class}'>{escape(label)}</div>", unsafe_allow_html=True)
    st.caption("Matching normalizes case, whitespace, Unicode and punctuation. A text match does not verify the conclusion.")


def _render_saved_finding(item: dict[str, Any]) -> None:
    """Keep the persisted record visible and link it to the export flow."""
    st.success(f"Finding {item['id']} saved to the evidence ledger.")
    if not item.get("verified"):
        st.warning("This finding was saved as unverified. Review its quote and source before sharing.")
    with st.expander("Saved finding details"):
        st.json(item)
    if st.button("Continue to export", type="primary", key="capture-export"):
        st.session_state["web_route"] = "Export"
        st.rerun()


def _capture_navigation() -> None:
    """Offer source navigation and the existing collection browser."""
    back, browse = st.columns(2)
    if back.button("Back to source", key="capture-back"):
        st.session_state["web_route"] = "Inspect"
        st.rerun()
    if browse.button("Browse evidence", key="capture-browse"):
        st.session_state.pop("web_capture_uid", None)
        st.rerun()
