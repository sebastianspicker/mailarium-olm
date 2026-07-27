"""Exercises sparse and hybrid retrieval, thread lookup, index reset, and SQLite-backed aggregate statistics.

It retains useful empty-collection and unknown-identifier behavior when local storage is unavailable.
"""

from ._retriever_coverage_cases import (
    TestGetBM25Results,
    TestGetSparseResults,
    TestListSendersSqlite,
    TestMergeHybrid,
    TestSearchByThread,
    TestStatsSqlite,
    test_list_folders_returns_folder_counts,
    test_reset_index,
    test_stats_empty_collection_without_db,
    test_stats_vector_collection_counts_unknown_uid_rows,
)

_COLLECTED_TESTS = (
    TestGetBM25Results,
    TestGetSparseResults,
    TestListSendersSqlite,
    TestMergeHybrid,
    TestSearchByThread,
    TestStatsSqlite,
    test_list_folders_returns_folder_counts,
    test_reset_index,
    test_stats_vector_collection_counts_unknown_uid_rows,
    test_stats_empty_collection_without_db,
)
