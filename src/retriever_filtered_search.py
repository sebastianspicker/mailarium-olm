"""Filtered-search helper logic for the email retriever."""
# pylint: disable=too-many-arguments,too-many-locals

from __future__ import annotations

from typing import TYPE_CHECKING

from .query_expander import legal_support_query_profile
from .result_filters import _deduplicate_by_email, _normalize_filter

if TYPE_CHECKING:
    from .retriever import EmailRetriever, SearchResult, _SearchFilters, _SearchPlan

_MAX_FETCH_SIZE = 10_000
_MAX_FETCH_ATTEMPTS = 6


def _empty_semantic_filter_filters(
    *,
    has_attachments: bool | None,
    priority: int | None,
    min_score: float | None,
    is_calendar: bool | None,
) -> _SearchFilters:
    from .retriever import _SearchFilters

    return _SearchFilters(
        sender=None,
        date_from=None,
        date_to=None,
        subject=None,
        folder=None,
        cc=None,
        to=None,
        bcc=None,
        has_attachments=has_attachments,
        priority=priority,
        min_score=min_score,
        email_type=None,
        allowed_uids=None,
        category=None,
        is_calendar=is_calendar,
        attachment_name=None,
        attachment_type=None,
    )


def prepare_filtered_search_impl(
    retriever: EmailRetriever,
    *,
    query: str,
    top_k: int,
    sender: str | None,
    date_from: str | None,
    date_to: str | None,
    subject: str | None,
    folder: str | None,
    cc: str | None,
    to: str | None,
    bcc: str | None,
    has_attachments: bool | None,
    priority: int | None,
    min_score: float | None,
    email_type: str | None,
    rerank: bool,
    hybrid: bool,
    topic_id: int | None,
    cluster_id: int | None,
    expand_query: bool,
    category: str | None,
    is_calendar: bool | None,
    attachment_name: str | None,
    attachment_type: str | None,
) -> tuple[_SearchPlan | None, _SearchFilters]:
    """Normalize filtered-search inputs and derive an execution plan."""
    from .retriever import _SearchFilters

    semantic_filter_requested = topic_id is not None or cluster_id is not None
    legal_support_profile = legal_support_query_profile(query)
    allowed_uids = retriever._resolve_allowed_uids(topic_id=topic_id, cluster_id=cluster_id)
    semantic_filter_errors = list(getattr(retriever, "_last_semantic_filter_errors", []) or [])
    if semantic_filter_requested and allowed_uids is None and not semantic_filter_errors:
        semantic_filter_errors = [
            {
                "filter": "topic_or_cluster",
                "value": {"topic_id": topic_id, "cluster_id": cluster_id},
                "error_type": "SemanticFilterUnavailable",
                "message": "SQLite email database is not available for semantic filter resolution.",
            }
        ]
    if semantic_filter_requested and (semantic_filter_errors or not allowed_uids):
        retriever._set_last_search_debug(
            {
                "original_query": query,
                "executed_query": query,
                "used_query_expansion": False,
                "query_expansion_suffix": "",
                "expand_query_requested": bool(expand_query),
                "use_hybrid": False,
                "use_rerank": False,
                "top_k": int(top_k),
                "fetch_size": 0,
                "legal_support_profile": legal_support_profile,
                "semantic_filter_status": "error" if semantic_filter_errors else "empty",
                "semantic_filter_errors": semantic_filter_errors,
                "semantic_filter_uid_count": 0,
                "filter_summary": {
                    "has_filters": True,
                    "topic_or_cluster_constrained": True,
                    "semantic_filter_error": bool(semantic_filter_errors),
                    "attachment_filter": bool(attachment_name or attachment_type),
                },
            }
        )
        return None, _empty_semantic_filter_filters(
            has_attachments=has_attachments,
            priority=priority,
            min_score=min_score,
            is_calendar=is_calendar,
        )

    normalized_query = retriever._expand_query(query) if expand_query and query else query
    expansion_debug = dict(getattr(retriever, "_last_query_expansion", {}) or {}) if expand_query else {}
    expansion_suffix = ""
    if normalized_query != query and normalized_query.startswith(query):
        expansion_suffix = normalized_query[len(query) :].strip()
    query_expansion_status = "not_requested"
    if expand_query:
        query_expansion_status = str(expansion_debug.get("query_expansion_status") or "").strip() or (
            "expanded" if normalized_query != query else "unchanged"
        )
    filters = _SearchFilters(
        sender=_normalize_filter(sender),
        date_from=_normalize_filter(date_from),
        date_to=_normalize_filter(date_to),
        subject=_normalize_filter(subject),
        folder=_normalize_filter(folder),
        cc=_normalize_filter(cc),
        to=_normalize_filter(to),
        bcc=_normalize_filter(bcc),
        has_attachments=has_attachments,
        priority=priority,
        min_score=min_score,
        email_type=(_normalize_filter(email_type) or "").lower() or None,
        allowed_uids=allowed_uids,
        category=_normalize_filter(category),
        is_calendar=is_calendar,
        attachment_name=_normalize_filter(attachment_name),
        attachment_type=_normalize_filter(attachment_type),
    )
    retriever._validate_filtered_search(top_k=top_k, min_score=min_score, filters=filters)
    plan = retriever._build_search_plan(normalized_query, top_k, filters, rerank=rerank, hybrid=hybrid)
    retriever._set_last_search_debug(
        {
            "original_query": query,
            "executed_query": normalized_query,
            "used_query_expansion": normalized_query != query,
            "query_expansion_status": query_expansion_status,
            "query_expansion_error_type": str(expansion_debug.get("query_expansion_error_type") or ""),
            "query_expansion_error": str(expansion_debug.get("query_expansion_error") or ""),
            "query_expansion_suffix": expansion_suffix,
            "expand_query_requested": bool(expand_query),
            "use_hybrid": bool(plan.use_hybrid),
            "use_rerank": bool(plan.use_rerank),
            "top_k": int(top_k),
            "fetch_size": int(plan.fetch_size),
            "legal_support_profile": legal_support_profile,
            "semantic_filter_status": "matched" if semantic_filter_requested else "not_requested",
            "semantic_filter_errors": semantic_filter_errors,
            "semantic_filter_uid_count": len(allowed_uids or set()),
            "filter_summary": {
                "has_filters": bool(filters.has_filters),
                "topic_or_cluster_constrained": allowed_uids is not None,
                "semantic_filter_error": bool(semantic_filter_errors),
                "attachment_filter": bool(filters.attachment_name or filters.attachment_type),
            },
        }
    )
    return plan, filters


def execute_filtered_search_impl(
    retriever: EmailRetriever,
    plan: _SearchPlan,
    filters: _SearchFilters,
) -> list[SearchResult]:
    """Run the iterative candidate fetch loop for a filtered search."""
    fetch_size = plan.fetch_size
    query_embedding: list[list[float]] | None = None
    deduped: list[SearchResult] = []
    for _ in range(_MAX_FETCH_ATTEMPTS):
        raw_candidates, raw_count, query_embedding = collect_candidates_impl(
            retriever,
            plan.query,
            fetch_size,
            plan.use_hybrid,
            query_embedding,
        )
        deduped = post_process_candidates_impl(retriever, plan, filters, raw_candidates)
        if len(deduped) >= plan.top_k:
            return deduped[: plan.top_k]
        if raw_count < fetch_size or fetch_size >= _MAX_FETCH_SIZE:
            return deduped[: plan.top_k]
        fetch_size = min(fetch_size * 2, _MAX_FETCH_SIZE)
    return deduped[: plan.top_k]


def collect_candidates_impl(
    retriever: EmailRetriever,
    query: str,
    fetch_size: int,
    use_hybrid: bool,
    query_embedding: list[list[float]] | None,
) -> tuple[list[SearchResult], int, list[list[float]] | None]:
    """Collect dense candidates and optionally merge hybrid keyword results."""
    if fetch_size <= retriever.MAX_TOP_K:
        raw_candidates = retriever.search(query, top_k=fetch_size)
    else:
        if query_embedding is None:
            query_embedding = retriever._encode_query(query)
        raw_candidates = retriever._query_with_embedding(query_embedding, fetch_size)
    raw_count = len(raw_candidates)
    if use_hybrid:
        raw_candidates = retriever._merge_hybrid(query, raw_candidates, fetch_size)
    return raw_candidates, raw_count, query_embedding


def post_process_candidates_impl(
    retriever: EmailRetriever,
    plan: _SearchPlan,
    filters: _SearchFilters,
    raw_candidates: list[SearchResult],
) -> list[SearchResult]:
    """Apply filters, deduplication, reranking, and post-rerank trimming."""
    filtered = filters.apply(raw_candidates, use_rerank=plan.use_rerank)
    deduped = _deduplicate_by_email(filtered)
    if plan.use_rerank and deduped:
        deduped = retriever._apply_rerank(plan.query, deduped, plan.top_k)
        if filters.min_score is not None:
            deduped = [result for result in deduped if (1.0 - result.distance) >= filters.min_score]
    return deduped
