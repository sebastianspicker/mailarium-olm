"""Diagnostic and maintenance MCP tools."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import nullcontext
from typing import Any

from mailarium.archive._sql_validation import validate_sql_identifier as _validate_sql_identifier

from ..mcp_models import EmailAdminInput
from . import diagnostics_summary as summary_family
from .search import invalidate_mcp_singletons
from .utils import ToolDepsProto, get_deps, json_error, json_response

logger = logging.getLogger(__name__)

# Thread-safety note: _deps is written once during single-threaded module
# registration at import time, then only read by tool handlers.
_deps: ToolDepsProto | None = None


def _table_columns(db, table: str) -> set[str]:
    """Return known column names for *table*, or an empty set on failure."""
    conn = getattr(db, "conn", None)
    if conn is None:
        return set()
    try:
        safe_table = _validate_sql_identifier(table)
        rows = conn.execute("SELECT * FROM pragma_table_info(?)", (safe_table,)).fetchall()
    except sqlite3.Error:
        logger.debug("Diagnostics PRAGMA failed for table %s", table, exc_info=True)
        return set()
    return {str(row["name"] if not isinstance(row, tuple) else row[1]) for row in rows}


def _count_rows(db, query: str) -> dict[str, int]:
    """Calculate rows for bounded response decisions."""
    try:
        rows = db.conn.execute(query).fetchall()
    except sqlite3.Error:
        logger.debug("Diagnostics counter query failed: %s", query, exc_info=True)
        return {}
    return {str(row["label"]): int(row["count"]) for row in rows if row["label"]}


def _scalar_count(db, query: str) -> int:
    """Execute a scalar diagnostics query and degrade database errors or empty rows to zero."""
    try:
        row = db.conn.execute(query).fetchone()
    except sqlite3.Error:
        logger.debug("Diagnostics scalar query failed: %s", query, exc_info=True)
        return 0
    if not row:
        return 0
    return int(row[0] or 0)


def _rate(count: int, total: int) -> float:
    """Return a stable float rate, guarding zero denominators."""
    if total <= 0:
        return 0.0
    return count / total


def _qa_readiness_summary(db) -> dict[str, Any]:
    """Measure database-backed QA readiness using schema, row-count, and rate helpers."""
    return summary_family.qa_readiness_summary_impl(
        db,
        table_columns=_table_columns,
        scalar_count=_scalar_count,
        count_rows=_count_rows,
        rate=_rate,
    )


def _d() -> ToolDepsProto:
    """Return the module-level deps, asserting it was set by ``register()``."""
    return get_deps(_deps)


async def email_diagnostics(deps: ToolDepsProto) -> str:
    """Return resolved runtime settings, embedder backend state, and sparse index status."""

    def _run() -> str:
        from mailarium.config import get_settings, resolve_runtime_summary

        retriever = deps.get_retriever()
        settings = get_settings()
        db = deps.get_archive_database()
        info: dict = resolve_runtime_summary(settings)
        info["batch_size_setting"] = info["embedding_batch_size_setting"]
        multi = getattr(retriever, "embedder", None)
        if multi:
            summary_fn = getattr(multi, "runtime_summary", None)
            if callable(summary_fn):
                raw_summary = summary_fn()
            else:
                raw_summary = {
                    "model_name": getattr(multi, "model_name", None),
                    "device": str(getattr(multi, "device", "unknown")),
                    "batch_size": getattr(multi, "batch_size", None),
                    "load_mode": getattr(multi, "load_mode", None),
                    "backend": type(getattr(multi, "_model", multi)).__name__,
                    "has_sparse": getattr(multi, "has_sparse", False),
                }
            summary_key_map = {
                "model_name": "embedder_model_name",
                "backend": "embedder_backend",
                "device": "embedder_device",
                "batch_size": "embedder_batch_size",
                "load_mode": "embedder_load_mode",
                "has_sparse": "embedder_has_sparse",
            }
            for raw_key, value in raw_summary.items():
                mapped_key = summary_key_map.get(raw_key, f"embedder_{raw_key}")
                info[mapped_key] = value
        info["mcp_profile"] = settings.mcp_model_profile
        info["mcp_budget"] = {
            "max_body_chars": settings.mcp_max_body_chars,
            "max_response_tokens": settings.mcp_max_response_tokens,
            "max_full_body_chars": settings.mcp_max_full_body_chars,
            "max_json_response_chars": settings.mcp_max_json_response_chars,
            "max_triage_results": settings.mcp_max_triage_results,
            "max_search_results": settings.mcp_max_search_results,
        }
        info["sparse_vector_count"] = 0
        info["sparse_index_built"] = False
        if db:
            operation = getattr(db, "operation", None)
            with operation() if callable(operation) else nullcontext():
                count_method = getattr(db, "sparse_vector_count", None)
                if count_method:
                    info["sparse_vector_count"] = count_method()
                info["body_kind_counts"] = _count_rows(
                    db,
                    """SELECT body_kind AS label, COUNT(*) AS count
                       FROM emails
                       WHERE body_kind IS NOT NULL AND body_kind != ''
                       GROUP BY body_kind
                       ORDER BY count DESC""",
                )
                info["body_empty_reason_counts"] = _count_rows(
                    db,
                    """SELECT body_empty_reason AS label, COUNT(*) AS count
                       FROM emails
                       WHERE body_empty_reason IS NOT NULL AND body_empty_reason != ''
                       GROUP BY body_empty_reason
                       ORDER BY count DESC""",
                )
                info["recipient_identity_source_counts"] = _count_rows(
                    db,
                    """SELECT recipient_identity_source AS label, COUNT(*) AS count
                       FROM emails
                       WHERE recipient_identity_source IS NOT NULL AND recipient_identity_source != ''
                       GROUP BY recipient_identity_source
                       ORDER BY count DESC""",
                )
                info["reply_context_recovered_count"] = _scalar_count(
                    db,
                    """SELECT COUNT(*) FROM emails
                       WHERE reply_context_from IS NOT NULL AND reply_context_from != ''""",
                )
                info["message_segment_count"] = _scalar_count(db, "SELECT COUNT(*) FROM message_segments")
                info["emails_with_segments_count"] = _scalar_count(
                    db,
                    "SELECT COUNT(DISTINCT email_uid) FROM message_segments",
                )
                info["emails_with_inferred_thread_count"] = _scalar_count(
                    db,
                    """SELECT COUNT(*) FROM emails
                       WHERE inferred_parent_uid IS NOT NULL AND inferred_parent_uid != ''""",
                )
                info["qa_readiness"] = _qa_readiness_summary(db)
        try:
            sparse_idx = getattr(retriever, "_sparse_index", None)
            if sparse_idx:
                info["sparse_index_built"] = getattr(sparse_idx, "_built", False)
        except Exception:
            logger.debug("Sparse index diagnostics unavailable", exc_info=True)
        return json_response(info)

    return await deps.offload(_run)


async def email_reingest_bodies(deps: ToolDepsProto, olm_path: str, force: bool = False) -> str:
    """Re-parse OLM to backfill body_text/body_html for existing SQLite rows."""

    def _run() -> str:
        from mailarium.ingestion import reingest_bodies

        try:
            result = reingest_bodies(olm_path, force=force)
            invalidate_mcp_singletons()
            return json_response(result)
        except FileNotFoundError:
            return json_error(f"OLM file not found: {olm_path}")
        except Exception as exc:
            return json_error(f"Body reingestion failed: {type(exc).__name__}")

    return await deps.offload(_run)


async def email_reembed(deps: ToolDepsProto, batch_size: int = 100) -> str:
    """Re-chunk and re-embed all emails from corrected SQLite body text."""

    def _run() -> str:
        from mailarium.ingestion import reembed

        try:
            result = reembed(batch_size=batch_size)
            invalidate_mcp_singletons()
            return json_response(result)
        except Exception as exc:
            return json_error(f"Re-embedding failed: {type(exc).__name__}")

    return await deps.offload(_run)


async def email_reingest_metadata(deps: ToolDepsProto, olm_path: str) -> str:
    """Backfill v7 metadata for existing emails from an OLM archive."""

    def _run() -> str:
        from mailarium.ingestion import reingest_metadata_archive

        try:
            result = reingest_metadata_archive(olm_path)
            invalidate_mcp_singletons()
            return json_response(result)
        except FileNotFoundError:
            return json_error(f"OLM file not found: {olm_path}")
        except Exception as exc:
            return json_error(f"Metadata reingestion failed: {type(exc).__name__}")

    return await deps.offload(_run)


async def email_reingest_analytics(deps: ToolDepsProto) -> str:
    """Backfill language detection and sentiment analysis for all emails."""

    def _run() -> str:
        from mailarium.ingestion import reingest_analytics

        try:
            result = reingest_analytics()
            invalidate_mcp_singletons()
            return json_response(result)
        except Exception as exc:
            return json_error(f"Analytics reingestion failed: {type(exc).__name__}")

    return await deps.offload(_run)


def register(mcp_instance: Any, deps: ToolDepsProto) -> None:
    """Register admin tools."""
    global _deps
    _deps = deps

    @mcp_instance.tool(
        name="email_admin",
        annotations=deps.idempotent_write_annotations("Admin & Diagnostics"),
    )
    async def email_admin(params: EmailAdminInput) -> str:
        """Admin and diagnostic operations in one tool.

        action='diagnostics': show resolved runtime settings, embedder backend state, and MCP budgets.
        action='reingest_bodies': re-parse OLM bodies (requires olm_path).
        action='reembed': re-embed all chunks from SQLite body text.
        action='reingest_metadata': backfill v7 metadata (requires olm_path).
        action='reingest_analytics': backfill language/sentiment data.
        """
        if params.action == "diagnostics":
            return await email_diagnostics(deps)
        if params.action == "reingest_bodies":
            if not params.olm_path:
                return json_error("olm_path is required for reingest_bodies.")
            return await email_reingest_bodies(deps, params.olm_path, force=params.force)
        if params.action == "reembed":
            return await email_reembed(deps, batch_size=params.batch_size)
        if params.action == "reingest_metadata":
            if not params.olm_path:
                return json_error("olm_path is required for reingest_metadata.")
            return await email_reingest_metadata(deps, params.olm_path)
        if params.action == "reingest_analytics":
            return await email_reingest_analytics(deps)
        return json_error(
            f"Invalid action: {params.action}. Use 'diagnostics', 'reingest_bodies', "
            "'reembed', 'reingest_metadata', or 'reingest_analytics'."
        )
