"""Core search MCP tools (moved from mcp_server.py)."""

from __future__ import annotations

from typing import Any

from ..formatting import format_triage_results
from ..mcp_models import (
    EmailAnswerContextInput,
    EmailIngestInput,
    EmailSearchStructuredInput,
    EmailTriageInput,
    ListSendersInput,
)
from ..repo_paths import normalize_local_path
from .search_answer_context import build_answer_context
from .utils import ToolDepsProto, get_deps, json_error, json_response, run_with_retriever

# Thread-safety note: _deps is written once during single-threaded module
# registration (register_all) at import time, then only read by tool handlers.
# No lock needed — the write happens-before any tool call.
_deps: ToolDepsProto | None = None


def _d() -> ToolDepsProto:
    """Return the module-level deps, asserting it was set by ``register()``."""
    return get_deps(_deps)


_FILTER_FIELDS = [
    "sender",
    "subject",
    "folder",
    "cc",
    "to",
    "bcc",
    "has_attachments",
    "priority",
    "email_type",
    "date_from",
    "date_to",
    "min_score",
    "topic_id",
    "cluster_id",
    "category",
    "is_calendar",
    "attachment_name",
    "attachment_type",
]
_BOOL_FIELDS = ["rerank", "hybrid", "expand_query"]


def _build_search_kwargs(params: EmailSearchStructuredInput) -> dict[str, Any]:
    """Build search_filtered kwargs from structured input, skipping None values."""
    kwargs: dict = {"query": params.query, "top_k": params.top_k}
    for field in _FILTER_FIELDS:
        value = getattr(params, field)
        if value is not None:
            kwargs[field] = value
    for field in _BOOL_FIELDS:
        if getattr(params, field):
            kwargs[field] = True
    return kwargs


async def email_answer_context(params: EmailAnswerContextInput) -> str:
    """Build an answer-oriented evidence bundle for a natural-language question."""
    return await build_answer_context(_d(), params)


async def email_list_senders(params: ListSendersInput) -> str:
    """List all unique senders in the email archive, sorted by frequency.

    Useful for discovering who is in the archive before searching for
    specific conversations. Returns sender name, email, and message count.
    """
    deps = _d()

    def _run() -> str:
        r = deps.get_retriever()
        senders = r.list_senders(limit=params.limit)
        payload: dict[str, Any] = {
            "count": len(senders),
            "senders": senders,
        }
        if not senders:
            payload["message"] = "No senders found. The archive may be empty."
        return json_response(payload)

    return await deps.offload(_run)


async def email_stats() -> str:
    """Get statistics about the email archive.

    Returns total email count, date range, number of unique senders,
    and folder distribution. Useful for understanding the scope of the
    archive before searching.
    """
    return await run_with_retriever(_d(), lambda r: json_response(r.stats()))


async def email_search_structured(params: EmailSearchStructuredInput) -> str:
    """The most powerful search tool — combines semantic query with metadata filters.

    Supports filters: sender, date range, folder, to, cc, bcc, attachments,
    priority, topic, cluster. Returns structured JSON. Also supports reranking,
    hybrid BM25 search, and query expansion. For simple unfiltered queries,
    email_search is faster.
    """
    deps = _d()

    def _run() -> str:
        from ..config import get_settings

        settings = get_settings()
        r = deps.get_retriever()
        effective_top_k = min(params.top_k, settings.mcp_max_search_results)
        search_kwargs = _build_search_kwargs(params)
        search_kwargs["top_k"] = effective_top_k
        results = r.search_filtered(**search_kwargs)
        scan_meta = None
        if params.scan_id:
            from ..scan_session import filter_seen

            results, scan_meta = filter_seen(params.scan_id, results)
        payload = r.serialize_results(params.query, results)
        debug = getattr(r, "last_search_debug", getattr(r, "_last_search_debug", None))
        if isinstance(debug, dict) and debug:
            retrieval_diagnostics: dict[str, Any] = {}
            original_query = str(debug.get("original_query") or "").strip()
            executed_query = str(debug.get("executed_query") or "").strip()
            if original_query:
                retrieval_diagnostics["original_query"] = original_query
            if executed_query:
                retrieval_diagnostics["executed_query"] = executed_query
            if "expand_query_requested" in debug:
                retrieval_diagnostics["expand_query_requested"] = bool(debug.get("expand_query_requested"))
            if "used_query_expansion" in debug:
                retrieval_diagnostics["used_query_expansion"] = bool(debug.get("used_query_expansion"))
            expansion_suffix = str(debug.get("query_expansion_suffix") or "").strip()
            if expansion_suffix:
                retrieval_diagnostics["query_expansion_suffix"] = expansion_suffix
            if retrieval_diagnostics:
                payload["retrieval_diagnostics"] = retrieval_diagnostics
        payload["top_k"] = effective_top_k
        payload["filters"] = {
            "sender": params.sender,
            "subject": params.subject,
            "folder": params.folder,
            "cc": params.cc,
            "to": params.to,
            "bcc": params.bcc,
            "has_attachments": params.has_attachments,
            "priority": params.priority,
            "email_type": params.email_type,
            "date_from": params.date_from,
            "date_to": params.date_to,
            "min_score": params.min_score,
            "rerank": params.rerank,
            "hybrid": params.hybrid,
            "topic_id": params.topic_id,
            "cluster_id": params.cluster_id,
            "expand_query": params.expand_query,
            "attachment_name": params.attachment_name,
            "attachment_type": params.attachment_type,
            "category": params.category,
            "is_calendar": params.is_calendar,
        }
        payload["model"] = settings.embedding_model
        if scan_meta:
            payload["_scan"] = scan_meta
        if effective_top_k < params.top_k:
            payload["_capped"] = {
                "requested": params.top_k,
                "effective": effective_top_k,
                "profile": settings.mcp_model_profile,
            }
        return json_response(payload)

    return await deps.offload(_run)


async def email_list_folders() -> str:
    """List all folders in the email archive with email counts.

    Returns a sorted list of folder names and the number of emails in each.
    Useful for understanding archive structure before scoping a search.
    """
    deps = _d()

    def _run() -> str:
        r = deps.get_retriever()
        folders = r.list_folders()
        payload: dict[str, Any] = {
            "count": len(folders),
            "folders": folders,
        }
        if not folders:
            payload["message"] = "No folders found. The archive may be empty."
        return json_response(payload)

    return await deps.offload(_run)


async def email_ingest(params: EmailIngestInput) -> str:
    """Ingest an Outlook .olm export into the email vector database.

    Parses the archive, chunks each email, embeds the chunks, and stores
    them in ChromaDB. Already-indexed emails are skipped automatically.
    """

    def _run() -> str:
        from ..ingest import ingest

        try:
            stats = ingest(
                olm_path=params.olm_path,
                chromadb_path=params.chromadb_path,
                sqlite_path=params.sqlite_path,
                batch_size=params.batch_size,
                max_emails=params.max_emails,
                dry_run=params.dry_run,
                extract_attachments=params.extract_attachments,
                extract_entities=params.extract_entities,
                embed_images=params.embed_images,
                incremental=params.incremental,
                timing=params.timing,
            )
        except FileNotFoundError:
            return json_error(f"OLM file not found: {params.olm_path}")
        except Exception as exc:
            return json_error(f"Ingestion failed: {type(exc).__name__}: {exc}")

        payload: dict[str, Any] = dict(stats)

        # Invalidate cached singletons only when ingestion targeted the active
        # runtime archive. Ingesting into an alternate archive is explicit and
        # does not silently retarget future searches in this server process.
        if not params.dry_run:
            import src.mcp_server as _server

            active_chromadb_path, active_sqlite_path = _server._resolved_runtime_paths()
            target_chromadb_path = params.chromadb_path or active_chromadb_path
            target_sqlite_path = params.sqlite_path or active_sqlite_path
            target_is_active_archive = normalize_local_path(
                target_chromadb_path, field_name="chromadb_path"
            ) == normalize_local_path(active_chromadb_path, field_name="chromadb_path") and normalize_local_path(
                target_sqlite_path, field_name="sqlite_path"
            ) == normalize_local_path(active_sqlite_path, field_name="sqlite_path")
            if target_is_active_archive:
                invalidate_mcp_singletons()
            else:
                payload["runtime_archive_unchanged"] = True
                payload["searches_continue_against_active_archive"] = True
                payload["active_archive_switch_required"] = True
                payload["active_archive"] = {
                    "chromadb_path": active_chromadb_path,
                    "sqlite_path": active_sqlite_path,
                }
                payload["ingest_target_archive"] = {
                    "chromadb_path": target_chromadb_path,
                    "sqlite_path": target_sqlite_path,
                }

        return json_response(payload)

    return await _d().offload(_run)


def invalidate_mcp_singletons() -> None:
    """Reset cached retriever and email_db singletons after archive mutations.

    The retriever caches BM25/sparse indices, query embeddings, and the
    ChromaDB collection reference. After ingest or maintenance writes these
    caches are stale. Re-creating the singletons forces a fresh load.
    """
    import src.mcp_server as _server

    with _server._retriever_lock:
        _server._retriever = None
    with _server._email_db_lock:
        _server._email_db = None


def _invalidate_singletons_after_ingest() -> None:
    """Backward-compatible alias for older imports/tests."""
    invalidate_mcp_singletons()


def _archive_stats_hint(retriever: Any) -> dict[str, Any]:
    """Compact archive overview for triage results (total emails, date range, senders)."""
    try:
        s = retriever.stats()
        dr = s.get("date_range", {})
        return {
            "total_emails": s.get("total_emails", 0),
            "date_range": f"{dr.get('earliest', '?')} to {dr.get('latest', '?')}",
            "unique_senders": s.get("unique_senders", 0),
        }
    except Exception:
        return {}


async def email_triage(params: EmailTriageInput) -> str:
    """Fast triage scan: ultra-compact results, high recall, up to 100 emails.

    Returns minimal JSON per result (uid, sender, date, subject, score, preview).
    Always uses query expansion for maximum recall. Issue 3-5 triage calls
    with different queries in one message for pseudo-parallel scanning.
    """
    deps = _d()

    def _run() -> str:
        from ..config import get_settings

        settings = get_settings()
        r = deps.get_retriever()
        effective_top_k = min(params.top_k, settings.mcp_max_triage_results)
        kwargs: dict = {"query": params.query, "top_k": effective_top_k, "expand_query": True}
        if params.sender:
            kwargs["sender"] = params.sender
        if params.date_from:
            kwargs["date_from"] = params.date_from
        if params.date_to:
            kwargs["date_to"] = params.date_to
        if params.folder:
            kwargs["folder"] = params.folder
        if params.has_attachments is not None:
            kwargs["has_attachments"] = params.has_attachments
        if params.hybrid:
            kwargs["hybrid"] = True
        results = r.search_filtered(**kwargs)
        scan_meta = None
        if params.scan_id:
            from ..scan_session import filter_seen

            results, scan_meta = filter_seen(params.scan_id, results)
        triage = format_triage_results(results, preview_chars=params.preview_chars)
        archive = _archive_stats_hint(r)
        payload = {
            "query": params.query,
            "count": len(triage),
            "archive": archive,
            "results": triage,
        }
        if scan_meta:
            payload["_scan"] = scan_meta
        if effective_top_k < params.top_k:
            payload["_capped"] = {
                "requested": params.top_k,
                "effective": effective_top_k,
                "profile": settings.mcp_model_profile,
            }
        return json_response(payload)

    return await deps.offload(_run)


def register(mcp_instance: Any, deps: ToolDepsProto) -> None:
    """Register core search tools."""
    global _deps
    _deps = deps

    ann = deps.tool_annotations
    # email_search removed — subsumed by email_search_structured (no filters = same)
    mcp_instance.tool(name="email_list_senders", annotations=ann("List Email Senders"))(email_list_senders)
    mcp_instance.tool(name="email_stats", annotations=ann("Email Archive Stats"))(email_stats)
    mcp_instance.tool(name="email_answer_context", annotations=ann("Question-to-Evidence Context"))(email_answer_context)
    mcp_instance.tool(name="email_search_structured", annotations=ann("Search Emails (Structured JSON)"))(email_search_structured)
    mcp_instance.tool(name="email_list_folders", annotations=ann("List Email Folders"))(email_list_folders)
    mcp_instance.tool(name="email_ingest", annotations=deps.idempotent_write_annotations("Ingest Email Archive"))(email_ingest)
    # email_search_thread removed — subsumed by email_thread_lookup in threads.py
    mcp_instance.tool(name="email_triage", annotations=ann("Fast Triage Scan"))(email_triage)
