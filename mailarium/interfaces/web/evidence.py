"""Evidence collection page helpers for the Streamlit app."""

from __future__ import annotations

from html import escape as html_escape
from typing import TYPE_CHECKING, Any

import streamlit as st

from .presentation import relevance_label

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase


def render_evidence_page(
    *,
    database: ArchiveDatabase | None,
) -> None:
    """Render the evidence collection page implementation."""
    if database is not None and st.session_state.get("web_capture_uid"):
        from .capture import render_evidence_capture

        render_evidence_capture(database=database, uid=str(st.session_state["web_capture_uid"]))
        return
    st.markdown(
        "<div class='page-heading'><h1>Evidence ledger</h1>"
        "<span class='page-note'>Every finding quotes a stored message. Treat the collection as provisional until each "
        "quote and its source have been reviewed.</span></div>",
        unsafe_allow_html=True,
    )

    if database is None:
        st.warning("The SQLite archive is not available. Run ingestion first to keep an evidence ledger.")
        return

    categories = _render_evidence_overview(database)
    items, total, cat_filter, min_relevance = _select_evidence_items(database, categories)
    _render_evidence_items(items, total)
    _render_export_handoff(cat_filter, min_relevance, bool(items))
    st.caption("Custody checks, dossiers and PDF export are available through the CLI and MCP evidence tools.")


def _render_evidence_overview(db: ArchiveDatabase) -> list[dict[str, Any]]:
    """Render evidence totals, text-match counts, and non-empty category counts."""
    stats = db.evidence.evidence_stats()
    total = int(stats["total"])
    rate = f"{stats['verified'] / total:.0%}" if total > 0 else "–"
    ledger_figures = (
        ("Findings", f"{total:,}", ""),
        ("Text match", f"{int(stats['verified']):,}", ""),
        ("Unverified", f"{int(stats['unverified']):,}", " is-caution" if stats["unverified"] else ""),
        ("Match rate", rate, ""),
    )
    st.markdown(
        "<dl class='ledger-figures'>"
        + "".join(f"<div><dt>{label}</dt><dd class='{css.strip()}'>{value}</dd></div>" for label, value, css in ledger_figures)
        + "</dl>",
        unsafe_allow_html=True,
    )
    st.caption("A text match follows the stored quote normalization. It confirms the words, not the analyst's conclusion.")

    categories = db.evidence.evidence_categories()
    cats_with_items = [category for category in categories if category["count"] > 0]
    if len(cats_with_items) > 1:
        from . import figures

        st.markdown("<h3>By category</h3>", unsafe_allow_html=True)
        figures.show(figures.ranked_bars(cats_with_items, label="category", value="count", value_title="Findings"))

    return categories


def _select_evidence_items(
    db: ArchiveDatabase, categories: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int, str | None, int]:
    """Collect evidence filters and run text search or filtered listing accordingly."""
    st.markdown("<h2 class='ledger-heading'>Findings</h2>", unsafe_allow_html=True)
    browse_col1, browse_col2, browse_col3 = st.columns([1, 1, 1.4])

    with browse_col1:
        all_categories = ["All"] + [category["category"] for category in categories]
        selected_cat = st.selectbox(
            "Category", all_categories, index=0, format_func=lambda value: "All categories" if value == "All" else value
        )

    with browse_col2:
        min_rel = st.selectbox("Minimum relevance", [1, 2, 3, 4, 5], index=0, format_func=relevance_label)

    with browse_col3:
        text_filter = st.text_input("Search findings", placeholder="Words in quotes, summaries or notes")

    cat_filter = None if selected_cat == "All" else selected_cat
    rel_filter = min_rel if min_rel > 1 else None

    if text_filter.strip():
        result = db.evidence.search_evidence(query=text_filter.strip(), category=cat_filter, min_relevance=rel_filter, limit=100)
    else:
        result = db.evidence.list_evidence(category=cat_filter, min_relevance=rel_filter, limit=100)
    return result["items"], result["total"], cat_filter, int(min_rel)


def _render_evidence_items(items: list[dict[str, Any]], total: int) -> None:
    """Render each finding as a ledger entry: register, source, exact quote, interpretation."""
    if not items:
        st.markdown(
            "<div class='ledger-empty'><strong>No findings here yet.</strong>"
            "Open a stored message on Inspect and choose Capture finding. Findings you save appear in this ledger "
            "with their quote and source.</div>",
            unsafe_allow_html=True,
        )
        return
    shown = f"{len(items)} of {total}" if total > len(items) else f"{total}"
    st.caption(f"{shown} {'finding' if total == 1 else 'findings'}, newest first")
    st.markdown("".join(_evidence_entry_html(item) for item in items), unsafe_allow_html=True)


def _evidence_entry_html(item: dict[str, Any]) -> str:
    """Build one escaped ledger entry; status is stated in words as well as color."""
    verified = bool(item.get("verified"))
    status_class = "evidence-status" if verified else "evidence-status is-unmatched"
    status = "text match" if verified else "unverified"
    sender = str(item.get("sender_name") or item.get("sender_email") or "Unknown sender")
    sender_email = str(item.get("sender_email") or "")
    source_line = html_escape(sender)
    if sender_email and sender_email != sender:
        source_line += f" &lt;{html_escape(sender_email)}&gt;"
    quote = str(item.get("key_quote") or "")
    summary = str(item.get("summary") or "")
    notes = str(item.get("notes") or "")
    register = (
        f"<span class='evidence-id'>F-{int(item['id']):04d}</span>"
        f"<span>{html_escape(str(item.get('date') or '')[:10])}</span>"
        f"<span class='category-tag'>{html_escape(str(item.get('category') or 'uncategorized'))}</span>"
        f"<span>{html_escape(relevance_label(item.get('relevance')))}</span>"
        f"<span class='{status_class}'>{status}</span>"
    )
    body = (
        f"<h3>{html_escape(str(item.get('subject') or '(no subject)'))}</h3>"
        f"<p class='evidence-entry-source'>{source_line}</p>"
        f"<blockquote class='evidence-quote{'' if verified else ' is-unmatched'}'>{html_escape(quote)}</blockquote>"
        + (f"<p><b>Why it matters</b> · {html_escape(summary)}</p>" if summary else "")
        + (f"<p><b>Notes</b> · {html_escape(notes)}</p>" if notes else "")
        + "<p class='evidence-meta'>"
        f"Message UID {html_escape(str(item.get('email_uid') or ''))}"
        + (f" · To {html_escape(str(item.get('recipients')))}" if item.get("recipients") else "")
        + "</p>"
    )
    return (
        f"<article class='evidence-entry'><div class='evidence-entry-register'>{register}</div>"
        f"<div class='evidence-entry-body'>{body}</div></article>"
    )


def _render_export_handoff(category: str | None, min_relevance: int, has_items: bool) -> None:
    """Carry the ledger's filters into Export, where the report is previewed before it is prepared."""
    if not has_items:
        return
    if st.button("Prepare a report for this category and relevance", type="primary", key="evidence-export-handoff"):
        for key in ("evidence-export-category", "evidence-export-relevance"):
            st.session_state.pop(key, None)
        draft = dict(st.session_state.get("web_evidence_export_draft", {}))
        draft.update({"category": category, "min_relevance": min_relevance})
        st.session_state["web_evidence_export_draft"] = draft
        st.session_state.pop("web_evidence_export", None)
        st.session_state["web_route"] = "Export"
        st.rerun()
