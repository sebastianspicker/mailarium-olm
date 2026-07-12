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
