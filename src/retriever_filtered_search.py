"""Filtered-search helper logic for the email retriever."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .result_filters import _deduplicate_by_email, _normalize_filter

if TYPE_CHECKING:
    from .retriever import EmailRetriever, SearchResult, _SearchFilters, _SearchPlan

_MAX_FETCH_SIZE = 10_000
_MAX_FETCH_ATTEMPTS = 6


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

    allowed_uids = retriever._resolve_allowed_uids(topic_id=topic_id, cluster_id=cluster_id)
    if (topic_id is not None or cluster_id is not None) and not allowed_uids:
        return None, _SearchFilters(
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

    normalized_query = retriever._expand_query(query) if expand_query and query else query
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
    return retriever._build_search_plan(normalized_query, top_k, filters, rerank=rerank, hybrid=hybrid), filters


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
