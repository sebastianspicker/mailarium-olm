"""Core MCP tools for email search, triage, archive inspection, and ingestion."""
# pylint: disable=too-many-branches,too-many-locals,too-many-statements

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
# No lock needed - the write happens-before any tool call.
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
    "scope",
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


def _retrieval_diagnostics(debug: object) -> dict[str, Any]:
    """Project the stable public diagnostics fields from a retriever debug record."""
    if not isinstance(debug, dict) or not debug:
        return {}
    diagnostics: dict[str, Any] = {}
    _add_text_diagnostics(debug, diagnostics)
    _add_expansion_diagnostics(debug, diagnostics)
    _add_semantic_filter_diagnostics(debug, diagnostics)
    _add_nested_diagnostics(debug, diagnostics)
    return diagnostics


def _add_text_diagnostics(debug: dict[str, Any], diagnostics: dict[str, Any]) -> None:
    """Copy populated string diagnostics from a retriever debug record."""
    text_fields = (
        "original_query",
        "executed_query",
        "query_expansion_status",
        "query_expansion_error_type",
        "query_expansion_error",
        "query_expansion_suffix",
        "semantic_filter_status",
    )
    for field in text_fields:
        value = str(debug.get(field) or "").strip()
        if value:
            diagnostics[field] = value


def _add_expansion_diagnostics(debug: dict[str, Any], diagnostics: dict[str, Any]) -> None:
    """Copy query-expansion flags when the retriever reported them."""
    for field in ("expand_query_requested", "used_query_expansion"):
        if field in debug:
            diagnostics[field] = bool(debug[field])


def _add_semantic_filter_diagnostics(debug: dict[str, Any], diagnostics: dict[str, Any]) -> None:
    """Copy semantic-filter counts and errors when available."""
    if "semantic_filter_uid_count" in debug:
        diagnostics["semantic_filter_uid_count"] = int(debug.get("semantic_filter_uid_count") or 0)
    errors = debug.get("semantic_filter_errors")
    if isinstance(errors, list) and errors:
        diagnostics["semantic_filter_errors"] = errors


def _add_nested_diagnostics(debug: dict[str, Any], diagnostics: dict[str, Any]) -> None:
    """Copy nested policy and fusion diagnostics without exposing mutable records."""
    policy = debug.get("retrieval_policy")
    if isinstance(policy, dict):
        diagnostics["retrieval_policy"] = dict(policy)
    fusion = debug.get("fusion")
    if isinstance(fusion, dict):
        diagnostics["fusion"] = dict(fusion)


def _structured_filters(params: EmailSearchStructuredInput) -> dict[str, Any]:
    """Return every structured-search filter, including explicit false values."""
    output_order = (
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
        "rerank",
        "hybrid",
        "topic_id",
        "cluster_id",
        "expand_query",
        "attachment_name",
        "attachment_type",
        "category",
        "is_calendar",
        "scope",
    )
    return {field: getattr(params, field) for field in output_order}


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
    """Combine semantic retrieval with metadata filters in one search request.

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
        diagnostics = _retrieval_diagnostics(getattr(r, "last_search_debug", getattr(r, "_last_search_debug", None)))
        if diagnostics:
            payload["retrieval_diagnostics"] = diagnostics
        payload["top_k"] = effective_top_k
        payload["filters"] = _structured_filters(params)
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
    them in USearch vector index. Already-indexed emails are skipped automatically.
    """

    def _run() -> str:
        from ..ingest import ingest

        try:
            stats = ingest(
                olm_path=params.olm_path,
                vector_index_path=params.vector_index_path,
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
        except Exception as exc:  # pylint: disable=broad-exception-caught
            return json_error(f"Ingestion failed: {type(exc).__name__}: {exc}")

        payload: dict[str, Any] = dict(stats)

        # Invalidate cached singletons only when ingestion targeted the active
        # runtime archive. Ingesting into an alternate archive is explicit and
        # does not silently retarget future searches in this server process.
        if params.dry_run:
            payload["ingest_archive_status"] = "dry_run"
        else:
            import mailarium.mcp_server as _server

            active_vector_index_path, active_sqlite_path = _server._resolved_runtime_paths()
            target_vector_index_path = params.vector_index_path or active_vector_index_path
            target_sqlite_path = params.sqlite_path or active_sqlite_path
            target_is_active_archive = normalize_local_path(
                target_vector_index_path, field_name="vector_index_path"
            ) == normalize_local_path(active_vector_index_path, field_name="vector_index_path") and normalize_local_path(
                target_sqlite_path, field_name="sqlite_path"
            ) == normalize_local_path(active_sqlite_path, field_name="sqlite_path")
            if target_is_active_archive:
                invalidate_mcp_singletons()
                payload["ingest_archive_status"] = "active_archive_updated"
            else:
                payload["ingest_archive_status"] = "inactive_target_success"
                payload["runtime_archive_unchanged"] = True
                payload["searches_continue_against_active_archive"] = True
                payload["active_archive_switch_required"] = True
                payload["active_archive"] = {
                    "vector_index_path": active_vector_index_path,
                    "sqlite_path": active_sqlite_path,
                }
                payload["ingest_target_archive"] = {
                    "vector_index_path": target_vector_index_path,
                    "sqlite_path": target_sqlite_path,
                }

        return json_response(payload)

    return await _d().offload(_run)


def invalidate_mcp_singletons() -> None:
    """Reset every archive-backed singleton after archive mutations.

    The retriever caches BM25/sparse indices, query embeddings, and the
    USearch vector index collection reference. After ingest or maintenance writes these
    caches are stale. Re-creating the singletons forces a fresh load.
    """
    import mailarium.mcp_server as _server

    _server._reset_runtime_clients()


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
    except Exception:  # pylint: disable=broad-exception-caught
        return {}


async def email_triage(params: EmailTriageInput) -> str:
    """Fast triage scan: ultra-compact results, high recall, up to 100 emails.

    Returns minimal JSON per result (uid, sender, date, subject, score, preview).
    Always uses query expansion for maximum recall. Issue 3-5 triage calls
    with different queries in one message for pseudo-parallel scanning.
    """
    deps = _d()
    return await deps.offload(lambda: _run_triage(deps, params))


def _triage_search_kwargs(params: EmailTriageInput, top_k: int) -> dict[str, Any]:
    """Translate populated triage filters into retriever arguments and preserve explicit scope controls."""
    kwargs: dict[str, Any] = {"query": params.query, "top_k": top_k, "expand_query": True}
    for field in ("sender", "date_from", "date_to", "folder"):
        value = getattr(params, field)
        if value is not None and value != "":
            kwargs[field] = value
    if params.has_attachments is not None:
        kwargs["has_attachments"] = params.has_attachments
    if params.hybrid:
        kwargs["hybrid"] = True
    if params.scope is not None:
        kwargs["scope"] = params.scope
    return kwargs


def _run_triage(deps: ToolDepsProto, params: EmailTriageInput) -> str:
    """Bound triage retrieval by settings, apply optional scan filtering, and serialize archive diagnostics."""
    from ..config import get_settings

    settings = get_settings()
    retriever = deps.get_retriever()
    effective_top_k = min(params.top_k, settings.mcp_max_triage_results)
    results = retriever.search_filtered(**_triage_search_kwargs(params, effective_top_k))
    scan_meta = _apply_triage_scan(params.scan_id, results)
    if scan_meta is not None:
        results, scan_meta = scan_meta
    triage = format_triage_results(results, preview_chars=params.preview_chars)
    payload: dict[str, Any] = {
        "query": params.query,
        "count": len(triage),
        "archive": _archive_stats_hint(retriever),
        "results": triage,
    }
    _add_triage_metadata(payload, retriever, scan_meta, params.top_k, effective_top_k, settings.mcp_model_profile)
    return json_response(payload)


def _apply_triage_scan(scan_id: str | None, results: list[Any]) -> tuple[list[Any], Any] | None:
    """Apply triage scan while retaining source diagnostics."""
    if not scan_id:
        return None
    from ..scan_session import filter_seen

    return filter_seen(scan_id, results)


def _add_triage_metadata(
    payload: dict[str, Any], retriever: Any, scan_meta: Any, requested_top_k: int, effective_top_k: int, profile: str
) -> None:
    """Attach retrieval diagnostics and scan/cap metadata to a triage response."""
    diagnostics = _retrieval_diagnostics(getattr(retriever, "last_search_debug", getattr(retriever, "_last_search_debug", None)))
    if diagnostics:
        payload["retrieval_diagnostics"] = diagnostics
    if scan_meta:
        payload["_scan"] = scan_meta
    if effective_top_k < requested_top_k:
        payload["_capped"] = {"requested": requested_top_k, "effective": effective_top_k, "profile": profile}


def register(mcp_instance: Any, deps: ToolDepsProto) -> None:
    """Register core search tools."""
    global _deps  # pylint: disable=global-statement
    _deps = deps

    ann = deps.tool_annotations
    # email_search removed - subsumed by email_search_structured (no filters = same)
    mcp_instance.tool(name="email_list_senders", annotations=ann("List Email Senders"))(email_list_senders)
    mcp_instance.tool(name="email_stats", annotations=ann("Email Archive Stats"))(email_stats)
    mcp_instance.tool(name="email_answer_context", annotations=ann("Question-to-Evidence Context"))(email_answer_context)
    mcp_instance.tool(name="email_search_structured", annotations=ann("Search Emails (Structured JSON)"))(email_search_structured)
    mcp_instance.tool(name="email_list_folders", annotations=ann("List Email Folders"))(email_list_folders)
    mcp_instance.tool(name="email_ingest", annotations=deps.idempotent_write_annotations("Ingest Email Archive"))(email_ingest)
    # email_search_thread removed - subsumed by email_thread_lookup in threads.py
    mcp_instance.tool(name="email_triage", annotations=ann("Fast Triage Scan"))(email_triage)
