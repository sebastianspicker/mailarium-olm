"""Evidence collection page helpers for the Streamlit app."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import streamlit as st

from .results import type_badge_html

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase


def _relevance_badge_html(relevance: int) -> str:
    """Generate HTML for a relevance badge with color coding and star rating."""
    relevance = max(1, min(5, relevance))
    rel_colors = {
        5: ("#2f6b46", "rgba(47,107,70,0.11)"),
        4: ("#2f6b46", "rgba(47,107,70,0.11)"),
        3: ("#7a5305", "rgba(122,83,5,0.10)"),
        2: ("#6f6649", "rgba(111,102,73,0.10)"),
        1: ("#6f6649", "rgba(111,102,73,0.10)"),
    }
    rel_labels = {5: "CRITICAL", 4: "STRONG", 3: "SUPPORTING", 2: "BACKGROUND", 1: "TANGENTIAL"}
    color, bg = rel_colors.get(relevance, ("#6f6649", "rgba(111,102,73,0.10)"))
    label = rel_labels.get(relevance, str(relevance))
    stars = "\u2605" * relevance + "\u2606" * (5 - relevance)
    return (
        f"<span style='display:inline-block;padding:0.15rem 0.5rem;border-radius:6px;"
        f"background:{bg};color:{color};font-size:0.75rem;font-weight:600;"
        f'font-family:"SF Mono","Fira Code",monospace;\'>'
        f"{stars} {label}</span>"
    )


def _verified_badge_html(verified: bool) -> str:
    """Generate HTML for a verification status badge."""
    if verified:
        return (
            "<span style='display:inline-block;padding:0.12rem 0.45rem;border-radius:6px;"
            "background:rgba(47,107,70,0.11);color:#2f6b46;font-size:0.72rem;font-weight:600;"
            "letter-spacing:0.04em;'>TEXT MATCH</span>"
        )
    return (
        "<span style='display:inline-block;padding:0.12rem 0.45rem;border-radius:6px;"
        "background:rgba(122,83,5,0.10);color:#7a5305;font-size:0.72rem;font-weight:600;"
        "letter-spacing:0.04em;'>UNVERIFIED</span>"
    )


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
        "<span class='page-note'>Collection is provisional until the source and custody record are reviewed.</span></div>",
        unsafe_allow_html=True,
    )
    st.info(
        "Capture findings from Inspect, browse saved evidence here, or prepare HTML/CSV reports in Export. "
        "Use the CLI or MCP evidence tools for repeatable workflows, custody checks, "
        "dossier generation, and PDF export."
    )

    if database is None:
        st.warning("SQLite database not available. Run ingestion first to enable evidence management.")
        return

    categories = _render_evidence_overview(database)
    items, total, cat_filter = _select_evidence_items(database, categories)
    _render_evidence_items(items, total)
    _render_evidence_export(database, cat_filter)


def _render_evidence_overview(db: ArchiveDatabase) -> list[dict[str, Any]]:
    """Render evidence totals, verification rate, and non-empty category counts."""
    import pandas as pd

    stats = db.evidence.evidence_stats()
    met_col1, met_col2, met_col3, met_col4 = st.columns(4)
    met_col1.metric("Total Items", stats["total"])
    met_col2.metric("Text matches", stats["verified"])
    met_col3.metric("Unverified", stats["unverified"])
    verified_pct = f"{stats['verified'] / stats['total']:.0%}" if stats["total"] > 0 else "N/A"
    met_col4.metric("Text-match rate", verified_pct)

    st.caption("Text matching follows stored quote normalization; it does not verify an analyst conclusion.")

    categories = db.evidence.evidence_categories()
    cats_with_items = [category for category in categories if category["count"] > 0]
    if cats_with_items:
        st.subheader("Items by Category")
        df_cats = pd.DataFrame(cats_with_items)
        st.bar_chart(df_cats, x="category", y="count")

    return categories


def _select_evidence_items(db: ArchiveDatabase, categories: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int, str | None]:
    """Collect evidence filters and run text search or filtered listing accordingly."""
    st.divider()
    st.subheader("Browse Evidence")
    browse_col1, browse_col2, browse_col3 = st.columns(3)

    with browse_col1:
        all_categories = ["All"] + [category["category"] for category in categories]
        selected_cat = st.selectbox("Category", all_categories, index=0)

    with browse_col2:
        min_rel = st.slider("Min Relevance", min_value=1, max_value=5, value=1)

    with browse_col3:
        text_filter = st.text_input("Text search", placeholder="Search quotes, summaries, notes...")

    cat_filter = None if selected_cat == "All" else selected_cat
    rel_filter = min_rel if min_rel > 1 else None

    if text_filter.strip():
        result = db.evidence.search_evidence(query=text_filter.strip(), category=cat_filter, min_relevance=rel_filter, limit=100)
        items = result["items"]
        total = result["total"]
    else:
        result = db.evidence.list_evidence(category=cat_filter, min_relevance=rel_filter, limit=100)
        items = result["items"]
        total = result["total"]

    return items, total, cat_filter


def _render_evidence_items(items: list[dict[str, Any]], total: int) -> None:
    """Render escaped evidence details, verification badges, and provenance fields."""
    st.caption(f"Showing {len(items)} of {total} items")

    if not items:
        st.info(
            "No evidence items found. Open a stored source in Inspect and choose Capture finding to start collecting evidence."
        )
    else:
        from html import escape as html_escape

        for item in items:
            relevance = item.get("relevance", 0)
            verified = bool(item.get("verified"))
            date_short = str(item.get("date", ""))[:10]
            category = item.get("category", "general")
            sender_name = item.get("sender_name", "")
            subject = item.get("subject", "(no subject)")

            with st.expander(
                f"{category.upper()} | "
                + "\u2605" * relevance
                + "\u2606" * (5 - relevance)
                + f" | {'TEXT MATCH' if verified else 'UNVERIFIED'} | "
                f"{sender_name} | {date_short} -- {subject}",
                expanded=False,
            ):
                badges = _relevance_badge_html(relevance)
                badges += " " + _verified_badge_html(verified)
                badges += " " + type_badge_html(None)
                badges += (
                    f" <span style='display:inline-block;padding:0.12rem 0.45rem;border-radius:6px;"
                    f"background:rgba(216,180,254,0.16);color:#d8b4fe;font-size:0.72rem;font-weight:600;"
                    f"text-transform:uppercase;letter-spacing:0.04em;'>{html_escape(category)}</span>"
                )
                st.markdown(badges, unsafe_allow_html=True)

                ev_col1, ev_col2, ev_col3 = st.columns(3)
                with ev_col1:
                    sender_display_ev = html_escape(sender_name or item.get("sender_email", ""))
                    st.markdown(
                        f"<div class='email-field'><strong>From:</strong> {sender_display_ev}</div>",
                        unsafe_allow_html=True,
                    )
                with ev_col2:
                    st.markdown(
                        f"<div class='email-field'><strong>Date:</strong> {html_escape(date_short)}</div>",
                        unsafe_allow_html=True,
                    )
                with ev_col3:
                    st.markdown(
                        f"<div class='email-field'><strong>Subject:</strong> {html_escape(str(subject))}</div>",
                        unsafe_allow_html=True,
                    )

                quote = item.get("key_quote", "")
                if quote:
                    st.markdown(
                        f"<div class='evidence-quote'><strong>Quote:</strong> <em>\"{html_escape(quote)}\"</em></div>",
                        unsafe_allow_html=True,
                    )

                summary = item.get("summary", "")
                if summary:
                    st.markdown(f"**Summary:** {html_escape(summary)}")

                if item.get("notes"):
                    st.markdown(f"**Notes:** {html_escape(item['notes'])}")

                st.caption(
                    f"Evidence ID: {item['id']} | "
                    f"Email UID: {item.get('email_uid', '')} | "
                    f"Sender: {item.get('sender_email', '')} | "
                    f"Recipients: {item.get('recipients', '')}"
                )


def _render_evidence_export(db: ArchiveDatabase, cat_filter: str | None) -> None:
    """Generate filtered HTML or CSV evidence and expose the matching download."""
    st.divider()
    st.subheader("Export Evidence")
    export_col1, export_col2 = st.columns(2)

    with export_col1:
        export_format = st.selectbox("Format", ["html", "csv"], index=0)

    with export_col2:
        export_min_rel = st.selectbox("Min Relevance for Export", [1, 2, 3, 4, 5], index=0)

    if st.button("Generate Export"):
        from mailarium.investigation.evidence_exporter import EvidenceExporter

        exporter = EvidenceExporter(db)
        export_min_rel_val: int | None = export_min_rel if export_min_rel > 1 else None
        if export_format == "csv":
            export_result = exporter.export_csv(min_relevance=export_min_rel_val, category=cat_filter)
        else:
            export_result = exporter.export_html(min_relevance=export_min_rel_val, category=cat_filter)

        if export_format == "html" and "html" in export_result:
            st.download_button(
                label="Download HTML Report",
                data=export_result["html"],
                file_name="evidence_report.html",
                mime="text/html",
            )
        elif export_format == "csv" and "csv" in export_result:
            st.download_button(
                label="Download CSV",
                data=export_result["csv"],
                file_name="evidence_report.csv",
                mime="text/csv",
            )
