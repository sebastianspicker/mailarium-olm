"""Pure data-preparation helpers for the Streamlit dashboard pages.

All functions return DataFrames or dicts suitable for charting.
No Streamlit imports — keeps these testable with plain pytest.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .email_db import EmailDatabase
    from .temporal_analysis import TemporalAnalyzer

logger = logging.getLogger(__name__)


def prepare_volume_chart_data(
    analyzer: TemporalAnalyzer,
    period: str = "day",
    date_from: str | None = None,
    date_to: str | None = None,
    sender: str | None = None,
) -> list[dict[str, Any]]:
    """Get volume-over-time data ready for charting.

    Returns list of {"period": "2024-01-15", "count": 42}.
    """
    return analyzer.volume_over_time(
        period=period,
        date_from=date_from,
        date_to=date_to,
        sender=sender,
    )


def prepare_heatmap_data(analyzer: TemporalAnalyzer) -> list[list[int]]:
    """Prepare a 7×24 grid (day_of_week × hour) for heatmap rendering.

    Returns a list of 7 rows (Mon-Sun), each with 24 hourly counts.
    """
    raw = analyzer.activity_heatmap()
    # Initialize 7 rows × 24 columns
    grid = [[0] * 24 for _ in range(7)]
    for entry in raw:
        day = entry["day_of_week"]  # 0=Mon
        hour = entry["hour"]
        if 0 <= day < 7 and 0 <= hour < 24:
            grid[day][hour] = entry["count"]
    return grid


def prepare_contacts_chart_data(
    db: EmailDatabase,
    email_address: str,
    limit: int = 15,
) -> list[dict[str, Any]]:
    """Get top contacts data for bar charting.

    Returns list of {"partner": "alice@…", "total_count": 42}.
    """
    return db.top_contacts(email_address, limit=limit)


def prepare_response_times_data(
    analyzer: TemporalAnalyzer,
    limit: int = 15,
) -> list[dict[str, Any]]:
    """Get response time data for display.

    Returns list of {"replier": "…", "avg_response_hours": 2.5, "response_count": 10}.
    """
    return analyzer.response_times(limit=limit)


def prepare_entity_summary(
    db: EmailDatabase,
    entity_type: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Get top entities for the entity browser page.

    Returns list of {"entity_text": "Acme", "entity_type": "organization", "mention_count": 15}.
    """
    return db.top_entities(entity_type=entity_type, limit=limit)


def prepare_network_summary(db: EmailDatabase, top_n: int = 20) -> dict[str, Any]:
    """Get network analysis summary for the network page.

    Returns dict with nodes, edges, most_connected, communities.
    """
    try:
        from .network_analysis import CommunicationNetwork

        net = CommunicationNetwork(db)
        return net.network_analysis(top_n=top_n)
    except Exception:
        logger.debug("Network analysis failed", exc_info=True)
        return {"error": "Network analysis unavailable"}
