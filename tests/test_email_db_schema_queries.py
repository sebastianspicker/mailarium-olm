"""Validates versioned archive schema data and query paths for attachments, threads, batches, and subject groups."""

from ._email_db_cases import (
    TestAttachmentQueries,
    TestEmailsByBaseSubject,
    TestGetEmailsFullBatch,
    TestGetInferredThreadEmails,
    TestGetThreadEmailsBatchRecipients,
    TestSchemaV7,
    TestSchemaV8,
    TestSchemaV9,
)

_COLLECTED_TESTS = (
    TestAttachmentQueries,
    TestEmailsByBaseSubject,
    TestGetEmailsFullBatch,
    TestGetInferredThreadEmails,
    TestGetThreadEmailsBatchRecipients,
    TestSchemaV7,
    TestSchemaV8,
    TestSchemaV9,
)
