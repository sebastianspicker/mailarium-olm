"""Filtered-search helper logic for the email retriever."""
# pylint: disable=too-many-arguments,too-many-locals

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .result_filters import _deduplicate_by_email, _normalize_filter
from .retrieval_policy import RetrievalPolicy, apply_scope_context, resolve_retrieval_policy

if TYPE_CHECKING:
    from .retriever import EmailRetriever, SearchResult, _SearchFilters, _SearchPlan
    from .retriever_models import FilteredSearchRequest

_MAX_FETCH_SIZE = 10_000
_MAX_FETCH_ATTEMPTS = 6


@dataclass(frozen=True, slots=True)
class _PreparedSearchDebugContext:
    """Carry expansion and semantic-filter diagnostics as one value."""

    semantic_requested: bool
    semantic_errors: list[dict]
    allowed_uids: set[str] | None
    normalized_query: str
    expansion_debug: dict[str, Any]
    expansion_suffix: str
    expansion_status: str


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
    retriever: EmailRetriever, request: FilteredSearchRequest
) -> tuple[_SearchPlan | None, _SearchFilters]:
    """Normalize filtered-search inputs and derive an execution plan."""
    semantic_filter_requested = request.topic_id is not None or request.cluster_id is not None
    configured_scope = getattr(getattr(retriever, "settings", None), "rag_scope", "general")
    if not isinstance(configured_scope, str):
        configured_scope = "general"
    requested_scope = configured_scope if request.scope is None else request.scope
    retrieval_policy = resolve_retrieval_policy(request.query, requested_scope)
    allowed_uids = retriever._resolve_allowed_uids(topic_id=request.topic_id, cluster_id=request.cluster_id)
    semantic_filter_errors = list(
        getattr(
            retriever,
            "last_semantic_filter_errors",
            getattr(retriever, "_last_semantic_filter_errors", []),
        )
        or []
    )
    failure = _semantic_filter_failure(
        retriever,
        request,
        retrieval_policy,
        allowed_uids,
        semantic_filter_errors,
    )
    if failure is not None:
        return failure
    normalized_query, expansion_debug, expansion_suffix, expansion_status = _expanded_query_state(
        retriever, request, retrieval_policy
    )
    filters = _normalized_filters(request, allowed_uids)
    retriever._validate_filtered_search(top_k=request.top_k, min_score=request.min_score, filters=filters)
    plan = retriever._build_search_plan(
        apply_scope_context(normalized_query, retrieval_policy.scope),
        normalized_query,
        request.top_k,
        filters,
        rerank=request.rerank,
        hybrid=request.hybrid,
        retrieval_policy=retrieval_policy,
    )
    _record_prepared_search_debug(
        retriever,
        request,
        plan,
        filters,
        retrieval_policy,
        _PreparedSearchDebugContext(
            semantic_requested=semantic_filter_requested,
            semantic_errors=semantic_filter_errors,
            allowed_uids=allowed_uids,
            normalized_query=normalized_query,
            expansion_debug=expansion_debug,
            expansion_suffix=expansion_suffix,
            expansion_status=expansion_status,
        ),
    )
    return plan, filters


def _semantic_filter_failure(
    retriever: EmailRetriever,
    request: FilteredSearchRequest,
    retrieval_policy: RetrievalPolicy,
    allowed_uids: set[str] | None,
    errors: list[dict],
) -> tuple[_SearchPlan | None, _SearchFilters] | None:
    requested = request.topic_id is not None or request.cluster_id is not None
    if requested and allowed_uids is None and not errors:
        errors.append(
            {
                "filter": "topic_or_cluster",
                "value": {"topic_id": request.topic_id, "cluster_id": request.cluster_id},
                "error_type": "SemanticFilterUnavailable",
                "message": "SQLite email database is not available for semantic filter resolution.",
            }
        )
    if not requested or (not errors and allowed_uids):
        return None
    retriever._set_last_search_debug(_semantic_failure_debug(request, retrieval_policy, errors))
    return None, _empty_semantic_filter_filters(
        has_attachments=request.has_attachments,
        priority=request.priority,
        min_score=request.min_score,
        is_calendar=request.is_calendar,
    )


def _semantic_failure_debug(
    request: FilteredSearchRequest,
    retrieval_policy: RetrievalPolicy,
    errors: list[dict],
) -> dict:
    """Create stable debug data for a failed or empty semantic filter resolution."""
    debug = {
        "original_query": request.query,
        "executed_query": apply_scope_context(request.query, retrieval_policy.scope),
        "used_query_expansion": False,
        "query_expansion_suffix": "",
        "expand_query_requested": bool(request.expand_query),
        "use_hybrid": False,
        "use_rerank": False,
        "top_k": int(request.top_k),
        "fetch_size": 0,
        "retrieval_policy": retrieval_policy.to_dict(),
        "semantic_filter_status": "error" if errors else "empty",
        "semantic_filter_errors": errors,
        "semantic_filter_uid_count": 0,
        "filter_summary": {
            "has_filters": True,
            "topic_or_cluster_constrained": True,
            "semantic_filter_error": bool(errors),
            "attachment_filter": bool(request.attachment_name or request.attachment_type),
        },
    }
    return debug


def _expanded_query_state(
    retriever: EmailRetriever,
    request: FilteredSearchRequest,
    retrieval_policy: RetrievalPolicy,
) -> tuple[str, dict, str, str]:
    """Expand the query and retain the exact diagnostic state used by callers."""
    normalized = (
        retriever._expand_query(request.query, scope=retrieval_policy.scope)
        if request.expand_query and request.query
        else request.query
    )
    debug = (
        dict(
            getattr(
                retriever,
                "last_query_expansion",
                getattr(retriever, "_last_query_expansion", {}),
            )
            or {}
        )
        if request.expand_query
        else {}
    )
    suffix = (
        normalized[len(request.query) :].strip() if normalized != request.query and normalized.startswith(request.query) else ""
    )
    status = str(debug.get("query_expansion_status") or "").strip() or (
        "expanded" if normalized != request.query else "unchanged"
    )
    return normalized, debug, suffix, status if request.expand_query else "not_requested"


def _normalized_filters(request: FilteredSearchRequest, allowed_uids: set[str] | None) -> _SearchFilters:
    """Normalize all text fields into the immutable runtime filter state."""
    from .retriever import _SearchFilters

    return _SearchFilters(
        sender=_normalize_filter(request.sender),
        date_from=_normalize_filter(request.date_from),
        date_to=_normalize_filter(request.date_to),
        subject=_normalize_filter(request.subject),
        folder=_normalize_filter(request.folder),
        cc=_normalize_filter(request.cc),
        to=_normalize_filter(request.to),
        bcc=_normalize_filter(request.bcc),
        has_attachments=request.has_attachments,
        priority=request.priority,
        min_score=request.min_score,
        email_type=(_normalize_filter(request.email_type) or "").lower() or None,
        allowed_uids=allowed_uids,
        category=_normalize_filter(request.category),
        is_calendar=request.is_calendar,
        attachment_name=_normalize_filter(request.attachment_name),
        attachment_type=_normalize_filter(request.attachment_type),
    )


def _record_prepared_search_debug(
    retriever: EmailRetriever,
    request: FilteredSearchRequest,
    plan: _SearchPlan,
    filters: _SearchFilters,
    retrieval_policy: RetrievalPolicy,
    context: _PreparedSearchDebugContext,
) -> None:
    """Persist the normalized search plan for diagnostics before retrieval begins."""
    debug = {
        "original_query": request.query,
        "executed_query": plan.query,
        "used_query_expansion": context.normalized_query != request.query,
        "query_expansion_status": context.expansion_status,
        "query_expansion_error_type": str(context.expansion_debug.get("query_expansion_error_type") or ""),
        "query_expansion_error": str(context.expansion_debug.get("query_expansion_error") or ""),
        "query_expansion_suffix": context.expansion_suffix,
        "expand_query_requested": bool(request.expand_query),
        "use_hybrid": bool(plan.use_hybrid),
        "use_rerank": bool(plan.use_rerank),
        "top_k": int(request.top_k),
        "fetch_size": int(plan.fetch_size),
        "retrieval_policy": retrieval_policy.to_dict(),
        "semantic_filter_status": "matched" if context.semantic_requested else "not_requested",
        "semantic_filter_errors": context.semantic_errors,
        "semantic_filter_uid_count": len(context.allowed_uids or set()),
        "filter_summary": {
            "has_filters": bool(filters.has_filters),
            "topic_or_cluster_constrained": context.allowed_uids is not None,
            "semantic_filter_error": bool(context.semantic_errors),
            "attachment_filter": bool(filters.attachment_name or filters.attachment_type),
        },
    }
    retriever._set_last_search_debug(debug)


def execute_filtered_search_impl(
    retriever: EmailRetriever,
    plan: _SearchPlan,
    filters: _SearchFilters,
) -> list[SearchResult]:
    """Fetch, filter, and deduplicate candidates until the requested result limit is met."""
    fetch_size = plan.fetch_size
    query_embedding: list[list[float]] | None = None
    deduped: list[SearchResult] = []
    for _ in range(_MAX_FETCH_ATTEMPTS):
        raw_candidates, raw_count, query_embedding = collect_candidates_impl(
            retriever,
            plan.query,
            plan.lexical_query,
            fetch_size,
            plan.use_hybrid,
            query_embedding,
            plan.retrieval_policy,
        )
        deduped = retriever._post_process_candidates(plan, filters, raw_candidates)
        if len(deduped) >= plan.top_k:
            return deduped[: plan.top_k]
        if raw_count < fetch_size or fetch_size >= _MAX_FETCH_SIZE:
            return deduped[: plan.top_k]
        fetch_size = min(fetch_size * 2, _MAX_FETCH_SIZE)
    return deduped[: plan.top_k]


def collect_candidates_impl(
    retriever: EmailRetriever,
    query: str,
    lexical_query: str,
    fetch_size: int,
    use_hybrid: bool,
    query_embedding: list[list[float]] | None,
    retrieval_policy: RetrievalPolicy,
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
        raw_candidates = retriever._merge_hybrid(
            lexical_query,
            raw_candidates,
            fetch_size,
            retrieval_policy=retrieval_policy,
        )
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
