"""Exercises extended OLM parsing for reply detection, namespace handling, body cleanup, and UID recovery.

It rejects missing or oversized input rather than silently producing incomplete mail records.
"""

from ._parse_olm_extended_cases import (
    TestCleanBodyEnglishReplyHeaders,
    TestCleanBodyGermanReplyHeaders,
    TestCleanBodyHtml,
    TestCleanBodyLegalDisclaimers,
    TestCleanBodyNonEnglishReplyHeaders,
    TestCleanBodySignatures,
    TestDetectNamespace,
    TestEmailTypeImplicitReply,
    TestEmailUidFallback,
    TestParseOlmFileNotFound,
    TestParseOlmOversizedXml,
)

_COLLECTED_TESTS = (
    TestCleanBodyEnglishReplyHeaders,
    TestCleanBodyGermanReplyHeaders,
    TestCleanBodyHtml,
    TestCleanBodyLegalDisclaimers,
    TestCleanBodyNonEnglishReplyHeaders,
    TestCleanBodySignatures,
    TestDetectNamespace,
    TestEmailTypeImplicitReply,
    TestEmailUidFallback,
    TestParseOlmFileNotFound,
    TestParseOlmOversizedXml,
)
