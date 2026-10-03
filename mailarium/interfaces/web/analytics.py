"""Page controller helpers for the Streamlit app."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import streamlit as st

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase


def render_dashboard_page(*, database: ArchiveDatabase | None) -> None:
    """Render the dashboard page implementation with analytics and charts."""
    st.markdown(
        "<div class='page-heading'><h1>The archive at a glance</h1>"
        "<span class='page-note'>Derived views remain aids to review, not source evidence.</span></div>",
        unsafe_allow_html=True,
    )

    if database is None:
        st.warning("SQLite database not available. Run ingestion first to enable analytics.")
        return

    import pandas as pd

    from mailarium.investigation.temporal_analysis import TemporalAnalyzer

    from .charts import prepare_heatmap_data, prepare_response_times_data, prepare_volume_chart_data

    analyzer = TemporalAnalyzer(database)

    st.subheader("Email Volume Over Time")
    period = st.selectbox("Period", ["day", "week", "month"], index=2)
    volume_data = prepare_volume_chart_data(analyzer, period=period)
    if volume_data:
        df = pd.DataFrame(volume_data)
        st.line_chart(df, x="period", y="count")
    else:
        st.info("No volume data available.")

    st.subheader("Activity Heatmap (hour × day-of-week)")
    heatmap_grid = prepare_heatmap_data(analyzer)
    if any(any(row) for row in heatmap_grid):
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        hour_columns = [f"{hour:02d}" for hour in range(24)]
        df_heat = pd.DataFrame(heatmap_grid, index=cast(Any, days), columns=cast(Any, hour_columns))
        st.dataframe(df_heat, use_container_width=True)
    else:
        st.info("No activity data available.")

    st.subheader("Top Contacts")
    email_input = st.text_input("Your email address", placeholder="you@example.com")
    if email_input:
        contacts = database.analytics.top_contacts(email_input, limit=15)
        if contacts:
            df_contacts = pd.DataFrame(contacts)
            st.bar_chart(df_contacts, x="partner", y="total")
        else:
            st.info(f"No contacts found for {email_input}")

    st.subheader("Response Times")
    st.caption("Based on up to the 500 most recent canonical reply pairs.")
    resp_data = prepare_response_times_data(analyzer, limit=15)
    if resp_data:
        df_resp = pd.DataFrame(resp_data)
        st.dataframe(df_resp, use_container_width=True)
    else:
        st.info("No response time data available.")


def render_entity_page(*, database: ArchiveDatabase | None) -> None:
    """Render the entity browser page implementation."""
    st.markdown(
        "<div class='page-heading'><h1>People &amp; names</h1>"
        "<span class='page-note'>Entities are extracted aids; verify each name against its message.</span></div>",
        unsafe_allow_html=True,
    )

    if database is None:
        st.warning("SQLite database not available. Run ingestion with `--extract-entities` first.")
        return

    import pandas as pd

    entity_types = ["All", "organization", "person", "url", "phone", "email", "event"]
    selected_type = st.selectbox("Entity Type", entity_types, index=0)
    entity_type = None if selected_type == "All" else selected_type

    entities = database.entities.top_entities(entity_type=entity_type, limit=30)
    if entities:
        df = pd.DataFrame(entities)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No entities found. Run ingestion with `--extract-entities` to populate.")

    st.subheader("Entity Co-occurrences")
    entity_query = st.text_input("Find co-occurring entities for:", placeholder="Acme Corp")
    if entity_query:
        co_entities = database.entities.entity_co_occurrences(entity_query, limit=20)
        if co_entities:
            df_co = pd.DataFrame(co_entities)
            st.dataframe(df_co, use_container_width=True)
        else:
            st.info(f"No co-occurrences found for '{entity_query}'")


def render_network_page(*, database: ArchiveDatabase | None) -> None:
    """Render the communication network page implementation."""
    st.markdown(
        "<div class='page-heading'><h1>The web of correspondence</h1>"
        "<span class='page-note'>Relationships are derived from retained archive records.</span></div>",
        unsafe_allow_html=True,
    )

    if database is None:
        st.warning("SQLite database not available. Run ingestion first.")
        return

    from .charts import prepare_network_summary

    net_data = prepare_network_summary(database, top_n=20)

    if "error" in net_data:
        st.warning(net_data["error"])
        return

    met_col1, met_col2 = st.columns(2)
    met_col1.metric("Total Nodes", net_data.get("total_nodes", 0))
    met_col2.metric("Total Edges", net_data.get("total_edges", 0))

    most_connected = net_data.get("most_connected", [])
    if most_connected:
        import pandas as pd

        st.subheader("Most Connected")
        df_mc = pd.DataFrame(most_connected)
        st.dataframe(df_mc, use_container_width=True)

    communities = net_data.get("communities", [])
    if communities:
        st.subheader(f"Communities ({len(communities)})")
        for idx, community in enumerate(communities[:10]):
            members = community.get("members", [])
            with st.expander(f"Community {idx + 1} ({len(members)} members)"):
                for member in members[:20]:
                    st.text(member)


__all__ = [
    "render_dashboard_page",
    "render_entity_page",
    "render_network_page",
]
