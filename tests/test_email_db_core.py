"""Maintains core archive inserts, recipient identities, contacts, communication edges, and null-safe re-embedding rows."""

from ._email_db_cases import TestEmailDatabase, TestParseAddress

_COLLECTED_TESTS = (
    TestEmailDatabase,
    TestParseAddress,
)
