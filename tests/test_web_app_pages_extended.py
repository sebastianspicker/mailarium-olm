"""Exercises Streamlit rendering for dashboard, entity, evidence, and network views from available analysis data."""

from ._web_app_extended_cases import (
    TestRenderDashboardPage,
    TestRenderEntityPage,
    TestRenderEvidencePage,
    TestRenderNetworkPage,
)

_COLLECTED_TESTS = (
    TestRenderDashboardPage,
    TestRenderEntityPage,
    TestRenderEvidencePage,
    TestRenderNetworkPage,
)
