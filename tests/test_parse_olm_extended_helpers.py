"""Exercises auxiliary OLM extractors for source bodies, Exchange lists, categories, meetings, and HTML.

It preserves structured metadata when the primary XML representation is incomplete.
"""

from ._parse_olm_extended_cases import (
    TestBodyFromSource,
    TestExtractCategories,
    TestExtractExchangeList,
    TestExtractHtmlBody,
    TestExtractMeetingData,
    TestFindHelpers,
    TestSourceFallbackHeaders,
)

_COLLECTED_TESTS = (
    TestBodyFromSource,
    TestExtractCategories,
    TestExtractExchangeList,
    TestExtractHtmlBody,
    TestExtractMeetingData,
    TestFindHelpers,
    TestSourceFallbackHeaders,
)
