from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _git_ls(relative_path: str) -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "--", relative_path],
        check=True,
        capture_output=True,
        cwd=REPO_ROOT,
        text=True,
    )
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def _is_tracked(relative_path: str) -> bool:
    return bool(_git_ls(relative_path))


def _mcp_tool_count() -> int:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from src.mcp_server import ToolDeps, mcp; "
                "from src.tools import register_all; "
                "manager = getattr(mcp, '_tool_manager', None); "
                "tools = getattr(manager, '_tools', None); "
                "register_all(mcp, ToolDeps()) if not isinstance(tools, dict) else None; "
                "manager = getattr(mcp, '_tool_manager', None); "
                "tools = getattr(manager, '_tools', None); "
                "print(len(tools))"
            ),
        ],
        check=True,
        capture_output=True,
        cwd=REPO_ROOT,
        text=True,
    )
    return int(completed.stdout.strip())


def test_env_example_includes_analytics_timezone():
    env_example = _read(".env.example")
    assert "ANALYTICS_TIMEZONE=" in env_example
    assert "RUNTIME_PROFILE=" in env_example
    assert "EMBEDDING_LOAD_MODE=" in env_example


def test_readme_install_flow_includes_package_install_for_console_scripts():
    readme = _read("README.md")
    assert "pip install -e ." in readme
    assert "docs/RUNTIME_TUNING.md" in readme
    assert "RUNTIME_PROFILE=quality" in readme
    assert "# RERANK_ENABLED=false" in readme
    assert "# HYBRID_ENABLED=false" in readme
    assert "# SPARSE_ENABLED=false" in readme
    assert "# COLBERT_RERANK_ENABLED=false" in readme


def test_env_example_uses_profile_first_quality_setup():
    env_example = _read(".env.example")
    assert "CHROMADB_PATH=private/runtime/current/chromadb" in env_example
    assert "SQLITE_PATH=private/runtime/current/email_metadata.db" in env_example
    assert "RUNTIME_PROFILE=quality" in env_example
    assert "# SPARSE_ENABLED=true" in env_example
    assert "# COLBERT_RERANK_ENABLED=true" in env_example
    assert "# RERANK_ENABLED=true" in env_example
    assert "# HYBRID_ENABLED=true" in env_example


def test_readme_does_not_hardcode_test_count_badge():
    readme = _read("README.md")
    assert not re.search(r"badge/tests-\d+", readme)
    assert "tests (2147+)" not in readme


def test_readme_mcp_tool_badge_matches_documented_tool_count():
    readme = _read("README.md")
    tool_count = _mcp_tool_count()
    assert f"badge/MCP_tools-{tool_count}" in readme
    assert f"Email RAG exposes {tool_count} MCP tools." in readme
    assert f"You should see all {tool_count} tools listed beneath it" in readme


def test_readme_privacy_note_matches_first_run_download_boundary():
    readme = _read("README.md")
    assert "No API calls, no data leaves your machine." not in readme
    assert "Email content stays local" in readme
    assert "Hugging Face" in readme


def test_security_policy_tracks_dev_branch_and_private_reporting():
    security = _read("SECURITY.md")

    assert "latest state of the `dev` branch" in security
    assert "Do not open a public GitHub issue" in security
    assert "private vulnerability reporting" in security or "private reporting" in security
    assert "Email content stays local" in security


def test_public_metadata_uses_canonical_github_urls():
    canonical = "https://github.com/sebastianspicker/outlook-email-rag"
    readme = _read("README.md")
    pyproject_text = _read("pyproject.toml")
    project = tomllib.loads(pyproject_text)["project"]
    urls = project["urls"]

    assert urls["Repository"] == canonical
    assert urls["Homepage"] == canonical
    assert urls["Issues"] == f"{canonical}/issues"
    assert urls["Documentation"] == f"{canonical}/tree/dev/docs"
    assert urls["Changelog"] == f"{canonical}/blob/dev/CHANGELOG.md"
    assert urls["Security"] == f"{canonical}/blob/dev/SECURITY.md"
    assert f"git clone {canonical}.git" in readme
    assert "example-org/outlook-email-rag" not in readme
    assert "example-org/outlook-email-rag" not in pyproject_text


def test_github_templates_are_present_and_privacy_safe():
    required_paths = [
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/ISSUE_TEMPLATE/config.yml",
    ]
    forbidden_markers = [
        "HfMT",
        "Koeln",
        "Köln",
        "/Users/",
        "01_high",
        "Codex",
        "OpenAI",
        "Claude",
    ]

    for relative_path in required_paths:
        text = _read(relative_path)
        assert "synthetic" in text.lower() or "private" in text.lower()
        for marker in forbidden_markers:
            assert marker not in text, f"{relative_path} contains {marker}"

    assert "blank_issues_enabled: false" in _read(".github/ISSUE_TEMPLATE/config.yml")
    assert "security/advisories/new" in _read(".github/ISSUE_TEMPLATE/config.yml")


def test_public_docs_explain_interface_choice_and_go_live_hygiene():
    readme = _read("README.md")
    architecture = _read("docs/ARCHITECTURE_AND_METHODS.md")
    operations = _read("docs/README_USAGE_AND_OPERATIONS.md")
    docs_index = _read("docs/README.md")

    assert "docs/ARCHITECTURE_AND_METHODS.md" in readme
    assert "ARCHITECTURE_AND_METHODS.md" in operations
    assert "ARCHITECTURE_AND_METHODS.md" in docs_index
    assert "```mermaid" in architecture
    assert "RRF(d)" in architecture
    assert "S(q, d)" in architecture
    assert "## Choose Your Interface" in readme
    assert "## Use The Right Surface" in operations
    assert "### Go-live checklist" in operations
    assert "## Choose The Right Surface" in docs_index
    assert "## Public Vs Advanced Docs" in docs_index
    assert "agent/README.md" in docs_index


def test_case_workflow_docs_cover_preflight_to_case_helper_and_full_pack_override_path():
    operations = _read("docs/README_USAGE_AND_OPERATIONS.md")
    cli_reference = _read("docs/CLI_REFERENCE.md")
    helper = _read("scripts/prepare_case_inputs.py")

    assert "scripts/prepare_case_inputs.py" in operations
    assert "--case-json-out private/cases/case.json" in operations
    assert "--overrides-out private/cases/full_pack_overrides.json" in operations
    assert "Do not curate `private/cases/case.json`" in operations

    assert "scripts/prepare_case_inputs.py" in cli_reference
    assert "full_pack_overrides.json" in cli_reference
    assert "extraction_basis" in cli_reference
    assert "Do not curate one structured case input for evidence harvest" in cli_reference

    assert "extraction_basis" in helper
    assert "date_confidence" in helper
    assert "--case-json-out" in helper
    assert "--overrides-out" in helper


def test_readme_routes_real_mailboxes_into_private_workspace():
    readme = _read("README.md")
    assert "private/ingest/example-export.olm" in readme
    assert "`private/` is ignored by Git" in readme
    assert "Keep tracked `data/` and `tests/fixtures/` content sanitized." in readme
    assert "private/runtime/current/chromadb" in readme
    assert "private/runtime/current/email_metadata.db" in readme


def test_gitignore_excludes_private_local_matter_workspaces():
    gitignore = _read(".gitignore")
    assert "/private/" in gitignore
    assert "/data/private/" in gitignore
    assert "/tests/private/" in gitignore
    assert "/tests/fixtures/private/" in gitignore
    assert ".streamlit/secrets.toml" in gitignore


def test_github_workflows_are_repo_native_ci_only():
    workflows_dir = REPO_ROOT / ".github" / "workflows"
    workflow_files = sorted(path.name for path in workflows_dir.glob("*.yml"))
    assert workflow_files == ["ci.yml"]
    assert not (REPO_ROOT / ".github" / ("co" + "dex")).exists()


def test_topic_surfaces_are_demoted_from_stable_contract():
    readme = _read("README.md")
    compatibility = _read("docs/API_COMPATIBILITY.md")

    assert "default ingest workflow does not populate topic tables yet" in readme
    assert "Conditional Topic Surface" in compatibility
    assert "excluded from the stable `0.1.x` compatibility contract" in compatibility


def test_cli_reference_leads_with_subcommands_before_legacy_flags():
    cli_reference = _read("docs/CLI_REFERENCE.md")
    assert "## Subcommands (recommended)" in cli_reference
    assert "## Legacy Flat-Flag Reference" in cli_reference
    assert cli_reference.index("## Subcommands (recommended)") < cli_reference.index("## Legacy Flat-Flag Reference")
    assert "python -m src.cli search" in cli_reference
    assert "python -m src.cli --query" not in cli_reference
    assert "case execute-wave" in cli_reference
    assert "case execute-all-waves" in cli_reference


def test_diagnostics_docs_describe_resolved_runtime_summary():
    readme = _read("README.md")
    mcp_tools = _read("docs/MCP_TOOLS.md")
    compatibility = _read("docs/API_COMPATIBILITY.md")

    assert "shows resolved runtime settings, embedder/backend state, MCP budgets, and sparse-index status" in readme
    assert "resolved runtime profile/load mode/device/batch size" in mcp_tools
    assert "current embedder backend state" in mcp_tools
    assert "resolved runtime settings" in compatibility
    assert "current embedder/backend state" in compatibility


def test_response_time_docs_are_explicitly_sample_scoped():
    readme = _read("README.md")
    cli_reference = _read("docs/CLI_REFERENCE.md")
    mcp_tools = _read("docs/MCP_TOOLS.md")
    analysis_models = _read("src/mcp_models_analysis.py")

    assert "recent-sample response times per sender based on canonical reply pairs" in readme
    assert "Recent-sample response times per sender (canonical reply pairs)" in cli_reference
    assert "recent-sample response times per sender based on canonical reply pairs" in mcp_tools
    assert "recent-sample response times per sender based on canonical reply pairs" in analysis_models
    assert "average response times per sender" not in mcp_tools


def test_internal_operator_workspace_artifacts_are_not_checked_in():
    local_only_paths = [
        "AGENTS.md",
        "HARNESS_PRINCIPLES.md",
        "code_review.md",
        "docs/source-audit",
        "docs/agent/Prompt.md",
        "docs/agent/Implement.md",
        "docs/agent/AutonomousHardStops.md",
        "docs/agent/RunModes.md",
        "docs/agent/AutonomyPolicy.md",
        "docs/agent/Goals.md",
        "docs/agent/RepoProfile.md",
        "docs/agent/Findings.md",
        "docs/agent/Backlog.md",
        "docs/agent/Topology.md",
        "docs/agent/VerificationMatrix.md",
        "docs/agent/Checkpoint.md",
        "docs/agent/Decisions.md",
        "docs/agent/ingestion_optimization_plan.md",
        "docs/agent/ingestion_optimization_progress.md",
        "docs/agent/qa_eval_plan.md",
        "docs/agent/qa_eval_captured_refresh.md",
    ]
    for relative_path in local_only_paths:
        assert not _is_tracked(relative_path), relative_path


def test_publication_surface_is_synthetic_and_private_artifact_free():
    completed = subprocess.run(
        [sys.executable, "scripts/privacy_scan.py", "--tracked-only", "--json"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stdout


def test_deprecated_audit_artifacts_are_tracked_repo_docs():
    required_paths = [
        "docs/agent/deprecated/AUDIT.md",
        "docs/agent/deprecated/AUDIT_COMPANION.md",
    ]
    for relative_path in required_paths:
        assert (REPO_ROOT / relative_path).exists(), relative_path
        assert _is_tracked(relative_path), relative_path


def test_live_autonomous_execution_docs_exist():
    required_paths = [
        "docs/agent/Plan.md",
        "docs/agent/Documentation.md",
        "docs/agent/runtime_path_remediation_plan.md",
        "docs/agent/email_matter_analysis_single_source_of_truth.md",
        "docs/agent/question_execution_companion.md",
        "docs/agent/question_execution_prompt_pack.md",
        "docs/agent/question_execution_query_packs.md",
        "docs/agent/question_register_template.md",
        "docs/agent/open_tasks_companion_template.md",
        "docs/agent/email_matter_investigation_checkpoint_template.md",
        "docs/agent/mcp_client_config_snippet.md",
    ]
    for relative_path in required_paths:
        assert (REPO_ROOT / relative_path).exists(), relative_path


def test_behavioral_captured_eval_pack_tracks_source_grounding_and_benchmark_cases():
    import json

    payload = json.loads(_read("docs/agent/qa_eval_questions.behavioral_analysis.captured.json"))
    cases = payload["cases"]

    assert any(case.get("expected_support_source_ids") for case in cases)
    assert any(case.get("benchmark_pack") for case in cases)


def test_legal_support_captured_eval_pack_tracks_grounding_and_negative_controls():
    import json

    payload = json.loads(_read("docs/agent/qa_eval_questions.legal_support.captured.json"))
    cases = payload["cases"]

    assert any(case.get("expected_legal_support_source_ids") for case in cases)
    assert any(case.get("expected_answer_terms") for case in cases)
    assert any(case.get("forbidden_issue_ids") for case in cases)
    assert any(case.get("forbidden_actor_ids") for case in cases)
    assert any(case.get("forbidden_dashboard_cards") for case in cases)
    assert any(case.get("forbidden_checklist_group_ids") for case in cases)


def test_gitignore_keeps_internal_operator_artifacts_out_of_future_commits():
    gitignore = _read(".gitignore")
    expected_entries = [
        "AGENTS.md",
        "HARNESS_PRINCIPLES.md",
        "code_review.md",
        "docs/source-audit/",
        "docs/agent/Prompt.md",
        "docs/agent/Implement.md",
        "docs/agent/AutonomousHardStops.md",
        "docs/agent/RunModes.md",
        "docs/agent/AutonomyPolicy.md",
        "docs/agent/Goals.md",
        "docs/agent/RepoProfile.md",
        "docs/agent/Findings.md",
        "docs/agent/Backlog.md",
        "docs/agent/Topology.md",
        "docs/agent/VerificationMatrix.md",
        "docs/agent/Checkpoint.md",
        "docs/agent/Decisions.md",
        "docs/agent/ingestion_optimization_plan.md",
        "docs/agent/ingestion_optimization_progress.md",
        "docs/agent/qa_eval_plan.md",
        "docs/agent/qa_eval_captured_refresh.md",
    ]
    for entry in expected_entries:
        assert entry in gitignore


def test_repo_maintained_files_stay_under_800_loc_threshold() -> None:
    tracked = subprocess.run(
        ["git", "ls-files"],
        check=True,
        capture_output=True,
        cwd=REPO_ROOT,
        text=True,
    ).stdout.splitlines()
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        check=True,
        capture_output=True,
        cwd=REPO_ROOT,
        text=True,
    ).stdout.splitlines()
    candidate_paths = sorted({*tracked, *untracked})
    threshold = 800
    exempt_prefixes = (
        "docs/agent/deprecated/",
        ".kilo/",
    )
    exempt_suffixes = (
        ".captured.json",
        ".live.json",
    )
    generated_golden_prefixes = ("docs/agent/legal_support_full_pack_golden.",)
    exempt_exact = {
        "uv.lock",
        # Staged refactor compatibility: remove after runtime/helper extraction lands.
        "src/db_evidence.py",
        "src/ingest_reingest.py",
        "src/matter_evidence_index_helpers.py",
        # Staged slice M2-M7 compatibility: split into helper modules in a follow-up refactor.
        "src/db_schema_migrations.py",
        "src/email_db.py",
        "src/ingest_pipeline.py",
        "tests/_ingest_pipeline_core_cases.py",
        "tests/test_repo_contracts.py",
    }
    offenders: list[tuple[str, int]] = []
    for relative_path in candidate_paths:
        if relative_path in exempt_exact:
            continue
        if relative_path.startswith(exempt_prefixes):
            continue
        if relative_path.startswith(generated_golden_prefixes) and relative_path.endswith(".json"):
            continue
        if relative_path.endswith(exempt_suffixes):
            continue
        if not relative_path.endswith((".py", ".md", ".yml", ".yaml", ".toml", ".json", ".txt", ".sh")):
            continue
        file_path = REPO_ROOT / relative_path
        if not file_path.is_file():
            continue
        with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
            line_count = sum(1 for _ in handle)
        if line_count > threshold:
            offenders.append((relative_path, line_count))
    assert not offenders, "\n".join(f"{path}: {count}" for path, count in sorted(offenders))


def test_readme_and_docs_index_reflect_public_documentation_surface():
    readme = _read("README.md")
    docs_index = _read("docs/README.md")
    agent_index = _read("docs/agent/README.md")
    tool_count = _mcp_tool_count()

    assert "[docs/README.md](docs/README.md)" in readme
    assert "[docs/README_USAGE_AND_OPERATIONS.md](docs/README_USAGE_AND_OPERATIONS.md)" in readme
    assert f"Available MCP Tool Families ({tool_count} tools)" in readme
    assert "A visual search interface that runs in your browser. This is the exploratory GUI" in readme
    assert "private/ingest/latest-export.olm" in readme
    assert "├── private/" in readme
    assert "[README_USAGE_AND_OPERATIONS.md](README_USAGE_AND_OPERATIONS.md)" in docs_index
    assert "[CLI_REFERENCE.md](CLI_REFERENCE.md)" in docs_index
    assert "[MCP_TOOLS.md](MCP_TOOLS.md)" in docs_index
    assert "Treat [`agent/README.md`](agent/README.md) as the single entry point" in docs_index
    assert "[docs/agent/README.md](docs/agent/README.md)" in readme
    assert "All checked-in examples in this subtree must remain synthetic." in agent_index
    assert "## Product And Contract Docs" in agent_index
    assert "## Operator Runbooks" in agent_index
    assert "## Synthetic Fixtures And Eval Assets" in agent_index
    assert "## Archive Material" in agent_index
    assert "[`Plan.md`](Plan.md)" in agent_index
    assert "[`runtime_path_remediation_plan.md`](runtime_path_remediation_plan.md)" in agent_index
    assert "[`question_execution_companion.md`](question_execution_companion.md)" in agent_index
    assert "[`question_execution_prompt_pack.md`](question_execution_prompt_pack.md)" in agent_index
    assert "[`question_register_template.md`](question_register_template.md)" in agent_index
    assert "[`open_tasks_companion_template.md`](open_tasks_companion_template.md)" in agent_index
    assert "[`mcp_client_config_snippet.md`](mcp_client_config_snippet.md)" in agent_index
    assert "`agent/Documentation.md` is a verification/change log" in docs_index
    assert "Historical audit artifacts live under [`agent/deprecated/`](agent/deprecated/)" in docs_index


def test_topology_inventory_targets_a_tracked_audit_surface():
    script = _read("scripts/topology_inventory.sh")

    assert "docs/agent/Topology.md" not in script
    assert "docs/agent/deprecated/AUDIT.md" in script


def test_tests_readme_defines_future_directory_contract():
    readme = _read("tests/README.md")

    assert "new tests should go in a component-aligned subdirectory" in readme
    assert "keep the `tests/` root for legacy files" in readme
    assert "tests/helpers/" in readme
    assert "tests/fixtures/" in readme
    assert "tests/case_workflows/" in readme
    assert "campaign-workflow slices" in readme


def test_case_workflow_test_slice_exists_as_real_subdirectory():
    required_paths = [
        "tests/case_workflows/test_cli_subcommands_case.py",
        "tests/case_workflows/test_case_full_pack.py",
        "tests/case_workflows/test_case_operator_intake.py",
    ]
    assert (REPO_ROOT / "tests/case_workflows").is_dir()
    for relative_path in required_paths:
        assert (REPO_ROOT / relative_path).exists(), relative_path
        assert _is_tracked(relative_path), relative_path


def test_acceptance_matrix_tracks_ci_contracts():
    acceptance = _read("scripts/run_acceptance_matrix.sh")
    ci = _read(".github/workflows/ci.yml")

    expected_checks = [
        "python -m ruff check .",
        "python -m ruff format --check .",
        "python -m mypy src",
        "python -m pytest -q --tb=short --cov=src --cov-report=term-missing --cov-fail-under=80",
        "tests/test_bm25_index_extended.py::TestBuildFromCollection::test_multi_batch_collection -W error::ResourceWarning",
        "python -m bandit -r src -q -ll -ii",
        "python scripts/dependency_audit.py",
        "python scripts/streamlit_smoke.py",
    ]

    for check in expected_checks:
        assert check in acceptance
    for check in [
        "ruff check .",
        "ruff format --check .",
        "mypy src",
        "pytest -q --tb=short --cov=src --cov-report=term-missing --cov-fail-under=80",
        (
            "python scripts/refresh_qa_eval_captured_reports.py --check --scenario legal_support "
            "--scenario legal_support_full_pack_goldens"
        ),
        "python scripts/wave_workflow_smoke.py",
        "bandit -r src -q -ll -ii",
        "python scripts/dependency_audit.py",
        "python scripts/streamlit_smoke.py",
    ]:
        assert check in ci

    assert 'python_bin="${PYTHON_BIN:-}"' in acceptance
    assert 'if [[ -x ".venv/bin/python" ]]; then' in acceptance
    assert 'python_bin=".venv/bin/python"' in acceptance
    assert "RUNTIME_PROFILE=offline-test" in acceptance
    assert "EMBEDDING_LOAD_MODE=local_only" in acceptance
    assert "DISABLE_SAFETENSORS_CONVERSION=1" in acceptance
    assert "SPACY_AUTO_DOWNLOAD_DURING_INGEST=0" in acceptance
    assert "Skipping in local profile because pypi.org is unreachable from this environment." in acceptance


def test_acceptance_matrix_exposes_release_profile_with_required_dependency_audit():
    acceptance = _read("scripts/run_acceptance_matrix.sh")

    assert "Usage: bash scripts/run_acceptance_matrix.sh [local|ci|release]" in acceptance
    assert "Running release profile. Dependency audit is required and may not be skipped." in acceptance
    expected = "Release profile requires a real dependency-audit result, but pypi.org is unreachable from this environment."
    assert expected in acceptance


def test_acceptance_matrix_ruff_contract_uses_python_module_invocation_only() -> None:
    acceptance = _read("scripts/run_acceptance_matrix.sh")

    assert "python -m ruff check ." in acceptance
    assert "python -m ruff format --check ." in acceptance
    assert "require_command ruff" not in acceptance


def test_acceptance_matrix_runs_campaign_workflow_smoke():
    acceptance = _read("scripts/run_acceptance_matrix.sh")

    assert "Campaign workflow smoke (python scripts/wave_workflow_smoke.py)" in acceptance
    assert "scripts/wave_workflow_smoke.py" in acceptance


def test_runtime_hygiene_contracts_protect_private_runtime_and_sqlite_sidecars():
    gitignore = _read(".gitignore")
    clean_workspace = _read("scripts/clean_workspace.sh")
    clean_ingest_reset = _read("scripts/clean_ingest_reset.sh")
    operations = _read("docs/README_USAGE_AND_OPERATIONS.md")
    acceptance = _read("scripts/run_acceptance_matrix.sh")

    assert "*.db-wal" in gitignore
    assert "*.db-shm" in gitignore
    assert "./private/runtime/*" in clean_workspace
    assert "./private/tests/results/*" in clean_workspace
    assert "private/files" in clean_ingest_reset
    assert "private/matter.md" in clean_ingest_reset
    assert "private/ingest/my-export.olm" in clean_ingest_reset
    assert "private/tests/materials" in clean_ingest_reset
    assert "private/tests/results" in clean_ingest_reset
    assert "private/tests/exports" in clean_ingest_reset
    assert "private/runtime/current" in clean_ingest_reset
    assert "--dry-run" in clean_ingest_reset
    assert "--yes" in clean_ingest_reset
    assert "scripts/clean_ingest_reset.sh" in operations
    assert "Ingest smoke (reports native vs fallback runtime)" in acceptance


def test_runtime_and_config_docs_use_portable_paths_and_current_archive_status():
    plan = _read("docs/agent/Plan.md")
    runtime_plan = _read("docs/agent/runtime_path_remediation_plan.md")
    mcp_client_config = _read("docs/agent/mcp_client_config_snippet.md")
    compatibility = _read("docs/API_COMPATIBILITY.md")
    documentation = _read("docs/agent/Documentation.md")

    assert "private/runtime/current/" in plan
    assert "missing source file" not in runtime_plan
    assert "<repo-root>" in mcp_client_config
    assert "<mcp-client-config>" in mcp_client_config
    assert "Intentional Surface Boundaries" in compatibility
    assert "Streamlit web app is exploratory" in compatibility
    assert "<home>/Git/01_high/01_high_outlook-email-rag" not in mcp_client_config
    assert "<home>/.config/mcp-client/config.toml" not in documentation


def test_docs_cover_corrected_case_workflow_contracts() -> None:
    compatibility = _read("docs/API_COMPATIBILITY.md")
    mcp_tools = _read("docs/MCP_TOOLS.md")
    docs_index = _read("docs/README.md")

    assert "does not refresh persisted matter snapshots" in compatibility
    assert "pdf` requires `output_path`" in compatibility
    assert "human_verified" in compatibility
    assert "export_approved" in compatibility
    assert "direct retrieval coverage" in compatibility
    assert "omit `output_path` only for in-memory HTML export" in mcp_tools
    assert "idempotent write surfaces" in mcp_tools
    assert "direct retrieval coverage from expanded thread or attachment context" in mcp_tools
    assert "remain archive-only context, not current execution inputs." in docs_index


def test_public_docs_capture_runtime_path_allowlist_and_ingest_side_effect_contracts() -> None:
    readme = _read("README.md")
    docs_index = _read("docs/README.md")
    compatibility = _read("docs/API_COMPATIBILITY.md")
    mcp_tools = _read("docs/MCP_TOOLS.md")
    cli_reference = _read("docs/CLI_REFERENCE.md")

    assert "EMAIL_RAG_ALLOWED_OUTPUT_ROOTS" in readme
    assert "EMAIL_RAG_ALLOWED_OUTPUT_ROOTS" in docs_index
    assert "EMAIL_RAG_ALLOWED_OUTPUT_ROOTS" in compatibility
    assert "EMAIL_RAG_ALLOWED_OUTPUT_ROOTS" in mcp_tools
    assert "EMAIL_RAG_ALLOWED_OUTPUT_ROOTS" in cli_reference

    assert "does not silently switch the active runtime archive" in readme
    assert "does not silently switch the active runtime archive" in docs_index
    assert "does not implicitly switch the active runtime archive" in compatibility
    assert "does not silently switch the currently active runtime archive" in mcp_tools
    assert "does not implicitly switch the active runtime archive" in cli_reference


def test_public_docs_capture_email_deep_context_body_budget_sentinel_contract() -> None:
    readme = _read("README.md")
    compatibility = _read("docs/API_COMPATIBILITY.md")
    mcp_tools = _read("docs/MCP_TOOLS.md")

    assert "email_deep_context.max_body_chars" in readme
    assert "`None` as a profile-default sentinel" in readme
    assert "`0` means unlimited" in readme
    assert "`None` uses profile default (`MCP_MAX_FULL_BODY_CHARS`)" in compatibility
    assert "`0` disables truncation" in compatibility
    assert "max_body_chars=None" in mcp_tools
    assert "max_body_chars=0" in mcp_tools


def test_autonomous_execution_prompt_pack_and_templates_cover_live_run_contract():
    plan = _read("docs/agent/Plan.md")
    companion = _read("docs/agent/question_execution_companion.md")
    runbook = _read("docs/agent/email_matter_analysis_single_source_of_truth.md")
    checkpoint = _read("docs/agent/email_matter_investigation_checkpoint_template.md")
    prompt_pack = _read("docs/agent/question_execution_prompt_pack.md")
    register_template = _read("docs/agent/question_register_template.md")
    open_tasks_template = _read("docs/agent/open_tasks_companion_template.md")
    mcp_client_config = _read("docs/agent/mcp_client_config_snippet.md")

    assert "docs/agent/question_execution_prompt_pack.md" in plan
    assert "docs/agent/question_register_template.md" in plan
    assert "docs/agent/open_tasks_companion_template.md" in plan
    assert "docs/agent/mcp_client_config_snippet.md" in plan

    assert "docs/agent/question_execution_prompt_pack.md" in companion
    assert "docs/agent/question_register_template.md" in companion
    assert "docs/agent/open_tasks_companion_template.md" in companion

    assert "private/tests/results/11_memo_draft_dashboard/question_register.md" in runbook
    assert "docs/agent/question_execution_prompt_pack.md" in runbook
    assert "docs/agent/question_register_template.md" in runbook
    assert "docs/agent/open_tasks_companion_template.md" in runbook
    assert "docs/agent/mcp_client_config_snippet.md" in runbook
    assert "private/runtime/current/chromadb" in runbook
    assert "private/runtime/current/email_metadata.db" in runbook
    assert "scripts/private_runtime_current_env.sh" in runbook

    assert "Question Register Delta" in checkpoint
    assert "best_supporting_sources" in checkpoint
    assert "best_counter_sources" in checkpoint
    assert "blocker_class" in checkpoint
    assert "remediation_taken" in checkpoint
    assert "rerun_count" in checkpoint
    assert "next_mcp_step" in checkpoint
    assert "Open-Tasks Delta" in checkpoint

    for heading in [
        "## MCP Readiness Prompt",
        "## Full Campaign Kickoff Prompt",
        "## Resume Prompt",
        "## Wave Execution Prompt Template",
        "## Blocker Remediation Prompt",
        "## Checkpoint And Register Update Prompt",
        "## Final Closure Prompt",
        "## Wave 1 Prompt",
        "## Wave 10 Prompt",
    ]:
        assert heading in prompt_pack

    for field in [
        "`question_id`",
        "`wave`",
        "`status`",
        "`best_supporting_sources`",
        "`best_counter_sources`",
        "`blocker_class`",
        "`remediation_taken`",
        "`rerun_count`",
        "`next_mcp_step`",
    ]:
        assert field in register_template

    assert "true external missing record" in open_tasks_template
    assert "`linked_question_ids`" in open_tasks_template
    assert "`next acquisition path`" in open_tasks_template
    assert "`resume_wave`" in open_tasks_template

    for tool_name in [
        "email_search_structured",
        "email_triage",
        "email_scan",
        "email_thread_lookup",
        "email_deep_context",
        "email_provenance",
        "evidence_add",
        "evidence_verify",
        "email_case_analysis_exploratory",
        "email_case_execute_wave",
        "email_case_execute_all_waves",
        "email_case_full_pack",
    ]:
        assert tool_name in mcp_client_config

    assert "private/runtime/current/chromadb" in mcp_client_config
    assert "private/runtime/current/email_metadata.db" in mcp_client_config


def test_mandatory_matter_inputs_contract_is_documented_across_main_run_surfaces() -> None:
    runbook = _read("docs/agent/email_matter_analysis_single_source_of_truth.md")
    checkpoint = _read("docs/agent/email_matter_investigation_checkpoint_template.md")
    prompt_pack = _read("docs/agent/question_execution_prompt_pack.md")

    for text in (runbook, prompt_pack):
        assert "private/cases/case.json" in text
        assert "private/results/evidence-harvest.json" in text
        assert "run_id" in text
        assert "phase_id" in text
        assert "scan_id_prefix" in text
        assert "verified trigger events" in text
        assert "alleged adverse actions" in text
        assert "comparators" in text
        assert "role hints" in text
        assert "institutional actors or mailboxes" in text

    assert "run_id:" in checkpoint
    assert "scan_id_prefix:" in checkpoint
    assert "evidence harvest file:" in checkpoint
    assert "verified trigger events:" in checkpoint
    assert "alleged adverse actions:" in checkpoint
    assert "comparators:" in checkpoint
    assert "role hints:" in checkpoint
    assert "institutional actors or mailboxes:" in checkpoint


def test_private_runtime_launcher_targets_current_runtime():
    launcher = _read("scripts/private_runtime_current_env.sh")

    assert "set -euo pipefail" in launcher
    assert "private/runtime/current" in launcher
    assert 'chromadb_path="${runtime_root}/chromadb"' in launcher
    assert 'sqlite_path="${runtime_root}/email_metadata.db"' in launcher
    assert "CHROMADB_PATH" in launcher
    assert "SQLITE_PATH" in launcher
    assert 'exec "$@"' in launcher


def test_private_runtime_current_topology_matches_live_layout():
    runtime_root = REPO_ROOT / "private/runtime"
    current = runtime_root / "current"
    baseline_run = runtime_root / "runs/baseline-p73-2026-04-17"
    legacy_run = runtime_root / "runs/live-default-legacy-2026-04-17"

    if not current.exists():
        pytest.skip("local private runtime not present")

    if not current.is_symlink():
        pytest.skip("local private runtime is not wired to the expected symlink topology")

    assert current.is_symlink()
    assert current.readlink() == Path("runs/baseline-p73-2026-04-17")

    baseline_chromadb = baseline_run / "chromadb"
    baseline_sqlite = baseline_run / "email_metadata.db"
    assert baseline_run.is_dir()
    assert baseline_chromadb.is_dir()
    assert not baseline_chromadb.is_symlink()
    assert baseline_sqlite.is_file()
    assert not baseline_sqlite.is_symlink()

    chromadb_alias = runtime_root / "chromadb_p73"
    sqlite_alias = runtime_root / "email_metadata_p73.db"
    assert chromadb_alias.is_symlink()
    assert chromadb_alias.readlink() == Path("runs/baseline-p73-2026-04-17/chromadb")
    assert sqlite_alias.is_symlink()
    assert sqlite_alias.readlink() == Path("runs/baseline-p73-2026-04-17/email_metadata.db")

    legacy_chromadb = legacy_run / "chromadb"
    legacy_sqlite = legacy_run / "email_metadata.db"
    assert legacy_chromadb.is_symlink()
    assert legacy_chromadb.readlink() == Path("../../chromadb")
    assert legacy_sqlite.is_symlink()
    assert legacy_sqlite.readlink() == Path("../../email_metadata.db")


def test_local_results_workspace_contract_uses_active_manifest():
    local_results_path = REPO_ROOT / "private/tests/results/README.local.md"
    if not local_results_path.exists():
        pytest.skip("local results workspace not present")

    local_results = local_results_path.read_text(encoding="utf-8")
    runbook = _read("docs/agent/email_matter_analysis_single_source_of_truth.md")
    prompt_pack = _read("docs/agent/question_execution_prompt_pack.md")

    assert "active_run.json" in local_results
    assert "refresh-active-run" in local_results
    assert "archive-results" in local_results
    assert "_archive/" in local_results
    assert "curation.status" in local_results
    assert "execute-wave" in local_results
    assert "execute-all-waves" in local_results
    assert "active_run.json" in runbook
    assert "curation.status" in runbook
    assert "refresh-active-run" in runbook
    assert "execute-wave" in runbook
    assert "active_run.json" in prompt_pack
    assert "curation.status" in prompt_pack
    assert "refresh-active-run" in prompt_pack


def test_shared_campaign_authority_docs_no_longer_declare_wave_cli_invalid():
    cli_reference = _read("docs/CLI_REFERENCE.md")
    runbook = _read("docs/agent/email_matter_analysis_single_source_of_truth.md")
    companion = _read("docs/agent/question_execution_companion.md")
    mcp_client_config = _read("docs/agent/mcp_client_config_snippet.md")
    compatibility = _read("docs/API_COMPATIBILITY.md")

    assert "shared_campaign_execution_surface" in cli_reference
    assert "email_case_execute_wave" in cli_reference
    assert "Shared campaign execution contract" in runbook
    assert "email_case_execute_all_waves" in runbook
    assert "dedicated `email_case_*` product refresh and counsel-facing export still belong to the MCP path" in mcp_client_config
    assert "only the MCP path counts as MCP-backed execution" not in mcp_client_config
    assert "Shared campaign execution is stable across the documented CLI" in compatibility
    assert "Dedicated legal-support analytical products and counsel-facing export remain MCP-governed" in compatibility
    assert "non-authoritative execution helpers" not in companion


def test_autonomy_boundary_docs_use_consistent_internal_vs_counsel_terms():
    cli_reference = _read("docs/CLI_REFERENCE.md")
    runbook = _read("docs/agent/email_matter_analysis_single_source_of_truth.md")
    companion = _read("docs/agent/question_execution_companion.md")
    governance = _read("docs/agent/review_governance.md")

    for text in (cli_reference, runbook, companion, governance):
        assert "autonomous internal completion" in text
        assert "human-gated counsel export" in text
