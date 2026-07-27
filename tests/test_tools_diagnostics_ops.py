"""Exercises diagnostic maintenance actions for invalid requests and controlled reingestion or reembedding operations."""

from ._tools_diagnostics_cases import (
    TestInvalidAction,
    TestReembed,
    TestReingestAnalytics,
    TestReingestBodies,
    TestReingestMetadata,
)

_COLLECTED_TESTS = (
    TestInvalidAction,
    TestReembed,
    TestReingestAnalytics,
    TestReingestBodies,
    TestReingestMetadata,
)
