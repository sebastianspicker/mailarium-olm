"""Page controller helpers for the Streamlit app."""
# pylint: disable=too-many-branches,too-many-locals,too-many-statements

from __future__ import annotations

from typing import Any, cast

from .mcp_models_base import _resolve_local_path


def get_email_db_safe_impl(sqlite_path: str | None = None) -> Any | None:
    """Get an EmailDatabase instance safely, returning None if unavailable or invalid."""
    try:
        from .config import get_settings
        from .email_db import EmailDatabase
    except ImportError:
        from mailarium.config import get_settings
        from mailarium.email_db import EmailDatabase

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
            except OSError, RuntimeError, ValueError:
                return None
    return None


def render_dashboard_page_impl(*, st_module: Any, get_email_db_safe_fn: Any) -> None:
    """Render the dashboard page implementation with analytics and charts."""
    st_module.markdown("## Analytics Dashboard")

    db = get_email_db_safe_fn()
    if db is None:
        st_module.warning("SQLite database not available. Run ingestion first to enable analytics.")
        return

    try:
        from .dashboard_charts import prepare_heatmap_data, prepare_response_times_data, prepare_volume_chart_data
        from .temporal_analysis import TemporalAnalyzer
    except ImportError:
        from mailarium.dashboard_charts import prepare_heatmap_data, prepare_response_times_data, prepare_volume_chart_data
        from mailarium.temporal_analysis import TemporalAnalyzer

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
    """Render the entity browser page implementation."""
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
    """Render the communication network page implementation."""
    st_module.markdown("## Communication Network")

    db = get_email_db_safe_fn()
    if db is None:
        st_module.warning("SQLite database not available. Run ingestion first.")
        return

    try:
        from .dashboard_charts import prepare_network_summary
    except ImportError:
        from mailarium.dashboard_charts import prepare_network_summary

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


# Re-export evidence page implementation for backward compatibility.
try:
    from .web_app_evidence import render_evidence_page_impl
except ImportError:  # pragma: no cover
    from mailarium.web_app_evidence import render_evidence_page_impl

__all__ = [
    "get_email_db_safe_impl",
    "render_dashboard_page_impl",
    "render_entity_page_impl",
    "render_evidence_page_impl",
    "render_network_page_impl",
]
