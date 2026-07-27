"""Exercises ingestion command edge cases for maintenance modes, argument requirements, progress, and empty archives."""

from ._ingest_extended_cases import (
    TestFormatSummaryEdgeCases,
    TestIngestEdgeCases,
    TestReingestAnalyticsEdgeCases,
    TestReingestBodiesEdgeCases,
    TestReingestMetadataEdgeCases,
)

_COLLECTED_TESTS = (
    TestFormatSummaryEdgeCases,
    TestIngestEdgeCases,
    TestReingestAnalyticsEdgeCases,
    TestReingestBodiesEdgeCases,
    TestReingestMetadataEdgeCases,
)
