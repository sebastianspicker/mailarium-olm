"""Entity search and NLP entity MCP tools."""

from __future__ import annotations

from typing import Any

from ..mcp_models import (
    EntityNetworkInput,
    EntitySearchInput,
    EntityTimelineInput,
    ListEntitiesInput,
)
from .utils import ToolDepsProto, json_response, run_with_db


def register(mcp: Any, deps: ToolDepsProto) -> None:
    """Register entity tools."""

    @mcp.tool(name="email_search_by_entity", annotations=deps.tool_annotations("Search by Entity"))
    async def email_search_by_entity(params: EntitySearchInput) -> str:
        """Find emails mentioning a specific entity (organization, URL, phone, etc.)."""
        return await run_with_db(
            deps, lambda db: json_response(db.search_by_entity(params.entity, entity_type=params.entity_type, limit=params.limit))
        )

    @mcp.tool(name="email_list_entities", annotations=deps.tool_annotations("List Top Entities"))
    async def email_list_entities(params: ListEntitiesInput) -> str:
        """List most frequently mentioned entities in the email archive."""
        return await run_with_db(
            deps, lambda db: json_response(db.top_entities(entity_type=params.entity_type, limit=params.limit))
        )

    @mcp.tool(name="email_entity_network", annotations=deps.tool_annotations("Entity Co-occurrences"))
    async def email_entity_network(params: EntityNetworkInput) -> str:
        """Find entities that co-occur with the given entity in the same emails."""
        return await run_with_db(deps, lambda db: json_response(db.entity_co_occurrences(params.entity, limit=params.limit)))

    # email_find_people removed — subsumed by email_search_by_entity(entity_type="person")

    @mcp.tool(name="email_entity_timeline", annotations=deps.tool_annotations("Entity Mention Timeline"))
    async def email_entity_timeline(params: EntityTimelineInput) -> str:
        """Show how often an entity appears over time.

        Track mention frequency of any entity (person, organization, etc.)
        across the email archive, grouped by day/week/month.

        Args:
            params: entity (str) - entity to track, period (str) - 'day'/'week'/'month'.

        Returns:
            JSON list of {period, count} entries.
        """
        return await run_with_db(deps, lambda db: json_response(db.entity_timeline(params.entity, period=params.period)))
