"""Network analysis MCP tools."""

from __future__ import annotations

from typing import Any

from ..mcp_models import (
    CoordinatedTimingInput,
    EmailContactsInput,
    NetworkAnalysisInput,
    RelationshipPathsInput,
    RelationshipSummaryInput,
    SharedRecipientsInput,
)
from .utils import ToolDepsProto, json_response, run_with_db, run_with_network


def register(mcp: Any, deps: ToolDepsProto) -> None:
    """Register network analysis tools."""

    @mcp.tool(name="email_contacts", annotations=deps.tool_annotations("Email Contacts"))
    async def email_contacts(params: EmailContactsInput) -> str:
        """Top contacts for a person, or bidirectional stats between two people.

        Omit compare_with to get top communication partners ranked by frequency.
        Set compare_with to get bidirectional communication stats between two addresses.
        """
        if params.compare_with:
            return await run_with_db(
                deps, lambda db: json_response(db.communication_between(params.email_address, params.compare_with))
            )
        return await run_with_db(deps, lambda db: json_response(db.top_contacts(params.email_address, limit=params.limit)))

    @mcp.tool(name="email_network_analysis", annotations=deps.tool_annotations("Email Network Analysis"))
    async def email_network_analysis(params: NetworkAnalysisInput) -> str:
        """Analyze the communication network: centrality, communities, bridge nodes."""
        return await run_with_network(deps, lambda db, net: json_response(net.network_analysis(top_n=params.top_n)))

    @mcp.tool(
        name="relationship_paths",
        annotations=deps.tool_annotations("Find Communication Paths"),
    )
    async def relationship_paths(params: RelationshipPathsInput) -> str:
        """Find communication paths between two people via intermediaries.

        Shows how person A connects to person B through shared contacts.
        Useful for mapping relationships in investigations and legal analysis.
        """

        def _work(db: Any, net: Any) -> str:
            paths = net.find_paths(
                source=params.source,
                target=params.target,
                max_hops=params.max_hops,
                top_k=params.top_k,
            )
            return json_response({"paths": paths, "count": len(paths)})

        return await run_with_network(deps, _work)

    @mcp.tool(
        name="shared_recipients",
        annotations=deps.tool_annotations("Find Shared Recipients"),
    )
    async def shared_recipients(params: SharedRecipientsInput) -> str:
        """Find recipients common to multiple senders.

        Identifies who is 'in the loop' on coordinated communications.
        Useful for discovering shared targets or information brokers.
        """

        def _work(db: Any, net: Any) -> str:
            results = net.shared_recipients(
                email_addresses=params.email_addresses,
                min_shared=params.min_shared,
            )
            total = len(results)
            results = results[: params.limit]
            return json_response({"shared_recipients": results, "count": len(results), "total": total})

        return await run_with_network(deps, _work)

    @mcp.tool(
        name="coordinated_timing",
        annotations=deps.tool_annotations("Detect Coordinated Timing"),
    )
    async def coordinated_timing(params: CoordinatedTimingInput) -> str:
        """Detect time windows where multiple senders were emailing together.

        Finds synchronized communication patterns: periods where multiple
        people were actively emailing within the same time window.
        """

        def _work(db: Any, net: Any) -> str:
            windows = net.coordinated_timing(
                email_addresses=params.email_addresses,
                window_hours=params.window_hours,
                min_events=params.min_events,
            )
            total = len(windows)
            windows = windows[: params.limit]
            return json_response({"windows": windows, "count": len(windows), "total": total})

        return await run_with_network(deps, _work)

    @mcp.tool(
        name="relationship_summary",
        annotations=deps.tool_annotations("Person Relationship Profile"),
    )
    async def relationship_summary(params: RelationshipSummaryInput) -> str:
        """Full relationship profile for one person.

        One-call profile: top contacts, community membership, bridge score,
        send/receive ratio. Saves tokens compared to multiple separate calls.
        """
        return await run_with_network(
            deps,
            lambda db, net: json_response(
                net.relationship_summary(
                    email_address=params.email_address,
                    limit=params.limit,
                )
            ),
        )
