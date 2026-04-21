"""Dossier empty and edge-case tests."""

from __future__ import annotations

pytest_plugins = ["tests._dossier_cases"]


def test_empty_dossier_still_contains_title(gen_empty):
    result = gen_empty.generate(title="Empty Dossier")

    assert "Empty Dossier" in result["html"]
    assert result["evidence_count"] == 0


def test_empty_preview_has_zero_categories(gen_empty):
    result = gen_empty.preview()

    assert result["categories"] == []
    assert result["category_count"] == 0


def test_empty_generate_omits_relationship_analysis(gen_empty):
    result = gen_empty.generate(include_relationships=True)

    assert "Relationship Analysis" not in result["html"]


def test_empty_generate_omits_executive_summary(gen_empty):
    result = gen_empty.generate()

    assert "Executive Summary" not in result["html"]


def test_populated_generate_keeps_html_root(gen):
    result = gen.generate()

    assert "<html" in result["html"]
