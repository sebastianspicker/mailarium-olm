"""Diagnostic and maintenance MCP tools."""

from __future__ import annotations

import logging
from typing import Any

from ..models.analysis import EmailAdminInput
from .search import invalidate_mcp_singletons
from .utils import ToolDepsProto, json_error, json_response

logger = logging.getLogger(__name__)


async def email_diagnostics(deps: ToolDepsProto) -> str:
    """Return resolved runtime settings, embedder backend state, and sparse index status."""

    def _run() -> str:
        from mailarium.platform.settings import get_settings, resolve_runtime_summary

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
            with db.operation():
                info["sparse_vector_count"] = db.sparse.sparse_vector_count()
                info.update(db.diagnostics.content_diagnostics())
                info["qa_readiness"] = db.diagnostics.qa_readiness_summary()
        try:
            sparse_idx = retriever.sparse_index
            if sparse_idx:
                info["sparse_index_built"] = sparse_idx.is_built
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
            invalidate_mcp_singletons(deps)
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
            invalidate_mcp_singletons(deps)
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
            invalidate_mcp_singletons(deps)
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
            invalidate_mcp_singletons(deps)
            return json_response(result)
        except Exception as exc:
            return json_error(f"Analytics reingestion failed: {type(exc).__name__}")

    return await deps.offload(_run)


def register(mcp_instance: Any, deps: ToolDepsProto) -> None:
    """Register admin tools."""

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
