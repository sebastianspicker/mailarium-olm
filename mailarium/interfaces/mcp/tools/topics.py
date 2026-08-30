"""Cluster, topic, similarity, and discovery MCP tools."""

from __future__ import annotations

from typing import Any

from ..mcp_models import (
    EmailClustersInput,
    EmailDiscoveryInput,
    EmailTopicsInput,
    FindSimilarInput,
)
from .utils import ToolDepsProto, json_error, json_response, run_with_db


def register(mcp: Any, deps: ToolDepsProto) -> None:
    """Register cluster, topic, similarity, and discovery tools."""
    _register_clusters_tool(mcp, deps)
    _register_similar_tool(mcp, deps)
    _register_topics_tool(mcp, deps)
    _register_discovery_tool(mcp, deps)


def _register_clusters_tool(mcp: Any, deps: ToolDepsProto) -> None:
    """Register the clusters tool without coupling it to sibling tool modules."""

    @mcp.tool(name="email_clusters", annotations=deps.tool_annotations("Email Clusters"))
    async def email_clusters(params: EmailClustersInput) -> str:
        """List all clusters or emails in a specific cluster.

        Omit cluster_id to list all clusters with sizes and labels.
        Set cluster_id to list emails in that cluster, sorted by centroid proximity.
        """

        def _work(db):
            if params.cluster_id is not None:
                return json_response(db.emails_in_cluster(params.cluster_id, limit=params.limit))
            results = db.cluster_summary()
            if not results:
                return json_error("No clusters available. Run `mailarium topics build` to populate cluster tables.")
            return json_response(results)

        return await run_with_db(deps, _work)


def _register_similar_tool(mcp: Any, deps: ToolDepsProto) -> None:
    """Register the similar tool without coupling it to sibling tool modules."""

    @mcp.tool(name="email_find_similar", annotations=deps.tool_annotations("Find Similar Emails"))
    async def email_find_similar(params: FindSimilarInput) -> str:
        """Find emails most similar to a given email or query text.

        Provide either uid (to find emails similar to a specific email) or
        query (to find emails similar to a text description).
        """

        def _run():
            query, error = _similarity_query(deps, params)
            if error:
                return json_error(error)
            return _similarity_response(deps, params, query)

        return await deps.offload(_run)


def _register_topics_tool(mcp: Any, deps: ToolDepsProto) -> None:
    """Register the topics tool without coupling it to sibling tool modules."""

    @mcp.tool(name="email_topics", annotations=deps.tool_annotations("Email Topics"))
    async def email_topics(params: EmailTopicsInput) -> str:
        """List all topics or emails assigned to a specific topic.

        Omit topic_id to list all discovered topics with labels and top words.
        Set topic_id to list emails for that topic, ranked by relevance.
        """

        def _work(db):
            if params.topic_id is not None:
                return json_response(db.emails_by_topic(params.topic_id, limit=params.limit))
            results = db.topic_distribution()
            if not results:
                return json_error("No topics available. Run `mailarium topics build` to populate topic tables.")
            return json_response(results)

        return await run_with_db(deps, _work)


def _register_discovery_tool(mcp: Any, deps: ToolDepsProto) -> None:
    """Register the discovery tool without coupling it to sibling tool modules."""

    @mcp.tool(name="email_discovery", annotations=deps.tool_annotations("Keyword & Suggestion Discovery"))
    async def email_discovery(params: EmailDiscoveryInput) -> str:
        """Discover keywords or get search suggestions."""

        def _work(db):
            if params.mode == "keywords":
                results = db.top_keywords(sender=params.sender, folder=params.folder, limit=params.limit)
                if not results:
                    return json_error("No keywords available. Run ingestion with --extract-keywords.")
                return json_response(results)
            if params.mode == "suggestions":
                from mailarium.retrieval.query_suggestions import QuerySuggester

                return json_response(QuerySuggester(db).suggest(limit=params.limit))
            return json_error(f"Invalid mode: {params.mode}. Use 'keywords' or 'suggestions'.")

        return await run_with_db(deps, _work)


def _similarity_query(deps: ToolDepsProto, params: FindSimilarInput) -> tuple[str | None, str | None]:
    """Resolve a direct or UID-derived similarity query without searching."""
    if not params.uid and not params.query:
        return None, "Provide either uid or query."
    if params.query:
        return params.query, None
    assert params.uid is not None
    db = deps.get_archive_database()
    email = db.get_email_full(params.uid) if db else None
    if db and not email:
        return None, f"Email not found: {params.uid}"
    query = (email or {}).get("body_text") or (email or {}).get("subject") or ""
    return (query[:1500], None) if query else (None, "Could not retrieve email text for similarity search.")


def _similarity_response(deps: ToolDepsProto, params: FindSimilarInput, query: str | None) -> str:
    """Run the filtered search and preserve the existing compact response shape."""
    if query is None:
        return json_error("Provide either uid or query.")
    retriever = deps.get_retriever()
    results = retriever.search_filtered(
        query=query,
        top_k=params.top_k + 1,
        scope=params.scope,
    )
    if params.uid:
        results = [result for result in results if result.metadata.get("uid") != params.uid]
    visible_results, scan_payload = _similarity_scan(params.scan_id, results[: params.top_k])
    payload = retriever.serialize_results(query, visible_results)
    from .search import _retrieval_diagnostics

    diagnostics = _retrieval_diagnostics(getattr(retriever, "last_search_debug", getattr(retriever, "_last_search_debug", None)))
    if diagnostics:
        payload["retrieval_diagnostics"] = diagnostics
    if scan_payload:
        payload["_scan"] = scan_payload
    return json_response(payload)


def _similarity_scan(scan_id: str | None, results: list[Any]) -> tuple[list[Any], Any]:
    """Apply optional scan-session de-duplication to already bounded results."""
    if not scan_id:
        return results, None
    from mailarium.retrieval.scan_session import filter_seen

    return filter_seen(scan_id, results)
