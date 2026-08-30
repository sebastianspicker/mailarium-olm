"""Thread intelligence MCP tools."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from ..mcp_models import (
    ActionItemsInput,
    DecisionsInput,
    EmailThreadLookupInput,
    ThreadSummaryInput,
)
from .utils import ToolDepsProto, json_error, json_response, run_with_db


def register(mcp: Any, deps: ToolDepsProto) -> None:
    """Register thread intelligence tools."""
    _register_thread_lookup_tool(mcp, deps)
    _register_thread_summary_tool(mcp, deps)
    _register_action_items_tool(mcp, deps)
    _register_decisions_tool(mcp, deps)


def _analysis_results(
    deps: ToolDepsProto,
    *,
    conversation_id: str | None,
    days: int | None,
    recent_query: str,
    recent_top_k: int,
) -> tuple[list[Any], bool] | None:
    """Load either one conversation or a bounded recent-search result set."""
    retriever = deps.get_retriever()
    if conversation_id:
        return retriever.search_by_thread(conversation_id=conversation_id, top_k=50), True
    if days:
        cutoff = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
        return (
            retriever.search_filtered(
                query=recent_query,
                top_k=recent_top_k,
                date_from=cutoff,
            ),
            False,
        )
    return None


def _thread_analysis_payload(
    deps: ToolDepsProto,
    *,
    conversation_id: str | None,
    days: int | None,
    recent_query: str,
    recent_top_k: int,
    limit: int,
    missing_scope_error: str,
    extract: Callable[[Any, str, dict[str, Any]], list[Any]],
    serialize: Callable[[Any], dict[str, Any]],
) -> str:
    """Extract and serialize bounded thread intelligence from a selected scope."""
    selection = _analysis_results(
        deps,
        conversation_id=conversation_id,
        days=days,
        recent_query=recent_query,
        recent_top_k=recent_top_k,
    )
    if selection is None:
        return json_error(missing_scope_error)
    results, is_thread = selection
    if is_thread and not results:
        return json_error("No emails found for this thread.")

    from mailarium.investigation.thread_intelligence import ThreadAnalyzer

    analyzer = ThreadAnalyzer()
    extracted: list[Any] = []
    for result in results:
        extracted.extend(extract(analyzer, deps.sanitize(result.text or ""), result.metadata))
    items = [serialize(item) for item in extracted[:limit]]
    return json_response({"count": len(items), "items": items})


def _extract_action_items(analyzer: Any, text: str, metadata: dict[str, Any]) -> list[Any]:
    return analyzer.extract_action_items(
        text,
        sender=metadata.get("sender_email", ""),
        source_uid=metadata.get("uid", ""),
    )


def _action_item_payload(item: Any) -> dict[str, Any]:
    return {
        "text": item.text,
        "assignee": item.assignee,
        "deadline": item.deadline,
        "is_urgent": item.is_urgent,
        "source_uid": item.source_uid,
    }


def _extract_decisions(analyzer: Any, text: str, metadata: dict[str, Any]) -> list[Any]:
    return analyzer.extract_decisions(
        text,
        sender=metadata.get("sender_email", ""),
        date=metadata.get("date", ""),
        source_uid=metadata.get("uid", ""),
    )


def _decision_payload(item: Any) -> dict[str, Any]:
    return {
        "text": item.text,
        "made_by": item.made_by,
        "date": item.date,
        "source_uid": item.source_uid,
    }


def _register_thread_lookup_tool(mcp: Any, deps: ToolDepsProto) -> None:
    """Register the thread lookup tool without coupling it to sibling tool modules."""

    @mcp.tool(name="email_thread_lookup", annotations=deps.tool_annotations("Thread Lookup"))
    async def email_thread_lookup(params: EmailThreadLookupInput) -> str:
        """Retrieve all emails in a thread by conversation_id or thread_topic.

        Provide exactly one: conversation_id (from search result metadata)
        or thread_topic (from OLM metadata). Returns all thread emails sorted by date.
        """
        if params.conversation_id:
            conv_id: str = params.conversation_id

            def _run():
                retriever = deps.get_retriever()
                results = retriever.search_by_thread(
                    conversation_id=conv_id,
                    top_k=params.limit,
                )
                payload = retriever.serialize_results(
                    conv_id,
                    results,
                )
                payload["conversation_id"] = conv_id
                return json_response(payload)

            return await deps.offload(_run)

        def _work(db):
            emails = db.thread_by_topic(params.thread_topic, limit=params.limit)
            return json_response(
                {
                    "thread_topic": params.thread_topic,
                    "emails": emails,
                    "count": len(emails),
                }
            )

        return await run_with_db(deps, _work)


def _register_thread_summary_tool(mcp: Any, deps: ToolDepsProto) -> None:
    """Register the thread summary tool without coupling it to sibling tool modules."""

    @mcp.tool(name="email_thread_summary", annotations=deps.tool_annotations("Summarize Thread"))
    async def email_thread_summary(params: ThreadSummaryInput) -> str:
        """Summarize a conversation thread using extractive summarization.

        Selects the most important sentences from the thread based on
        TF-IDF scoring with position bias.
        """

        def _run():
            retriever = deps.get_retriever()
            results = retriever.search_by_thread(
                conversation_id=params.conversation_id,
                top_k=50,
            )
            if not results:
                return json_error(f"No emails found for thread: {params.conversation_id}")

            emails = [
                {
                    "clean_body": deps.sanitize(r.text or ""),
                    "sender_email": r.metadata.get("sender_email", ""),
                    "sender_name": r.metadata.get("sender_name", ""),
                    "date": r.metadata.get("date", ""),
                    "uid": r.metadata.get("uid", ""),
                    "subject": r.metadata.get("subject", ""),
                }
                for r in results
            ]

            from mailarium.investigation.thread_summarizer import summarize_thread

            summary = summarize_thread(emails, max_sentences=params.max_sentences)
            participants = list(dict.fromkeys(e["sender_email"] for e in emails if e["sender_email"]))
            dates = [str(e["date"])[:10] for e in emails if e["date"]]
            return json_response(
                {
                    "conversation_id": params.conversation_id,
                    "email_count": len(emails),
                    "participants": participants,
                    "date_range": {"first": min(dates), "last": max(dates)} if dates else {},
                    "summary": summary,
                }
            )

        return await deps.offload(_run)


def _register_action_items_tool(mcp: Any, deps: ToolDepsProto) -> None:
    """Register the action items tool without coupling it to sibling tool modules."""

    @mcp.tool(name="email_action_items", annotations=deps.tool_annotations("Extract Action Items"))
    async def email_action_items(params: ActionItemsInput) -> str:
        """Extract action items from a thread or across recent emails.

        Detects patterns like 'please do X', 'need to', 'I will', 'by Friday'.
        """

        def _run():
            return _thread_analysis_payload(
                deps,
                conversation_id=params.conversation_id,
                days=params.days,
                recent_query="action items tasks todo",
                recent_top_k=params.limit * 3,
                limit=params.limit,
                missing_scope_error="Provide conversation_id or days to extract action items.",
                extract=_extract_action_items,
                serialize=_action_item_payload,
            )

        return await deps.offload(_run)


def _register_decisions_tool(mcp: Any, deps: ToolDepsProto) -> None:
    """Register the decisions tool without coupling it to sibling tool modules."""

    @mcp.tool(name="email_decisions", annotations=deps.tool_annotations("Extract Decisions"))
    async def email_decisions(params: DecisionsInput) -> str:
        """Extract decisions from email threads.

        Detects patterns like 'we decided', 'agreed to', 'approved', 'go ahead with'.
        """

        def _run():
            return _thread_analysis_payload(
                deps,
                conversation_id=params.conversation_id,
                days=params.days,
                recent_query="decided agreed approved confirmed",
                recent_top_k=100,
                limit=params.limit,
                missing_scope_error="Provide conversation_id or days to extract decisions.",
                extract=_extract_decisions,
                serialize=_decision_payload,
            )

        return await deps.offload(_run)
