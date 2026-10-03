"""Altair figures drawn in the Marginalia palette.

Derived data is the machine's voice: charts use ink and graphite only, never the
analyst's cinnabar, and carry their numbers in the monospace face.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

_PALETTES = {
    "night": {"ink": "#ede7db", "ink3": "#a0988a", "rule": "#36332d", "mark": "#c6beae", "low": "#25231f"},
    "day": {"ink": "#1c1a16", "ink3": "#665f53", "rule": "#dcd5c6", "mark": "#47433b", "low": "#ece7dc"},
}
_MONO = "PT Mono, Menlo, Consolas, monospace"
_UI = "Seravek, Gill Sans Nova, Segoe UI, sans-serif"


def _palette() -> dict[str, str]:
    return _PALETTES.get(str(st.session_state.get("web_theme", "night")), _PALETTES["night"])


def _configure(chart: Any, height: Any) -> Any:
    colors = _palette()
    return (
        chart.properties(height=height, width="container")
        .configure(background="transparent", font=_UI)
        .configure_view(stroke=None)
        .configure_axis(
            labelColor=colors["ink3"],
            titleColor=colors["ink3"],
            labelFont=_MONO,
            titleFont=_MONO,
            labelFontSize=11,
            titleFontSize=11,
            titleFontWeight="normal",
            gridColor=colors["rule"],
            domainColor=colors["rule"],
            tickColor=colors["rule"],
        )
        .configure_legend(labelColor=colors["ink3"], titleColor=colors["ink3"], labelFont=_MONO, titleFont=_MONO)
    )


def show(chart: Any) -> None:
    """Render a configured figure without Streamlit's own chart theme."""
    st.altair_chart(chart, theme=None, width="stretch")


def volume_bars(rows: list[dict[str, Any]], *, x: str, y: str, x_title: str, y_title: str) -> Any:
    """Counts per period as thin bars: honest about discrete periods."""
    import altair as alt

    colors = _palette()
    chart = (
        alt.Chart(alt.Data(values=rows))
        .mark_bar(color=colors["mark"], size=14)
        .encode(
            x=alt.X(f"{x}:O", title=x_title, axis=alt.Axis(labelAngle=0, labelOverlap="greedy")),
            y=alt.Y(f"{y}:Q", title=y_title, axis=alt.Axis(tickCount=4, format="d", tickMinStep=1)),
            tooltip=[alt.Tooltip(f"{x}:O", title=x_title), alt.Tooltip(f"{y}:Q", title=y_title)],
        )
    )
    return _configure(chart, 220)


def ranked_bars(rows: list[dict[str, Any]], *, label: str, value: str, value_title: str) -> Any:
    """Horizontal bars ordered by value, labelled on the axis."""
    import altair as alt

    colors = _palette()
    chart = (
        alt.Chart(alt.Data(values=rows))
        .mark_bar(color=colors["mark"], height=12)
        .encode(
            y=alt.Y(
                f"{label}:N",
                sort="-x",
                title=None,
                axis=alt.Axis(labelFont=_UI, labelFontSize=13, labelLimit=260, labelColor=colors["ink"]),
            ),
            x=alt.X(f"{value}:Q", title=value_title, axis=alt.Axis(tickCount=4, format="d", tickMinStep=1)),
            tooltip=[alt.Tooltip(f"{label}:N"), alt.Tooltip(f"{value}:Q", title=value_title)],
        )
    )
    return _configure(chart, alt.Step(30))


def _legend_values(grid: list[list[int]]) -> list[int]:
    """Whole-number legend stops, so small archives never show repeated labels."""
    peak = max((max(row) for row in grid), default=0)
    step = max(1, -(-peak // 4))
    return list(range(0, peak + 1, step)) or [0]


def activity_grid(grid: list[list[int]]) -> Any:
    """A 7 x 24 weekday-by-hour grid in one graphite ramp."""
    import altair as alt

    colors = _palette()
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    values = [{"day": days[d], "hour": f"{h:02d}", "messages": grid[d][h]} for d in range(7) for h in range(24)]
    chart = (
        alt.Chart(alt.Data(values=values))
        .mark_rect()
        .encode(
            x=alt.X("hour:O", title="Hour", axis=alt.Axis(labelAngle=0, values=[f"{h:02d}" for h in range(0, 24, 3)])),
            y=alt.Y("day:O", title=None, sort=days),
            color=alt.Color(
                "messages:Q",
                title="Messages",
                scale=alt.Scale(range=[colors["low"], colors["ink"]]),
                legend=alt.Legend(format="d", values=_legend_values(grid), gradientLength=120),
            ),
            tooltip=["day:O", "hour:O", "messages:Q"],
        )
    )
    return _configure(chart, 210)
