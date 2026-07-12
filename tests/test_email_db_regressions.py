from ._email_db_cases import (
    TestAttachmentStatsMultiDotExtension,
    TestDateBoundaryBug,
    TestGetEmailForReembedNullSafety,
    TestGetEmailFullNoJsonLeak,
    TestGetThreadEmailsParsesJsonFields,
    TestInsertEmailContentHash,
    TestInsertEmailNoneBody,
    TestLikeEscaping,
    TestUpdateV7IsInline,
)

_COLLECTED_TESTS = (
    TestAttachmentStatsMultiDotExtension,
    TestDateBoundaryBug,
    TestGetEmailForReembedNullSafety,
    TestGetEmailFullNoJsonLeak,
    TestGetThreadEmailsParsesJsonFields,
    TestInsertEmailContentHash,
    TestInsertEmailNoneBody,
    TestLikeEscaping,
    TestUpdateV7IsInline,
)
