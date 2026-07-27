"""Exercises evidence-oriented CLI routes for provenance, custody checks, and exportable audit material."""

from ._cli_commands_cases import (
    TestCmdEvidence,
    TestRunCustodyChain,
    TestRunDossier,
    TestRunEvidenceExport,
    TestRunEvidenceList,
    TestRunEvidenceStats,
    TestRunEvidenceVerify,
    TestRunProvenance,
)

_COLLECTED_TESTS = (
    TestCmdEvidence,
    TestRunCustodyChain,
    TestRunDossier,
    TestRunEvidenceExport,
    TestRunEvidenceList,
    TestRunEvidenceStats,
    TestRunEvidenceVerify,
    TestRunProvenance,
)
