"""Evidence management, provenance, and collection-report MCP tools."""
# pylint: disable=too-many-statements

from __future__ import annotations

import logging
from typing import Any

from ..mcp_models import (
    CustodyChainInput,
    EmailDossierInput,
    EmailProvenanceInput,
    EvidenceAddBatchInput,
    EvidenceAddInput,
    EvidenceExportInput,
    EvidenceGetInput,
    EvidenceOverviewInput,
    EvidenceProvenanceInput,
    EvidenceQueryInput,
    EvidenceRemoveInput,
    EvidenceUpdateInput,
)
from .utils import ToolDepsProto, json_error, json_response, run_with_db

logger = logging.getLogger(__name__)


def _compact_evidence_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return new list of evidence items with heavy fields stripped (compact mode).

    Creates new dicts instead of mutating the originals.
    """
    compacted: list[dict[str, Any]] = []
    for item in items:
        new_item = {k: v for k, v in item.items() if k not in ("key_quote", "notes", "content_hash")}
        quote = item.get("key_quote") or ""
        new_item["quote_preview"] = (quote[:80] + "...") if len(quote) > 80 else quote
        compacted.append(new_item)
    return compacted


def _custody_chain_response(db: Any, params: CustodyChainInput) -> str:
    """Query custody events, optionally compact them, and echo only active filters."""
    events = db.get_custody_chain(
        target_type=params.target_type, target_id=params.target_id, action=params.action, limit=params.limit
    )
    if params.compact:
        events = _compact_custody_events(events)
    payload: dict[str, Any] = {"count": len(events), "events": events}
    filter_pairs = (
        ("target_type", params.target_type),
        ("target_id", params.target_id),
        ("action", params.action),
    )
    filters = {key: value for key, value in filter_pairs if value}
    if filters:
        payload["filter"] = filters
    return json_response(payload, default=str)


def _compact_custody_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compact custody events to keep bounded tool responses useful."""
    compacted = []
    for event in events:
        compact = {key: value for key, value in event.items() if key not in ("details", "content_hash")}
        if content_hash := event.get("content_hash", ""):
            compact["hash_prefix"] = content_hash[:16]
        compacted.append(compact)
    return compacted


def _query_evidence_response(db: Any, params: EvidenceQueryInput) -> str:
    """Route evidence requests to text search, chronological timeline, or filtered listing."""
    if params.query:
        return _search_evidence_response(db, params)
    if params.sort == "date":
        return _timeline_evidence_response(db, params)
    return _list_evidence_response(db, params)


def _search_evidence_response(db: Any, params: EvidenceQueryInput) -> str:
    """Search evidence text, optionally remove full quotes, and annotate empty results."""
    result = db.search_evidence(
        query=params.query,
        category=params.category,
        min_relevance=params.min_relevance,
        limit=params.limit,
    )
    if not params.include_quotes:
        result = {**result, "items": _compact_evidence_items(result["items"])}
    result.update(mode="search", query=params.query)
    if not result["items"]:
        result["message"] = f"No evidence items match query: {params.query}"
    return json_response(result)


def _timeline_evidence_response(db: Any, params: EvidenceQueryInput) -> str:
    """Return chronologically filtered evidence with optional quote compaction and empty-state guidance."""
    items = db.evidence_timeline(
        category=params.category,
        min_relevance=params.min_relevance,
        limit=params.limit,
        offset=params.offset,
    )
    if not params.include_quotes:
        items = _compact_evidence_items(items)
    payload: dict[str, Any] = {"mode": "timeline", "items": items, "total": len(items)}
    if not items:
        payload["message"] = "No evidence items found for the given filters."
    return json_response(payload)


def _list_evidence_response(db: Any, params: EvidenceQueryInput) -> str:
    """List filtered evidence with pagination metadata, optional quote compaction, and collection guidance."""
    result = db.list_evidence(
        category=params.category,
        min_relevance=params.min_relevance,
        email_uid=params.email_uid,
        limit=params.limit,
        offset=params.offset,
    )
    if not params.include_quotes:
        result = {**result, "items": _compact_evidence_items(result["items"])}
    result["mode"] = "list"
    if not result["items"]:
        result["message"] = "No evidence items found. Use evidence_add to start collecting evidence."
    return json_response(result)


def register(mcp: Any, deps: ToolDepsProto) -> None:
    """Register evidence, custody, and dossier tools."""
    _register_custody_tools(mcp, deps)
    _register_dossier_tool(mcp, deps)
    _register_evidence_add_tool(mcp, deps)
    _register_evidence_query_tool(mcp, deps)
    _register_evidence_detail_tools(mcp, deps)
    _register_evidence_mutation_tools(mcp, deps)
    _register_evidence_export_tools(mcp, deps)


def _register_custody_tools(mcp: Any, deps: ToolDepsProto) -> None:
    # ── Chain of Custody ──────────────────────────────────────────

    """Register the custody tools without coupling it to sibling tool modules."""

    @mcp.tool(
        name="custody_chain",
        annotations=deps.tool_annotations("View Chain-of-Custody Audit Trail"),
    )
    async def custody_chain(params: CustodyChainInput) -> str:
        """View the chain-of-custody audit trail for evidence handling.

        Shows a chronological log of all evidence lifecycle events.
        Compact mode (default) omits verbose details JSON.
        """

        return await run_with_db(deps, lambda db: _custody_chain_response(db, params))

    @mcp.tool(
        name="email_provenance",
        annotations=deps.tool_annotations("Email Provenance & Source Tracing"),
    )
    async def email_provenance(params: EmailProvenanceInput) -> str:
        """Full provenance for an email: OLM source hash, ingestion run, custody events."""

        def _work(db: Any) -> str:
            return json_response(db.email_provenance(params.email_uid), default=str)

        return await run_with_db(deps, _work)

    @mcp.tool(
        name="evidence_provenance",
        annotations=deps.tool_annotations("Evidence Provenance & Chain"),
    )
    async def evidence_provenance(params: EvidenceProvenanceInput) -> str:
        """Full evidence chain: item details + source email provenance + modification history."""

        def _work(db: Any) -> str:
            return json_response(db.evidence_provenance(params.evidence_id), default=str)

        return await run_with_db(deps, _work)

    # ── Evidence Collection Report ────────────────────────────────


def _register_dossier_tool(mcp: Any, deps: ToolDepsProto) -> None:
    # ── Evidence Collection Report ────────────────────────────────
    """Register the dossier tool without coupling it to sibling tool modules."""

    @mcp.tool(
        name="email_dossier",
        annotations=deps.idempotent_write_annotations("Generate/Preview Evidence Collection"),
    )
    async def email_dossier(params: EmailDossierInput) -> str:
        """Generate or preview an evidence collection report.

        Set preview_only=True to check scope (counts, categories, date range)
        before generating. Default generates a full HTML/PDF dossier combining
        evidence, source emails, relationship analysis, and chain of custody.
        """

        def _work(db: Any) -> str:
            if params.preview_only:
                from ..dossier_generator import DossierGenerator

                return json_response(
                    DossierGenerator(db).preview(
                        min_relevance=params.min_relevance,
                        category=params.category,
                    )
                )

            network = None
            try:
                from ..network_analysis import CommunicationNetwork

                network = CommunicationNetwork(db)
            except Exception:  # pylint: disable=broad-exception-caught
                logger.debug("Network analysis unavailable for dossier generation", exc_info=True)

            from ..dossier_generator import DossierGenerator

            gen = DossierGenerator(db, network=network)
            result = gen.generate_file(
                output_path=params.output_path,
                fmt=params.format,
                title=params.title,
                collection_reference=params.collection_reference,
                custodian=params.custodian,
                prepared_by=params.prepared_by,
                min_relevance=params.min_relevance,
                category=params.category,
                include_relationships=params.include_relationships,
                include_custody=params.include_custody,
                persons_of_interest=params.persons_of_interest,
            )
            return json_response(result)

        return await run_with_db(deps, _work)


def _register_evidence_add_tool(mcp: Any, deps: ToolDepsProto) -> None:
    # ── Evidence Management ───────────────────────────────────────
    """Register the evidence add tool without coupling it to sibling tool modules."""

    @mcp.tool(
        name="evidence_add",
        annotations=deps.write_tool_annotations("Add Evidence Item"),
    )
    async def evidence_add(params: EvidenceAddInput) -> str:
        """Add an evidence item linked to a specific email.

        The key_quote MUST be an exact substring from the email body - it is
        automatically verified against stored body text. Use email_deep_context
        to read the full email body before extracting a quote.
        """

        def _work(db: Any) -> str:
            try:
                return json_response(
                    db.add_evidence(
                        email_uid=params.email_uid,
                        category=params.category,
                        key_quote=params.key_quote,
                        summary=params.summary,
                        relevance=params.relevance,
                        notes=params.notes,
                    )
                )
            except ValueError as exc:
                return json_error(str(exc))

        return await run_with_db(deps, _work)


def _register_evidence_query_tool(mcp: Any, deps: ToolDepsProto) -> None:
    """Register the evidence query tool without coupling it to sibling tool modules."""

    @mcp.tool(
        name="evidence_query",
        annotations=deps.tool_annotations("Query Evidence Items"),
    )
    async def evidence_query(params: EvidenceQueryInput) -> str:
        """List, search, or view evidence timeline in one tool.

        Omit query to list all evidence. Set query to search text.
        Use sort='date' for chronological timeline view.
        Filter by category, min_relevance, or email_uid.
        """

        return await run_with_db(deps, lambda db: _query_evidence_response(db, params))


def _register_evidence_detail_tools(mcp: Any, deps: ToolDepsProto) -> None:
    """Register the evidence detail tools without coupling it to sibling tool modules."""

    @mcp.tool(
        name="evidence_get",
        annotations=deps.tool_annotations("Get Evidence Item"),
    )
    async def evidence_get(params: EvidenceGetInput) -> str:
        """Get a single evidence item with full details including quote and verification status."""

        def _work(db: Any) -> str:
            item = db.get_evidence(params.evidence_id)
            if not item:
                return json_error(f"Evidence item not found: {params.evidence_id}")
            return json_response(item)

        return await run_with_db(deps, _work)


def _register_evidence_mutation_tools(mcp: Any, deps: ToolDepsProto) -> None:
    """Register the evidence mutation tools without coupling it to sibling tool modules."""

    @mcp.tool(
        name="evidence_update",
        annotations=deps.write_tool_annotations("Update Evidence Item"),
    )
    async def evidence_update(params: EvidenceUpdateInput) -> str:
        """Update an evidence item's category, quote, summary, relevance, or notes."""

        def _work(db: Any) -> str:
            updated = db.update_evidence(
                params.evidence_id,
                category=params.category,
                key_quote=params.key_quote,
                summary=params.summary,
                relevance=params.relevance,
                notes=params.notes,
            )
            if not updated:
                return json_error(f"Evidence item not found: {params.evidence_id}")
            return json_response(db.get_evidence(params.evidence_id))

        return await run_with_db(deps, _work)

    @mcp.tool(
        name="evidence_remove",
        annotations=deps.write_tool_annotations("Remove Evidence Item"),
    )
    async def evidence_remove(params: EvidenceRemoveInput) -> str:
        """Remove an evidence item by ID."""

        def _work(db: Any) -> str:
            removed = db.remove_evidence(params.evidence_id)
            if not removed:
                return json_error(f"Evidence item not found: {params.evidence_id}")
            return json_response({"removed": params.evidence_id})

        return await run_with_db(deps, _work)

    @mcp.tool(
        name="evidence_verify",
        annotations=deps.write_tool_annotations("Verify Evidence Quotes"),
    )
    async def evidence_verify() -> str:
        """Re-verify all evidence quotes against source email body text."""
        return await run_with_db(deps, lambda db: json_response(db.verify_evidence_quotes()))


def _register_evidence_export_tools(mcp: Any, deps: ToolDepsProto) -> None:
    """Register the evidence export tools without coupling it to sibling tool modules."""

    @mcp.tool(
        name="evidence_export",
        annotations=deps.idempotent_write_annotations("Export Evidence Report"),
    )
    async def evidence_export(params: EvidenceExportInput) -> str:
        """Export the evidence collection as an HTML report or CSV file."""

        def _work(db: Any) -> str:
            from ..evidence_exporter import EvidenceExporter

            return json_response(
                EvidenceExporter(db).export_file(
                    output_path=params.output_path,
                    fmt=params.format,
                    min_relevance=params.min_relevance,
                    category=params.category,
                )
            )

        return await run_with_db(deps, _work)

    @mcp.tool(
        name="evidence_overview",
        annotations=deps.tool_annotations("Evidence Overview"),
    )
    async def evidence_overview(params: EvidenceOverviewInput) -> str:
        """Evidence statistics and category breakdown in one call.

        Returns total items, verified/unverified counts, breakdown by category
        and relevance level, plus all category counts.
        """

        def _work(db: Any) -> str:
            stats = db.evidence_stats(
                category=params.category,
                min_relevance=params.min_relevance,
            )
            categories = db.evidence_categories()
            total = stats.get("total", 0)
            verified = stats.get("verified", 0)
            payload: dict[str, Any] = {
                "summary": {
                    "total_items": total,
                    "verified": verified,
                    "unverified": stats.get("unverified", 0),
                    "verification_rate": f"{verified / total:.0%}" if total > 0 else "N/A",
                },
                "stats": stats,
                "categories": categories,
            }
            if total == 0:
                payload["message"] = "No evidence collected yet. Use evidence_add to start."
            return json_response(payload)

        return await run_with_db(deps, _work)

    @mcp.tool(
        name="evidence_add_batch",
        annotations=deps.write_tool_annotations("Batch Add Evidence Items"),
    )
    async def evidence_add_batch(params: EvidenceAddBatchInput) -> str:
        """Add multiple evidence items in one call (up to 20).

        Each item is independent - if one fails, others still succeed.
        """

        def _work(db: Any) -> str:
            added: list[dict] = []
            failed: list[dict] = []
            for item in params.items:
                try:
                    result = db.add_evidence(
                        email_uid=item.email_uid,
                        category=item.category,
                        key_quote=item.key_quote,
                        summary=item.summary,
                        relevance=item.relevance,
                        notes=item.notes,
                    )
                    added.append(result)
                except ValueError as exc:
                    failed.append({"email_uid": item.email_uid, "error": str(exc)})
            return json_response(
                {
                    "added": added,
                    "failed": failed,
                    "total_added": len(added),
                    "total_failed": len(failed),
                }
            )

        return await run_with_db(deps, _work)
