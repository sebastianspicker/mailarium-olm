"""Reporting and export MCP tools."""

from __future__ import annotations

import logging
from typing import Any

from ..mcp_models import EmailReportInput
from .utils import ToolDepsProto, json_error, json_response, run_with_db

logger = logging.getLogger(__name__)


def register(mcp: Any, deps: ToolDepsProto) -> None:
    """Register reporting and export tools."""

    @mcp.tool(
        name="email_report",
        annotations=deps.idempotent_write_annotations("Generate Email Report"),
    )
    async def email_report(params: EmailReportInput) -> str:
        """Generate reports: archive overview, network export, or writing analysis.

        type='archive': self-contained HTML report with overview, top senders, volume.
        type='network': GraphML export for Gephi/Cytoscape visualization.
        type='writing': writing style and readability metrics per sender.
        """

        def _work(db: Any) -> str:
            if params.type == "archive":
                from ..report_generator import ReportGenerator

                ReportGenerator(db).generate(title=params.title, output_path=params.output_path)
                return json_response({"status": "ok", "output_path": params.output_path})

            if params.type == "network":
                from ..network_analysis import CommunicationNetwork

                return json_response(CommunicationNetwork(db).export_graphml(params.output_path))

            if params.type == "writing":
                return _writing_analysis(deps, db, params.sender, params.limit)

            return json_error(f"Invalid type: {params.type}. Use 'archive', 'network', or 'writing'.")

        return await run_with_db(deps, _work)


def _writing_analysis(deps: ToolDepsProto, db: Any, sender: str | None, limit: int) -> str:
    """Run writing style analysis (extracted for clarity)."""
    from ..writing_analyzer import WritingAnalyzer

    retriever = deps.get_retriever()
    analyzer = WritingAnalyzer()

    def _get_sender_texts(sender_filter: str, max_texts: int = 50) -> list[str]:
        """Get email body texts for a sender.

        Prefers SQLite direct query (avoids semantic search with a
        meaningless '*' query). Falls back to search_filtered if SQLite
        is not available.
        """
        # Prefer direct SQLite query — accurate and avoids '*' embedding
        if db:
            try:
                emails = db.list_emails_paginated(
                    sender=sender_filter,
                    limit=max_texts,
                    offset=0,
                )
                uids = [e["uid"] for e in emails.get("emails", [])]
                if uids:
                    full_map = db.get_emails_full_batch(uids)
                    return [full.get("body_text", "") for full in full_map.values() if full and full.get("body_text")][:max_texts]
            except Exception:
                logger.debug("SQLite query failed for sender %r, falling back", sender_filter, exc_info=True)

        # Fallback: use search_filtered with a generic query
        try:
            results = retriever.search_filtered(
                query="email",
                top_k=max_texts,
                sender=sender_filter,
            )
            return [r.text for r in results if r.text]
        except Exception:
            logger.debug("search_filtered failed for sender %r", sender_filter, exc_info=True)
            return []

    if sender:
        texts = _get_sender_texts(sender, max_texts=limit)
        if not texts:
            return json_error(f"No emails found for sender: {sender}")
        profile = analyzer.analyze_sender_profile(texts, sender)
        if not profile:
            return json_error(f"Not enough content to analyze: {sender}")
        return json_response(profile)

    # Compare top senders
    if not db:
        return json_error("SQLite database not available.")

    try:
        senders = db.top_senders(limit=limit)
    except Exception:
        return json_error("Could not fetch sender list.")

    profiles = []
    for s in senders:
        email_addr = s.get("sender_email", "")
        if not email_addr:
            continue
        texts = _get_sender_texts(email_addr, max_texts=30)
        profile = analyzer.analyze_sender_profile(texts, email_addr)
        if profile:
            profiles.append(profile)

    return json_response(profiles)
