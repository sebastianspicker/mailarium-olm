"""Exercises CLI search, browsing, and export routes with their requested output representations."""

from ._cli_commands_cases import (
    TestCmdBrowse,
    TestCmdExport,
    TestCmdSearch,
    TestResolveOutputFormat,
    TestRunBrowse,
    TestRunExportEmail,
    TestRunExportThread,
    TestRunSingleQuery,
)

_COLLECTED_TESTS = (
    TestCmdBrowse,
    TestCmdExport,
    TestCmdSearch,
    TestResolveOutputFormat,
    TestRunBrowse,
    TestRunExportEmail,
    TestRunExportThread,
    TestRunSingleQuery,
)
