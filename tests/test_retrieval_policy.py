"""Focused contract tests for deterministic retrieval policy selection."""

from dataclasses import FrozenInstanceError

import pytest

from mailarium.retrieval_policy import (
    GENERAL_SCOPE,
    MAX_SCOPE_LENGTH,
    apply_scope_context,
    normalize_scope,
    resolve_retrieval_policy,
)


def test_normalize_scope_defaults_and_compacts_whitespace() -> None:
    assert normalize_scope() == GENERAL_SCOPE
    assert normalize_scope("  Customer\t Support  ") == "customer support"


@pytest.mark.parametrize("scope", ["", "   ", "legal\x00support", "x" * (MAX_SCOPE_LENGTH + 1)])
def test_normalize_scope_rejects_empty_control_and_too_long_values(scope: str) -> None:
    with pytest.raises(ValueError):
        normalize_scope(scope)


def test_normalize_scope_rejects_non_string_values() -> None:
    with pytest.raises(TypeError):
        normalize_scope(42)  # type: ignore[arg-type]


def test_default_policy_is_immutable_and_weights_are_normalized() -> None:
    policy = resolve_retrieval_policy("find messages about schedule changes")

    assert policy.semantic_weight == 0.60
    assert policy.keyword_weight == 0.40
    assert policy.semantic_weight + policy.keyword_weight == 1.0
    assert 0.0 <= policy.semantic_weight <= 1.0
    assert 0.0 <= policy.keyword_weight <= 1.0
    with pytest.raises(FrozenInstanceError):
        policy.scope = "other"  # type: ignore[misc]


@pytest.mark.parametrize(
    "query, reason",
    [
        ('find "budget approval" email', "quoted_phrase"),
        ("find alice@example.com", "email_token"),
        ("open payroll-2025.xlsx", "filename_token"),
        ("find ticket 123456789", "long_identifier"),
    ],
)
def test_exact_lexical_signals_shift_toward_keyword(query: str, reason: str) -> None:
    policy = resolve_retrieval_policy(query)

    assert policy.keyword_weight > policy.semantic_weight
    assert reason in policy.reason_codes


def test_question_and_long_natural_language_queries_shift_toward_semantic() -> None:
    policy = resolve_retrieval_policy("How did the schedule change affect the handover process?")

    assert policy.semantic_weight > policy.keyword_weight
    assert "semantic_query_shape" in policy.reason_codes


def test_custom_scope_enriches_query_but_general_scope_does_not() -> None:
    query = "find overdue invoices"

    assert apply_scope_context(query) == query
    assert apply_scope_context(query, "Finance Team") == "find overdue invoices\nRetrieval scope: finance team"


def test_policy_output_is_deterministic() -> None:
    query = 'How did "project alpha" change after 123456?'

    assert resolve_retrieval_policy(query, "Customer Support") == resolve_retrieval_policy(query, "Customer Support")
