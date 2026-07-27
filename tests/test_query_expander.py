"""Verifies corpus-driven query expansion produces relevant alternatives while preserving search intent."""

from __future__ import annotations

import numpy as np
import pytest

from mailarium.query_expander import QueryExpander


class _FakeModel:
    def encode_dense(self, texts):
        return [np.random.RandomState(hash(text) % 2**31).randn(8).astype(np.float32).tolist() for text in texts]


def test_expansion_uses_corpus_terms_for_every_scope() -> None:
    expander = QueryExpander(model=_FakeModel(), vocabulary=["calendar invite", "budget forecast", "project handover"])

    expanded = expander.expand("budget review", n_terms=2, scope="finance")

    assert expanded.startswith("budget review")
    assert len(expanded) > len("budget review")


def test_lane_expansion_keeps_original_and_ascii_variant() -> None:
    expander = QueryExpander(model=None, vocabulary=[])

    lanes = expander.expand_lanes("Überprüfung", max_lanes=4, scope="customer support")

    assert lanes == ["Überprüfung", "Ueberpruefung"]


def test_empty_or_unconfigured_expansion_is_unchanged() -> None:
    expander = QueryExpander(model=None, vocabulary=[])

    assert expander.expand("plain query") == "plain query"
    assert expander.expand_lanes("") == []


def test_related_terms_exclude_query_terms_and_short_tokens() -> None:
    expander = QueryExpander(model=_FakeModel(), vocabulary=["ab", "budget", "project management"])

    assert all(len(term) >= 3 and term != "budget" for term, _score in expander.get_related_terms("budget", n_terms=5))


def test_scope_validation_stays_at_the_cli_boundary() -> None:
    from mailarium.cli import parse_args

    with pytest.raises(SystemExit):
        parse_args(["search", "budget", "--scope", ""])
