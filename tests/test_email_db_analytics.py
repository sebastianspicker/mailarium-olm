"""Persists and queries archive entities, communication relationships, and time-based message activity."""

from ._email_db_cases import TestEntityOperations, TestNetworkQueries, TestTemporalQueries

_COLLECTED_TESTS = (
    TestEntityOperations,
    TestNetworkQueries,
    TestTemporalQueries,
)
