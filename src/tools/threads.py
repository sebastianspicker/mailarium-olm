"""Thread intelligence MCP tools."""

from __future__ import annotations

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

            from ..thread_summarizer import summarize_thread

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

    @mcp.tool(name="email_action_items", annotations=deps.tool_annotations("Extract Action Items"))
    async def email_action_items(params: ActionItemsInput) -> str:
        """Extract action items from a thread or across recent emails.

        Detects patterns like 'please do X', 'need to', 'I will', 'by Friday'.
        """

        def _run():
            from ..thread_intelligence import ThreadAnalyzer

            analyzer = ThreadAnalyzer()

            if params.conversation_id:
                retriever = deps.get_retriever()
                results = retriever.search_by_thread(
                    conversation_id=params.conversation_id,
                    top_k=50,
                )
                if not results:
                    return json_error("No emails found for this thread.")

                all_items = []
                for r in results:
                    items = analyzer.extract_action_items(
                        deps.sanitize(r.text or ""),
                        sender=r.metadata.get("sender_email", ""),
                        source_uid=r.metadata.get("uid", ""),
                    )
                    all_items.extend(items)

                items_out = [
                    {
                        "text": a.text,
                        "assignee": a.assignee,
                        "deadline": a.deadline,
                        "is_urgent": a.is_urgent,
                        "source_uid": a.source_uid,
                    }
                    for a in all_items[: params.limit]
                ]
                return json_response({"count": len(items_out), "items": items_out})

            if params.days:
                retriever = deps.get_retriever()
                cutoff = (datetime.now(UTC) - timedelta(days=params.days)).strftime("%Y-%m-%d")
                results = retriever.search_filtered(
                    query="action items tasks todo",
                    top_k=params.limit * 3,
                    date_from=cutoff,
                )
                all_items = []
                for r in results:
                    items = analyzer.extract_action_items(
                        deps.sanitize(r.text or ""),
                        sender=r.metadata.get("sender_email", ""),
                        source_uid=r.metadata.get("uid", ""),
                    )
                    all_items.extend(items)
                items_out = [
                    {
                        "text": a.text,
                        "assignee": a.assignee,
                        "deadline": a.deadline,
                        "is_urgent": a.is_urgent,
                        "source_uid": a.source_uid,
                    }
                    for a in all_items[: params.limit]
                ]
                return json_response({"count": len(items_out), "items": items_out})

            return json_error("Provide conversation_id or days to extract action items.")

        return await deps.offload(_run)

    @mcp.tool(name="email_decisions", annotations=deps.tool_annotations("Extract Decisions"))
    async def email_decisions(params: DecisionsInput) -> str:
        """Extract decisions from email threads.

        Detects patterns like 'we decided', 'agreed to', 'approved', 'go ahead with'.
        """

        def _run():
            from ..thread_intelligence import ThreadAnalyzer

            analyzer = ThreadAnalyzer()

            if params.conversation_id:
                retriever = deps.get_retriever()
                results = retriever.search_by_thread(
                    conversation_id=params.conversation_id,
                    top_k=50,
                )
                if not results:
                    return json_error("No emails found for this thread.")

                all_decisions = []
                for r in results:
                    decisions = analyzer.extract_decisions(
                        deps.sanitize(r.text or ""),
                        sender=r.metadata.get("sender_email", ""),
                        date=r.metadata.get("date", ""),
                        source_uid=r.metadata.get("uid", ""),
                    )
                    all_decisions.extend(decisions)

                items_out = [
                    {"text": d.text, "made_by": d.made_by, "date": d.date, "source_uid": d.source_uid}
                    for d in all_decisions[: params.limit]
                ]
                return json_response({"count": len(items_out), "items": items_out})

            if params.days:
                retriever = deps.get_retriever()
                cutoff = (datetime.now(UTC) - timedelta(days=params.days)).strftime("%Y-%m-%d")
                results = retriever.search_filtered(
                    query="decided agreed approved confirmed",
                    top_k=100,
                    date_from=cutoff,
                )
                all_decisions = []
                for r in results:
                    decisions = analyzer.extract_decisions(
                        deps.sanitize(r.text or ""),
                        sender=r.metadata.get("sender_email", ""),
                        date=r.metadata.get("date", ""),
                        source_uid=r.metadata.get("uid", ""),
                    )
                    all_decisions.extend(decisions)
                items_out = [
                    {"text": d.text, "made_by": d.made_by, "date": d.date, "source_uid": d.source_uid}
                    for d in all_decisions[: params.limit]
                ]
                return json_response({"count": len(items_out), "items": items_out})

            return json_error("Provide conversation_id or days to extract decisions.")

        return await deps.offload(_run)
