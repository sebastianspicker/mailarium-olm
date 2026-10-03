"""Pure data-preparation helpers for the Streamlit dashboard pages.

All functions return DataFrames or dicts suitable for charting.
No Streamlit imports - keeps these testable with plain pytest.
"""

from __future__ import annotations

import logging
import threading
import weakref
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase
    from mailarium.investigation.temporal_analysis import TemporalAnalyzer

logger = logging.getLogger(__name__)


@dataclass
class _NetworkCacheEntry:
    revision: tuple[int, int]
    summaries: dict[int, dict[str, Any]]


_NETWORK_CACHE: weakref.WeakKeyDictionary[Any, _NetworkCacheEntry] = weakref.WeakKeyDictionary()
_NETWORK_CACHE_LOCK = threading.Lock()


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


def prepare_response_times_data(
    analyzer: TemporalAnalyzer,
    limit: int = 15,
) -> list[dict[str, Any]]:
    """Get response time data for display.

    Returns list of {"replier": "…", "avg_response_hours": 2.5, "response_count": 10}
    from the recent canonical-reply sample used by TemporalAnalyzer.
    """
    return analyzer.response_times(limit=limit)


def prepare_network_summary(db: ArchiveDatabase, top_n: int = 20) -> dict[str, Any]:
    """Get network analysis summary for the network page.

    Returns dict with nodes, edges, most_connected, communities.
    """
    try:
        from mailarium.investigation.network_analysis import CommunicationNetwork

        with db.operation():
            revision = db.change_revision()
            with _NETWORK_CACHE_LOCK:
                entry = _NETWORK_CACHE.get(db)
                if entry is None or entry.revision != revision:
                    entry = _NetworkCacheEntry(revision, {})
                    _NETWORK_CACHE[db] = entry
                cached = entry.summaries.get(top_n)
                if cached is not None:
                    return cached
            summary = CommunicationNetwork(db).network_analysis(top_n=top_n)
            with _NETWORK_CACHE_LOCK:
                current = _NETWORK_CACHE.get(db)
                if current is not None and current.revision == revision:
                    return current.summaries.setdefault(top_n, summary)
            return summary
    except Exception:
        logger.debug("Network analysis failed", exc_info=True)
        return {"error": "Network analysis unavailable"}
