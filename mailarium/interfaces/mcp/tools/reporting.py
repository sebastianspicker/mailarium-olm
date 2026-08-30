"""Reporting and export MCP tools."""

from __future__ import annotations

import logging
from typing import Any

from ..mcp_models import EmailReportInput
from .utils import ToolDepsProto, json_error, json_response, run_with_db

logger = logging.getLogger(__name__)


def _report_warnings(generator: Any) -> list[str]:
    """Normalize a generator warning list while discarding blank or non-list values."""
    warnings = getattr(generator, "last_warnings", [])
    if not isinstance(warnings, list):
        return []
    return [str(item) for item in warnings if str(item).strip()]


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
                from mailarium.investigation.report_generator import ReportGenerationError, ReportGenerator

                generator = ReportGenerator(db)
                try:
                    generator.generate(
                        title=params.title,
                        output_path=params.output_path,
                        privacy_mode=params.privacy_mode,
                    )
                except ReportGenerationError as exc:
                    return json_error(str(exc))

                warnings = _report_warnings(generator)
                status = "degraded" if warnings else "ok"
                return json_response(
                    {
                        "status": status,
                        "output_path": params.output_path,
                        "privacy_mode": params.privacy_mode,
                        "warnings": warnings,
                    }
                )

            if params.type == "network":
                from mailarium.investigation.network_analysis import CommunicationNetwork

                return json_response(CommunicationNetwork(db).export_graphml(params.output_path))

            if params.type == "writing":
                return _writing_analysis(deps, db, params.sender, params.limit)

            return json_error(f"Invalid type: {params.type}. Use 'archive', 'network', or 'writing'.")

        return await run_with_db(deps, _work)


def _writing_analysis(deps: ToolDepsProto, db: Any, sender: str | None, limit: int) -> str:
    """Analyze one sender or top archive senders and format the resulting style report."""
    from mailarium.investigation.writing_analyzer import WritingAnalyzer

    retriever = deps.get_retriever()
    analyzer = WritingAnalyzer()
    if sender:
        return _single_sender_writing_analysis(_sender_texts(db, retriever, sender, limit), analyzer, sender)
    return _top_sender_writing_analysis(db, retriever, analyzer, limit)


def _sender_texts(db: Any, retriever: Any, sender_filter: str, max_texts: int = 50) -> list[str]:
    """Get email body texts for a sender, preferring the SQLite archive."""
    if db:
        try:
            emails = db.list_emails_paginated(sender=sender_filter, limit=max_texts, offset=0)
            uids = [email["uid"] for email in emails.get("emails", [])]
            if uids:
                full_map = db.get_emails_full_batch(uids)
                return [full.get("body_text", "") for full in full_map.values() if full and full.get("body_text")][:max_texts]
        except Exception:
            logger.debug("SQLite query failed for sender %r, falling back", sender_filter, exc_info=True)
    try:
        results = retriever.search_filtered(query="email", top_k=max_texts, sender=sender_filter)
        return [result.text for result in results if result.text]
    except Exception:
        logger.debug("search_filtered failed for sender %r", sender_filter, exc_info=True)
        return []


def _single_sender_writing_analysis(texts: list[str], analyzer: Any, sender: str) -> str:
    """Analyze one sender only when enough mailbox text exists to produce a profile."""
    if not texts:
        return json_error(f"No emails found for sender: {sender}")
    profile = analyzer.analyze_sender_profile(texts, sender)
    if not profile:
        return json_error(f"Not enough content to analyze: {sender}")
    return json_response(profile)


def _top_sender_writing_analysis(db: Any, retriever: Any, analyzer: Any, limit: int) -> str:
    """Build writing profiles for top senders while skipping missing addresses and empty analyses."""
    if not db:
        return json_error("SQLite database not available.")
    try:
        senders = db.top_senders(limit=limit)
    except Exception:
        return json_error("Could not fetch sender list.")
    profiles = []
    for sender in senders:
        email_addr = sender.get("sender_email", "")
        if not email_addr:
            continue
        profile = analyzer.analyze_sender_profile(_sender_texts(db, retriever, email_addr, max_texts=30), email_addr)
        if profile:
            profiles.append(profile)
    return json_response(profiles)
