"""Ensures publication-facing repository files enforce private reporting, synthetic fixtures, and local-state exclusion.

It rejects obsolete domain material and non-native workflow behavior from the public surface.
"""

from __future__ import annotations

import hashlib
import json
import subprocess  # nosec B404
import sys
import tomllib

import pytest

from .helpers.repo_contracts import REPO_ROOT, _read


def _run_privacy_scan() -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosemgrep
        [sys.executable, "scripts/privacy_scan.py", "--tracked-only", "--json"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_security_policy_tracks_private_reporting() -> None:
    security = _read("SECURITY.md")

    assert "current\n`main` branch" in security
    assert "Do not disclose a suspected vulnerability in a public issue" in security
    assert "private vulnerability reporting" in security or "private reporting" in security
    assert "Mailarium is local-first" in security


def test_github_templates_are_present_and_privacy_safe() -> None:
    paths = (
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/ISSUE_TEMPLATE/question.yml",
        ".github/ISSUE_TEMPLATE/config.yml",
    )
    for relative_path in paths:
        text = _read(relative_path)
        assert "synthetic" in text.casefold() or "private" in text.casefold()
        assert "/Users/" not in text
    assert "security/advisories/new" in _read(".github/ISSUE_TEMPLATE/config.yml")


def test_gitignore_protects_private_runtime_and_local_tool_state() -> None:
    gitignore = _read(".gitignore")

    for entry in (
        "/private/",
        "/data/private/",
        "data/vector-index/",
        "/tests/private/",
        ".streamlit/secrets.toml",
        ".codegraph/",
        ".serena/",
        "/archive/local/",
        "docs/agent/",
        "/AUDIT_REPORT_*.md",
    ):
        assert entry in gitignore


def test_streamlit_is_bound_to_loopback_by_default() -> None:
    streamlit_config = tomllib.loads(_read(".streamlit/config.toml"))

    assert streamlit_config["server"]["address"] == "127.0.0.1"
    assert streamlit_config["theme"] == {
        "base": "light",
        "primaryColor": "#0B63CE",
        "backgroundColor": "#FFFFFF",
        "secondaryBackgroundColor": "#F4F7FA",
        "textColor": "#172331",
        "font": "sans serif",
    }
    launch = "python -m streamlit run mailarium/web_app.py --server.address 127.0.0.1"
    assert launch in _read("README.md")
    assert launch in _read("docs/README_USAGE_AND_OPERATIONS.md")


def test_removed_domain_surfaces_are_absent() -> None:
    removed_paths = (
        "mailarium/case_analysis.py",
        "mailarium/colbert_reranker.py",
        "mailarium/transformers_compat.py",
        "mailarium/templates/legal_support_handoff.html",
        "scripts/wave_workflow_smoke.py",
        "docs/archive/legal-domain-pack/README.md",
        "tests/case_workflows",
        "tests/fixtures/full_pack_matters",
    )
    for relative_path in removed_paths:
        assert not (REPO_ROOT / relative_path).exists(), relative_path


def test_generic_captured_eval_sets_include_grounding_and_negative_controls() -> None:
    core = json.loads(_read("tests/fixtures/qa_eval/qa_eval_questions.core.json"))["cases"]

    assert any(case.get("expected_support_source_ids") for case in core)
    assert any(case.get("expected_answer_terms") for case in core)
    assert any(case.get("forbidden_support_uids") or case.get("forbidden_support_source_ids") for case in core)


def test_qa_eval_fixtures_have_explicit_authored_synthetic_provenance() -> None:
    provenance = _read("tests/fixtures/qa_eval/PROVENANCE.md")
    core_payload = json.loads(_read("tests/fixtures/qa_eval/qa_eval_questions.core.json"))
    fixture_text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((REPO_ROOT / "tests/fixtures/qa_eval").glob("*.json"))
    )

    assert "intentionally authored synthetic regression data" in provenance
    assert "No operator mailbox export" in provenance
    assert "outlook-email-rag-alpha:<scenario-name>" in provenance
    uid_manifest = core_payload["uid_seed_manifest"]
    assert uid_manifest == {
        seed: hashlib.sha256(f"outlook-email-rag-alpha:{seed}".encode()).hexdigest()[:32] for seed in uid_manifest
    }
    referenced_uids = {
        uid
        for case in core_payload["cases"]
        for uid in (*case.get("expected_support_uids", []), case.get("expected_top_uid"))
        if uid
    }
    assert referenced_uids == set(uid_manifest.values())
    for stale_marker in (
        "HARICA",
        "Apple Support notes",
        "ticket system Reboot 2026",
        "Configurator 2 Blueprints",
        "891648cc4954152190a269112d54912e",
        "2606da536f3e533033cd6c2a8544f3a3",
    ):
        assert stale_marker not in fixture_text


def test_publication_surface_is_synthetic_and_private_artifact_free() -> None:
    completed = _run_privacy_scan()
    if completed.returncode:
        findings = {(item["category"], item["path"]) for item in json.loads(completed.stdout)}
        deleted_or_policy_denied = all(path == ".env.example" or not (REPO_ROOT / path).exists() for _category, path in findings)
        if findings and deleted_or_policy_denied:
            pytest.skip("managed workspace prevents a clean tracked-only scan until intended deletions are staged")
    assert completed.returncode == 0, completed.stdout


def test_github_workflows_are_repo_native_ci_only() -> None:
    workflows = sorted(path.name for path in (REPO_ROOT / ".github/workflows").glob("*.yml"))
    assert workflows == ["ci.yml"]
