"""Exercises operational CLI dispatch for archive administration, analytics, training, and interactive terminal actions."""

from ._cli_commands_cases import (
    TestCmdAdmin,
    TestCmdAnalytics,
    TestCmdTraining,
    TestGetEmailDb,
    TestInteractiveAction,
    TestMainDispatch,
    TestPrintSenderLines,
    TestRenderHelpers,
    TestRunAnalyticsCommand,
    TestRunFineTune,
    TestRunGenerateTrainingData,
)

_COLLECTED_TESTS = (
    TestCmdAdmin,
    TestCmdAnalytics,
    TestCmdTraining,
    TestGetEmailDb,
    TestInteractiveAction,
    TestMainDispatch,
    TestPrintSenderLines,
    TestRenderHelpers,
    TestRunAnalyticsCommand,
    TestRunFineTune,
    TestRunGenerateTrainingData,
)
