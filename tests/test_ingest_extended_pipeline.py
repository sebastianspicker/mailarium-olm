"""Exercises pipeline edge handling for attachments, duplicate records, argument validation, and re-embedding progress."""

from ._ingest_extended_cases import (
    TestAttachmentProcessing,
    TestParseArgsEdgeCases,
    TestPipelineSkipAlreadyInserted,
    TestPositiveInt,
    TestReembedEdgeCases,
)

_COLLECTED_TESTS = (
    TestAttachmentProcessing,
    TestParseArgsEdgeCases,
    TestPipelineSkipAlreadyInserted,
    TestPositiveInt,
    TestReembedEdgeCases,
)
