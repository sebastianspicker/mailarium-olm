"""Page controller helpers for the Streamlit app."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape
from typing import TYPE_CHECKING, Any

import streamlit as st

from .presentation import build_register_table_html

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase

_PERIOD_LABELS = {"day": "By day", "week": "By week", "month": "By month"}


def _heading(title: str, note: str) -> None:
    st.markdown(
        f"<div class='page-heading'><h1>{title}</h1><span class='page-note'>{note}</span></div>",
        unsafe_allow_html=True,
    )


def _section(title: str) -> None:
    st.markdown(f"<h3 class='analysis-heading'>{escape(title)}</h3>", unsafe_allow_html=True)


def _table(rows: Sequence[Mapping[str, Any]], columns: dict[str, str], numeric: tuple[str, ...] = ()) -> None:
    st.markdown(build_register_table_html(rows, columns, numeric), unsafe_allow_html=True)


def _figures(items: tuple[tuple[str, str], ...]) -> None:
    st.markdown(
        "<dl class='ledger-figures'>"
        + "".join(f"<div><dt>{escape(label)}</dt><dd>{escape(value)}</dd></div>" for label, value in items)
        + "</dl>",
        unsafe_allow_html=True,
    )


def render_dashboard_page(*, database: ArchiveDatabase | None) -> None:
    """Render the dashboard page implementation with analytics and charts."""
    _heading("The archive at a glance", "Counts derived from stored messages. Use them to decide where to read, not as findings.")

    if database is None:
        st.warning("The SQLite archive is not available. Run ingestion first to see archive patterns.")
        return

    from mailarium.investigation.temporal_analysis import TemporalAnalyzer

    from . import figures
    from .charts import prepare_heatmap_data, prepare_response_times_data, prepare_volume_chart_data

    analyzer = TemporalAnalyzer(database)

    _section("Messages over time")
    period = st.selectbox("Period", ["day", "week", "month"], index=2, format_func=_PERIOD_LABELS.__getitem__, width=240)
    volume_data = prepare_volume_chart_data(analyzer, period=period)
    if volume_data:
        figures.show(figures.volume_bars(volume_data, x="period", y="count", x_title=period.capitalize(), y_title="Messages"))
    else:
        st.info("No dated messages to count yet.")

    _section("When mail was sent")
    heatmap_grid = prepare_heatmap_data(analyzer)
    if any(any(row) for row in heatmap_grid):
        figures.show(figures.activity_grid(heatmap_grid))
        st.caption("Weekday and hour as recorded in the stored message timestamps.")
    else:
        st.info("No timestamps are available for an activity pattern.")

    _section("Most frequent correspondents")
    email_input = st.text_input("Measure from this address", placeholder="you@example.com", width=480)
    if email_input:
        contacts = database.analytics.top_contacts(email_input, limit=15)
        if contacts:
            figures.show(figures.ranked_bars(contacts, label="partner", value="total", value_title="Messages exchanged"))
        else:
            st.info(f"No correspondence recorded for {email_input}. Check the address as it appears in the archive.")
    else:
        st.caption("Enter an address as it appears in the archive to rank the people it exchanged mail with.")

    _section("Response times")
    st.caption("Sampled from up to the 500 most recent canonical reply pairs.")
    resp_data = prepare_response_times_data(analyzer, limit=15)
    if resp_data:
        _table(
            resp_data,
            {"replier": "Replier", "avg_response_hours": "Average hours", "response_count": "Replies"},
            numeric=("avg_response_hours", "response_count"),
        )
    else:
        st.info("No canonical reply pairs were found, so response times cannot be measured.")


def render_entity_page(*, database: ArchiveDatabase | None) -> None:
    """Render the entity browser page implementation."""
    _heading("People &amp; names", "Extracted automatically. Confirm each name against the message it came from.")

    if database is None:
        st.warning("The SQLite archive is not available. Run ingestion with --extract-entities first.")
        return

    entity_types = ["All", "organization", "person", "url", "phone", "email", "event"]
    selected_type = st.selectbox(
        "Entity type",
        entity_types,
        index=0,
        format_func=lambda value: "All types" if value == "All" else value.capitalize(),
        width=320,
    )
    entity_type = None if selected_type == "All" else selected_type

    entities = database.entities.top_entities(entity_type=entity_type, limit=30)
    if entities:
        _table(
            entities,
            {"entity_text": "Name", "entity_type": "Type", "email_count": "Messages", "total_mentions": "Mentions"},
            numeric=("email_count", "total_mentions"),
        )
    else:
        st.info("No entities were extracted. Run ingestion with --extract-entities to populate this page.")

    _section("Named together")
    entity_query = st.text_input("Names that appear with", placeholder="Acme Corp", width=480)
    if entity_query:
        co_entities = database.entities.entity_co_occurrences(entity_query, limit=20)
        if co_entities:
            _table(
                co_entities,
                {"entity_text": "Name", "entity_type": "Type", "co_occurrence_count": "Shared messages"},
                numeric=("co_occurrence_count",),
            )
        else:
            st.info(f"Nothing is recorded alongside '{entity_query}'. Try the name as it is spelled in the messages.")


def render_network_page(*, database: ArchiveDatabase | None) -> None:
    """Render the communication network page implementation."""
    _heading("The web of correspondence", "Who wrote to whom, derived from sender and recipient fields in retained messages.")

    if database is None:
        st.warning("The SQLite archive is not available. Run ingestion first.")
        return

    from .charts import prepare_network_summary

    net_data = prepare_network_summary(database, top_n=20)

    if "error" in net_data:
        st.warning("The correspondence network could not be computed for this archive.")
        return

    _figures(
        (
            ("Addresses", f"{int(net_data.get('total_nodes', 0)):,}"),
            ("Connections", f"{int(net_data.get('total_edges', 0)):,}"),
            ("Groups", f"{len(net_data.get('communities', [])):,}"),
        )
    )

    most_connected = net_data.get("most_connected", [])
    if most_connected:
        _section("Most connected")
        _table(most_connected, {"email": "Address", "centrality": "Centrality"}, numeric=("centrality",))

    communities = net_data.get("communities", [])
    if communities:
        _section("Groups that write to each other")
        for idx, community in enumerate(communities[:10]):
            members = community.get("members", [])
            with st.expander(f"Group {idx + 1} · {len(members)} {'address' if len(members) == 1 else 'addresses'}"):
                st.markdown(
                    "<ul class='member-list'>" + "".join(f"<li>{escape(str(member))}</li>" for member in members[:20]) + "</ul>",
                    unsafe_allow_html=True,
                )
                if len(members) > 20:
                    st.caption(f"Showing 20 of {len(members)} addresses.")


__all__ = [
    "render_dashboard_page",
    "render_entity_page",
    "render_network_page",
]
