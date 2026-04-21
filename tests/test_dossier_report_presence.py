"""Dossier report-presence and executive-summary tests."""

from __future__ import annotations

from src.dossier_generator import DossierGenerator

pytest_plugins = ["tests._dossier_cases"]


def test_preview_returns_correct_counts(gen):
    result = gen.preview()

    assert result["evidence_count"] == 3
    assert result["email_count"] == 3
    assert result["category_count"] == 3
    assert "harassment" in result["categories"]
    assert "discrimination" in result["categories"]


def test_preview_filters_by_relevance(gen):
    result = gen.preview(min_relevance=4)

    assert result["evidence_count"] == 2


def test_preview_filters_by_category(gen):
    result = gen.preview(category="harassment")

    assert result["evidence_count"] == 1
    assert result["categories"] == ["harassment"]


def test_preview_empty_evidence(gen_empty):
    result = gen_empty.preview()

    assert result["evidence_count"] == 0
    assert result["email_count"] == 0


def test_generate_returns_valid_html(gen):
    result = gen.generate(title="Test Dossier")

    assert "html" in result
    assert "<html" in result["html"]
    assert "Test Dossier" in result["html"]


def test_generate_includes_case_reference(gen):
    result = gen.generate(case_reference="CASE-2024-001")

    assert "CASE-2024-001" in result["html"]


def test_generate_includes_custodian(gen):
    result = gen.generate(custodian="Evidence Manager")

    assert "Evidence Manager" in result["html"]


def test_generate_has_dossier_hash(gen):
    import hashlib

    result = gen.generate()

    assert "dossier_hash" in result
    assert len(result["dossier_hash"]) == 64
    assert result["dossier_hash"] == hashlib.sha256(result["html"].encode("utf-8")).hexdigest()


def test_generate_filters_by_relevance(gen):
    result = gen.generate(min_relevance=5)

    assert result["evidence_count"] == 1


def test_generate_filters_by_category(gen):
    result = gen.generate(category="harassment")

    assert result["evidence_count"] == 1


def test_generate_includes_custody_log(gen):
    result = gen.generate(include_custody=True)

    assert "Chain-of-Custody Log" in result["html"]


def test_generate_excludes_custody_when_disabled(gen):
    result = gen.generate(include_custody=False)

    assert "Chain-of-Custody Log" not in result["html"]


def test_generate_empty_evidence(gen_empty):
    result = gen_empty.generate(title="Empty Dossier")

    assert "html" in result
    assert result["evidence_count"] == 0
    assert "Empty Dossier" in result["html"]


def test_generate_has_generated_at(gen):
    result = gen.generate()

    assert "generated_at" in result
    assert "UTC" in result["generated_at"]


def test_generate_with_network(db):
    from src.network_analysis import CommunicationNetwork

    net = CommunicationNetwork(db)
    generator = DossierGenerator(db, network=net)
    result = generator.generate(include_relationships=True)

    assert "Relationship Analysis" in result["html"]


def test_generate_without_network(gen):
    result = gen.generate(include_relationships=True)

    assert "Relationship Analysis" not in result["html"]


def test_generate_with_persons_of_interest(db):
    from src.network_analysis import CommunicationNetwork

    net = CommunicationNetwork(db)
    generator = DossierGenerator(db, network=net)
    result = generator.generate(persons_of_interest=["sender1@example.test"])

    assert "sender1@example.test" in result["html"]


def test_executive_summary_present(gen):
    result = gen.generate()
    html = result["html"]

    assert "Executive Summary" in html
    assert "evidence items" in html
    assert "source emails" in html


def test_executive_summary_absent_when_empty(gen_empty):
    result = gen_empty.generate()
    html = result["html"]

    assert "Executive Summary" not in html


def test_category_breakdown_table(gen):
    result = gen.generate()
    html = result["html"]

    assert "Category Breakdown" in html
    assert "harassment" in html
    assert "discrimination" in html
    assert "retaliation" in html


def test_glossary_present(gen):
    result = gen.generate()
    html = result["html"]

    assert "Category Definitions" in html
    assert "Hostile behavior" in html


def test_prepared_by_on_cover(gen):
    result = gen.generate(prepared_by="Jane Smith, Paralegal")
    html = result["html"]

    assert "Jane Smith, Paralegal" in html
    assert "Prepared by:" in html


def test_scope_section_no_filters(gen):
    result = gen.generate()
    html = result["html"]

    assert "No filters applied" in html
    assert "3</strong> emails" in html


def test_scope_section_with_filters(gen):
    result = gen.generate(category="harassment")
    html = result["html"]

    assert "Category: harassment" in html


def test_legal_disclaimer_present(gen):
    result = gen.generate()
    html = result["html"]

    assert "electronically stored information" in html
    assert "does not constitute" in html
