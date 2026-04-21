"""Page controller helpers for the Streamlit app."""

from __future__ import annotations

from typing import Any, cast

from .mcp_models_base import _resolve_local_path


def get_email_db_safe_impl(sqlite_path: str | None = None) -> Any | None:
    try:
        from .config import get_settings
        from .email_db import EmailDatabase
    except ImportError:
        from src.config import get_settings
        from src.email_db import EmailDatabase

    settings = get_settings()
    db_path = sqlite_path or settings.sqlite_path
    if db_path:
        try:
            resolved_path = _resolve_local_path(db_path, field_name="SQLite path")
        except ValueError:
            return None
        if resolved_path is not None and resolved_path.exists():
            try:
                return EmailDatabase(str(resolved_path))
            except (OSError, RuntimeError, ValueError):
                return None
    return None


def render_dashboard_page_impl(*, st_module: Any, get_email_db_safe_fn: Any) -> None:
    st_module.markdown("## Analytics Dashboard")

    db = get_email_db_safe_fn()
    if db is None:
        st_module.warning("SQLite database not available. Run ingestion first to enable analytics.")
        return

    try:
        from .dashboard_charts import prepare_heatmap_data, prepare_response_times_data, prepare_volume_chart_data
        from .temporal_analysis import TemporalAnalyzer
    except ImportError:
        from src.dashboard_charts import prepare_heatmap_data, prepare_response_times_data, prepare_volume_chart_data
        from src.temporal_analysis import TemporalAnalyzer

    import pandas as pd

    analyzer = TemporalAnalyzer(db)

    st_module.subheader("Email Volume Over Time")
    period = st_module.selectbox("Period", ["day", "week", "month"], index=2)
    volume_data = prepare_volume_chart_data(analyzer, period=period)
    if volume_data:
        df = pd.DataFrame(volume_data)
        st_module.line_chart(df, x="period", y="count")
    else:
        st_module.info("No volume data available.")

    st_module.subheader("Activity Heatmap (hour × day-of-week)")
    heatmap_grid = prepare_heatmap_data(analyzer)
    if any(any(row) for row in heatmap_grid):
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        hour_columns = [f"{hour:02d}" for hour in range(24)]
        df_heat = pd.DataFrame(heatmap_grid, index=cast(Any, days), columns=cast(Any, hour_columns))
        st_module.dataframe(df_heat, use_container_width=True)
    else:
        st_module.info("No activity data available.")

    st_module.subheader("Top Contacts")
    email_input = st_module.text_input("Your email address", placeholder="you@example.com")
    if email_input:
        contacts = db.top_contacts(email_input, limit=15)
        if contacts:
            df_contacts = pd.DataFrame(contacts)
            st_module.bar_chart(df_contacts, x="partner", y="total")
        else:
            st_module.info(f"No contacts found for {email_input}")

    st_module.subheader("Response Times")
    st_module.caption("Based on up to the 500 most recent canonical reply pairs.")
    resp_data = prepare_response_times_data(analyzer, limit=15)
    if resp_data:
        df_resp = pd.DataFrame(resp_data)
        st_module.dataframe(df_resp, use_container_width=True)
    else:
        st_module.info("No response time data available.")


def render_entity_page_impl(*, st_module: Any, get_email_db_safe_fn: Any) -> None:
    st_module.markdown("## Entity Browser")

    db = get_email_db_safe_fn()
    if db is None:
        st_module.warning("SQLite database not available. Run ingestion with `--extract-entities` first.")
        return

    import pandas as pd

    entity_types = ["All", "organization", "person", "url", "phone", "email", "event"]
    selected_type = st_module.selectbox("Entity Type", entity_types, index=0)
    entity_type = None if selected_type == "All" else selected_type

    entities = db.top_entities(entity_type=entity_type, limit=30)
    if entities:
        df = pd.DataFrame(entities)
        st_module.dataframe(df, use_container_width=True)
    else:
        st_module.info("No entities found. Run ingestion with `--extract-entities` to populate.")

    st_module.subheader("Entity Co-occurrences")
    entity_query = st_module.text_input("Find co-occurring entities for:", placeholder="Acme Corp")
    if entity_query:
        co_entities = db.entity_co_occurrences(entity_query, limit=20)
        if co_entities:
            df_co = pd.DataFrame(co_entities)
            st_module.dataframe(df_co, use_container_width=True)
        else:
            st_module.info(f"No co-occurrences found for '{entity_query}'")


def render_network_page_impl(*, st_module: Any, get_email_db_safe_fn: Any) -> None:
    st_module.markdown("## Communication Network")

    db = get_email_db_safe_fn()
    if db is None:
        st_module.warning("SQLite database not available. Run ingestion first.")
        return

    try:
        from .dashboard_charts import prepare_network_summary
    except ImportError:
        from src.dashboard_charts import prepare_network_summary

    net_data = prepare_network_summary(db, top_n=20)

    if "error" in net_data:
        st_module.warning(net_data["error"])
        return

    met_col1, met_col2 = st_module.columns(2)
    met_col1.metric("Total Nodes", net_data.get("total_nodes", 0))
    met_col2.metric("Total Edges", net_data.get("total_edges", 0))

    most_connected = net_data.get("most_connected", [])
    if most_connected:
        import pandas as pd

        st_module.subheader("Most Connected")
        df_mc = pd.DataFrame(most_connected)
        st_module.dataframe(df_mc, use_container_width=True)

    communities = net_data.get("communities", [])
    if communities:
        st_module.subheader(f"Communities ({len(communities)})")
        for idx, community in enumerate(communities[:10]):
            members = community.get("members", [])
            with st_module.expander(f"Community {idx + 1} ({len(members)} members)"):
                for member in members[:20]:
                    st_module.text(member)


def _relevance_badge_html(relevance: int) -> str:
    relevance = max(1, min(5, relevance))
    rel_colors = {
        5: ("#065f46", "#d1fae5"),
        4: ("#065f46", "#d1fae5"),
        3: ("#92400e", "#fef3c7"),
        2: ("#78716c", "#f5f5f4"),
        1: ("#78716c", "#f5f5f4"),
    }
    rel_labels = {5: "DIRECT PROOF", 4: "STRONG", 3: "SUPPORTING", 2: "BACKGROUND", 1: "TANGENTIAL"}
    color, bg = rel_colors.get(relevance, ("#78716c", "#f5f5f4"))
    label = rel_labels.get(relevance, str(relevance))
    stars = "\u2605" * relevance + "\u2606" * (5 - relevance)
    return (
        f"<span style='display:inline-block;padding:0.15rem 0.5rem;border-radius:6px;"
        f"background:{bg};color:{color};font-size:0.75rem;font-weight:600;"
        f'font-family:"SF Mono","Fira Code",monospace;\'>'
        f"{stars} {label}</span>"
    )


def _verified_badge_html(verified: bool) -> str:
    if verified:
        return (
            "<span style='display:inline-block;padding:0.12rem 0.45rem;border-radius:6px;"
            "background:#d1fae5;color:#065f46;font-size:0.72rem;font-weight:600;"
            "letter-spacing:0.04em;'>VERIFIED</span>"
        )
    return (
        "<span style='display:inline-block;padding:0.12rem 0.45rem;border-radius:6px;"
        "background:#fef3c7;color:#92400e;font-size:0.72rem;font-weight:600;"
        "letter-spacing:0.04em;'>PENDING</span>"
    )


def render_evidence_page_impl(
    *,
    st_module: Any,
    get_email_db_safe_fn: Any,
    type_badge_html_fn: Any,
) -> None:
    st_module.markdown("## Evidence Collection")
    st_module.info(
        "Exploratory evidence collection only. For authoritative lawyer-ready evidence indexes, chronology, and "
        "counsel-facing matter review, use the MCP legal-support tools. CLI `case full-pack` / `case counsel-pack` "
        "remain local operator wrappers for preparation and exporter checks. Web downloads here stay intentionally "
        "limited to HTML and CSV; use CLI or MCP when you need PDF evidence export."
    )

    db = get_email_db_safe_fn()
    if db is None:
        st_module.warning("SQLite database not available. Run ingestion first to enable evidence management.")
        return

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
                    f"background:#ede9fe;color:#5b21b6;font-size:0.72rem;font-weight:600;"
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
                        f'<div style=\'font-family:"Inter",sans-serif;font-size:0.88rem;line-height:1.55;'
                        f"padding:0.75rem 1rem;background:#fefce8;border-radius:8px;"
                        f"border-left:4px solid #eab308;color:#713f12;'>"
                        f"<strong style='font-style:normal;color:#92400e;'>Quote:</strong> "
                        f'<em>"{html_escape(quote)}"</em></div>',
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

    st_module.divider()
    st_module.subheader("Export Evidence")
    export_col1, export_col2 = st_module.columns(2)

    with export_col1:
        export_format = st_module.selectbox("Format", ["html", "csv"], index=0)

    with export_col2:
        export_min_rel = st_module.selectbox("Min Relevance for Export", [1, 2, 3, 4, 5], index=0)

    if st_module.button("Generate Export"):
        try:
            from .evidence_exporter import EvidenceExporter
        except ImportError:
            from src.evidence_exporter import EvidenceExporter

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
