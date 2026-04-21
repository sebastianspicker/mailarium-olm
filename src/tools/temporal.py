"""Temporal analysis MCP tools."""

from __future__ import annotations

from typing import Any

from ..mcp_models import EmailTemporalInput
from .utils import ToolDepsProto, json_error, json_response, run_with_db


def register(mcp: Any, deps: ToolDepsProto) -> None:
    """Register temporal analysis tools."""

    @mcp.tool(name="email_temporal", annotations=deps.tool_annotations("Temporal Email Analysis"))
    async def email_temporal(params: EmailTemporalInput) -> str:
        """Temporal analysis: volume trends, activity heatmap, or response times.

        analysis='volume': email volume grouped by day/week/month.
        analysis='activity': hour-of-day x day-of-week heatmap.
        analysis='response_times': average response times per sender.
        """

        def _work(db: Any) -> str:
            from ..temporal_analysis import TemporalAnalyzer

            analyzer = TemporalAnalyzer(db)
            if params.analysis == "volume":
                return json_response(
                    analyzer.volume_over_time(
                        period=params.period,
                        date_from=params.date_from,
                        date_to=params.date_to,
                        sender=params.sender,
                    )
                )
            if params.analysis == "activity":
                return json_response(analyzer.activity_heatmap())
            if params.analysis == "response_times":
                return json_response(
                    analyzer.response_times(
                        sender=params.sender,
                        limit=params.limit,
                    )
                )
            return json_error(f"Invalid analysis: {params.analysis}. Use 'volume', 'activity', or 'response_times'.")

        return await run_with_db(deps, _work)
