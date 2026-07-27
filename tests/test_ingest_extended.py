"""Exercises ingestion helpers for progress fallback, analytics, checkpoints, entity extraction, and rollback-aware writes."""

from ._ingest_extended_cases import (
    TestAutoDownloadSpacyModels,
    TestCheckpointWal,
    TestComputeAnalytics,
    TestHashFileSha256,
    TestMainDispatch,
    TestMakeProgressBar,
    TestNoOpProgressBar,
    TestPipelineProcessBatch,
    TestPipelineSubmitError,
    TestResetIndex,
    TestResolveEntityExtractor,
)

_COLLECTED_TESTS = (
    TestAutoDownloadSpacyModels,
    TestCheckpointWal,
    TestComputeAnalytics,
    TestHashFileSha256,
    TestMainDispatch,
    TestMakeProgressBar,
    TestNoOpProgressBar,
    TestPipelineProcessBatch,
    TestPipelineSubmitError,
    TestResetIndex,
    TestResolveEntityExtractor,
)
