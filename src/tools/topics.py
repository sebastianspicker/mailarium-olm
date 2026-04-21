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
                return json_error("No clusters available. Run `email-rag topics build` to populate cluster tables.")
            return json_response(results)

        return await run_with_db(deps, _work)

    @mcp.tool(name="email_find_similar", annotations=deps.tool_annotations("Find Similar Emails"))
    async def email_find_similar(params: FindSimilarInput) -> str:
        """Find emails most similar to a given email or query text.

        Provide either uid (to find emails similar to a specific email) or
        query (to find emails similar to a text description).
        """

        def _run():
            if not params.uid and not params.query:
                return json_error("Provide either uid or query.")

            retriever = deps.get_retriever()
            query = params.query
            if params.uid and not query:
                db = deps.get_email_db()
                if db:
                    email = db.get_email_full(params.uid)
                    if not email:
                        return json_error(f"Email not found: {params.uid}")
                    body = email.get("body_text") or email.get("subject") or ""
                    query = body[:1500]
                if not query:
                    return json_error("Could not retrieve email text for similarity search.")

            if query is None:
                return json_error("Provide either uid or query.")
            # Use search_filtered instead of search to get per-email
            # deduplication (only the best chunk per email is returned).
            results = retriever.search_filtered(query, top_k=params.top_k + 1)
            if params.uid:
                results = [r for r in results if r.metadata.get("uid") != params.uid]
            results = results[: params.top_k]
            scan_meta = None
            if params.scan_id:
                from ..scan_session import filter_seen

                results, scan_meta = filter_seen(params.scan_id, results)
            payload = retriever.serialize_results(query or "", results)
            if scan_meta:
                payload["_scan"] = scan_meta
            return json_response(payload)

        return await deps.offload(_run)

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
                return json_error("No topics available. Run `email-rag topics build` to populate topic tables.")
            return json_response(results)

        return await run_with_db(deps, _work)

    @mcp.tool(name="email_discovery", annotations=deps.tool_annotations("Keyword & Suggestion Discovery"))
    async def email_discovery(params: EmailDiscoveryInput) -> str:
        """Discover keywords or get search suggestions.

        mode='keywords': top keywords across the archive (filterable by sender/folder).
        mode='suggestions': categorized search suggestions based on indexed data.
        """

        def _work(db):
            if params.mode == "keywords":
                results = db.top_keywords(
                    sender=params.sender,
                    folder=params.folder,
                    limit=params.limit,
                )
                if not results:
                    return json_error("No keywords available. Run ingestion with --extract-keywords.")
                return json_response(results)
            if params.mode == "suggestions":
                from ..query_suggestions import QuerySuggester

                return json_response(QuerySuggester(db).suggest(limit=params.limit))
            return json_error(f"Invalid mode: {params.mode}. Use 'keywords' or 'suggestions'.")

        return await run_with_db(deps, _work)
