"""Exercises dense retrieval validation, result semantics, reranking, and hybrid-search integration.

It bounds candidate expansion and uses the cross-encoder fallback when a reranker cannot run.
"""

from ._retriever_coverage_cases import (
    TestQueryWithEmbedding,
    TestSearchFilteredSemantic,
    TestSearchResultMethods,
    TestSearchValidation,
    test_apply_rerank_cross_encoder_fallback,
    test_model_property_is_embedder_alias,
    test_search_filtered_calls_merge_hybrid_when_enabled,
    test_search_filtered_calls_rerank_when_enabled,
    test_search_filtered_lowercases_email_type,
    test_search_filtered_raises_on_zero_top_k,
    test_search_filtered_stops_at_max_fetch_size,
)

_COLLECTED_TESTS = (
    TestQueryWithEmbedding,
    TestSearchFilteredSemantic,
    TestSearchResultMethods,
    TestSearchValidation,
    test_apply_rerank_cross_encoder_fallback,
    test_model_property_is_embedder_alias,
    test_search_filtered_calls_merge_hybrid_when_enabled,
    test_search_filtered_calls_rerank_when_enabled,
    test_search_filtered_lowercases_email_type,
    test_search_filtered_raises_on_zero_top_k,
    test_search_filtered_stops_at_max_fetch_size,
)
