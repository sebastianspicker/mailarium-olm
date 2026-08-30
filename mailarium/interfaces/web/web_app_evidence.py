"""Evidence collection page helpers for the Streamlit app."""

from __future__ import annotations

from typing import Any


def _relevance_badge_html(relevance: int) -> str:
    """Generate HTML for a relevance badge with color coding and star rating."""
    relevance = max(1, min(5, relevance))
    rel_colors = {
        5: ("#6ee7b7", "rgba(110,231,183,0.14)"),
        4: ("#6ee7b7", "rgba(110,231,183,0.14)"),
        3: ("#f6cf78", "rgba(246,207,120,0.15)"),
        2: ("#9aa9b6", "rgba(154,169,182,0.12)"),
        1: ("#9aa9b6", "rgba(154,169,182,0.12)"),
    }
    rel_labels = {5: "DIRECT PROOF", 4: "STRONG", 3: "SUPPORTING", 2: "BACKGROUND", 1: "TANGENTIAL"}
    color, bg = rel_colors.get(relevance, ("#9aa9b6", "rgba(154,169,182,0.12)"))
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
            "background:rgba(110,231,183,0.14);color:#6ee7b7;font-size:0.72rem;font-weight:600;"
            "letter-spacing:0.04em;'>VERIFIED</span>"
        )
    return (
        "<span style='display:inline-block;padding:0.12rem 0.45rem;border-radius:6px;"
        "background:rgba(246,207,120,0.15);color:#f6cf78;font-size:0.72rem;font-weight:600;"
        "letter-spacing:0.04em;'>PENDING</span>"
    )


def render_evidence_page_impl(
    *,
    st_module: Any,
    database: Any | None,
    type_badge_html_fn: Any,
) -> None:
    """Render the evidence collection page implementation."""
    st_module.markdown("## Evidence Collection")
    st_module.info(
        "This page supports exploratory evidence collection and HTML/CSV downloads. "
        "Use the CLI or MCP evidence tools for repeatable workflows, custody checks, "
        "dossier generation, and PDF export."
    )

    if database is None:
        st_module.warning("SQLite database not available. Run ingestion first to enable evidence management.")
        return

    categories = _render_evidence_overview(st_module, database)
    items, total, cat_filter = _select_evidence_items(st_module, database, categories)
    _render_evidence_items(st_module, items, total, type_badge_html_fn)
    _render_evidence_export(st_module, database, cat_filter)


def _render_evidence_overview(st_module: Any, db: Any) -> list[dict[str, Any]]:
    """Render evidence totals, verification rate, and non-empty category counts."""
    import pandas as pd

    stats = db.evidence_stats()
    met_col1, met_col2, met_col3, met_col4 = st_module.columns(4)
    met_col1.metric("Total Items", stats["total"])
    met_col2.metric("Verified", stats["verified"])
    met_col3.metric("Unverified", stats["unverified"])
    verified_pct = f"{stats['verified'] / stats['total']:.0%}" if stats["total"] > 0 else "N/A"
    met_col4.metric("Verification Rate", verified_pct)

    categories = db.evidence_categories()
    cats_with_items = [category for category in categories if category["count"] > 0]
    if cats_with_items:
        st_module.subheader("Items by Category")
        df_cats = pd.DataFrame(cats_with_items)
        st_module.bar_chart(df_cats, x="category", y="count")

    return categories


def _select_evidence_items(
    st_module: Any, db: Any, categories: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int, str | None]:
    """Collect evidence filters and run text search or filtered listing accordingly."""
    st_module.divider()
    st_module.subheader("Browse Evidence")
    browse_col1, browse_col2, browse_col3 = st_module.columns(3)

    with browse_col1:
        all_categories = ["All"] + [category["category"] for category in categories]
        selected_cat = st_module.selectbox("Category", all_categories, index=0)

    with browse_col2:
        min_rel = st_module.slider("Min Relevance", min_value=1, max_value=5, value=1)

    with browse_col3:
        text_filter = st_module.text_input("Text search", placeholder="Search quotes, summaries, notes...")

    cat_filter = None if selected_cat == "All" else selected_cat
    rel_filter = min_rel if min_rel > 1 else None

    if text_filter.strip():
        result = db.search_evidence(query=text_filter.strip(), category=cat_filter, min_relevance=rel_filter, limit=100)
        items = result["items"]
        total = result["total"]
    else:
        result = db.list_evidence(category=cat_filter, min_relevance=rel_filter, limit=100)
        items = result["items"]
        total = result["total"]

    return items, total, cat_filter


def _render_evidence_items(st_module: Any, items: list[dict[str, Any]], total: int, type_badge_html_fn: Any) -> None:
    """Render escaped evidence details, verification badges, and provenance fields."""
    st_module.caption(f"Showing {len(items)} of {total} items")

    if not items:
        st_module.info(
            "No evidence items found. Use the `evidence_add` MCP tool from your MCP client to start collecting evidence."
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

            with st_module.expander(
                f"{category.upper()} | "
                + "\u2605" * relevance
                + "\u2606" * (5 - relevance)
                + f" | {'VERIFIED' if verified else 'PENDING'} | "
                f"{sender_name} | {date_short} -- {subject}",
                expanded=False,
            ):
                badges = _relevance_badge_html(relevance)
                badges += " " + _verified_badge_html(verified)
                badges += " " + type_badge_html_fn(None)
                badges += (
                    f" <span style='display:inline-block;padding:0.12rem 0.45rem;border-radius:6px;"
                    f"background:rgba(216,180,254,0.16);color:#d8b4fe;font-size:0.72rem;font-weight:600;"
                    f"text-transform:uppercase;letter-spacing:0.04em;'>{html_escape(category)}</span>"
                )
                st_module.markdown(badges, unsafe_allow_html=True)

                ev_col1, ev_col2, ev_col3 = st_module.columns(3)
                with ev_col1:
                    sender_display_ev = html_escape(sender_name or item.get("sender_email", ""))
                    st_module.markdown(
                        f"<div class='email-field'><strong>From:</strong> {sender_display_ev}</div>",
                        unsafe_allow_html=True,
                    )
                with ev_col2:
                    st_module.markdown(
                        f"<div class='email-field'><strong>Date:</strong> {html_escape(date_short)}</div>",
                        unsafe_allow_html=True,
                    )
                with ev_col3:
                    st_module.markdown(
                        f"<div class='email-field'><strong>Subject:</strong> {html_escape(str(subject))}</div>",
                        unsafe_allow_html=True,
                    )

                quote = item.get("key_quote", "")
                if quote:
                    st_module.markdown(
                        f"<div class='evidence-quote'><strong>Quote:</strong> <em>\"{html_escape(quote)}\"</em></div>",
                        unsafe_allow_html=True,
                    )

                summary = item.get("summary", "")
                if summary:
                    st_module.markdown(f"**Summary:** {html_escape(summary)}")

                if item.get("notes"):
                    st_module.markdown(f"**Notes:** {html_escape(item['notes'])}")

                st_module.caption(
                    f"Evidence ID: {item['id']} | "
                    f"Email UID: {item.get('email_uid', '')} | "
                    f"Sender: {item.get('sender_email', '')} | "
                    f"Recipients: {item.get('recipients', '')}"
                )


def _render_evidence_export(st_module: Any, db: Any, cat_filter: str | None) -> None:
    """Generate filtered HTML or CSV evidence and expose the matching download."""
    st_module.divider()
    st_module.subheader("Export Evidence")
    export_col1, export_col2 = st_module.columns(2)

    with export_col1:
        export_format = st_module.selectbox("Format", ["html", "csv"], index=0)

    with export_col2:
        export_min_rel = st_module.selectbox("Min Relevance for Export", [1, 2, 3, 4, 5], index=0)

    if st_module.button("Generate Export"):
        from mailarium.investigation.evidence_exporter import EvidenceExporter

        exporter = EvidenceExporter(db)
        export_min_rel_val: int | None = export_min_rel if export_min_rel > 1 else None
        if export_format == "csv":
            export_result = exporter.export_csv(min_relevance=export_min_rel_val, category=cat_filter)
        else:
            export_result = exporter.export_html(min_relevance=export_min_rel_val, category=cat_filter)

        if export_format == "html" and "html" in export_result:
            st_module.download_button(
                label="Download HTML Report",
                data=export_result["html"],
                file_name="evidence_report.html",
                mime="text/html",
            )
        elif export_format == "csv" and "csv" in export_result:
            st_module.download_button(
                label="Download CSV",
                data=export_result["csv"],
                file_name="evidence_report.csv",
                mime="text/csv",
            )
