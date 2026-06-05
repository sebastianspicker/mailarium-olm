from __future__ import annotations

import re
import tomllib

from .helpers.repo_contracts import _mcp_tool_count, _read


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


def test_readme_routes_real_mailboxes_into_private_workspace():
    readme = _read("README.md")
    assert "private/ingest/example-export.olm" in readme
    assert "`private/` is ignored by Git" in readme
    assert "Keep tracked `data/` and `tests/fixtures/` content sanitized." in readme
    assert "private/runtime/current/chromadb" in readme
    assert "private/runtime/current/email_metadata.db" in readme


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
    assert "Historical audit artifacts live under" in docs_index
    assert "[`archive/2026-05-16-remediation-closure/`](archive/2026-05-16-remediation-closure/)" in docs_index


def test_tests_readme_defines_future_directory_contract():
    readme = _read("tests/README.md")

    assert "new tests should go in a component-aligned subdirectory" in readme
    assert "keep the `tests/` root for legacy files" in readme
    assert "tests/helpers/" in readme
    assert "tests/fixtures/" in readme
    assert "tests/case_workflows/" in readme
    assert "campaign-workflow slices" in readme


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
    docs = _autonomous_execution_docs()
    _assert_autonomous_doc_routes(docs)
    _assert_checkpoint_contract(docs["checkpoint"])
    _assert_prompt_pack_headings(docs["prompt_pack"])
    _assert_question_register_fields(docs["register_template"])
    _assert_open_tasks_fields(docs["open_tasks_template"])
    _assert_mcp_client_config_tools(docs["mcp_client_config"])


def _autonomous_execution_docs() -> dict[str, str]:
    return {
        "plan": _read("docs/agent/Plan.md"),
        "companion": _read("docs/agent/question_execution_companion.md"),
        "runbook": _read("docs/agent/email_matter_analysis_single_source_of_truth.md"),
        "checkpoint": _read("docs/agent/email_matter_investigation_checkpoint_template.md"),
        "prompt_pack": _read("docs/agent/question_execution_prompt_pack.md"),
        "register_template": _read("docs/agent/question_register_template.md"),
        "open_tasks_template": _read("docs/agent/open_tasks_companion_template.md"),
        "mcp_client_config": _read("docs/agent/mcp_client_config_snippet.md"),
    }


def _assert_autonomous_doc_routes(docs: dict[str, str]) -> None:
    for target in [
        "docs/agent/question_execution_prompt_pack.md",
        "docs/agent/question_register_template.md",
        "docs/agent/open_tasks_companion_template.md",
    ]:
        assert target in docs["plan"]
        assert target in docs["companion"]
        assert target in docs["runbook"]
    assert "docs/agent/mcp_client_config_snippet.md" in docs["plan"]
    assert "docs/agent/mcp_client_config_snippet.md" in docs["runbook"]
    assert "private/tests/results/11_memo_draft_dashboard/question_register.md" in docs["runbook"]
    assert "scripts/private_runtime_current_env.sh" in docs["runbook"]
    _assert_runtime_paths(docs["runbook"])


def _assert_runtime_paths(text: str) -> None:
    assert "private/runtime/current/chromadb" in text
    assert "private/runtime/current/email_metadata.db" in text


def _assert_checkpoint_contract(checkpoint: str) -> None:
    for marker in [
        "Question Register Delta",
        "best_supporting_sources",
        "best_counter_sources",
        "blocker_class",
        "remediation_taken",
        "rerun_count",
        "next_mcp_step",
        "Open-Tasks Delta",
    ]:
        assert marker in checkpoint


def _assert_prompt_pack_headings(prompt_pack: str) -> None:
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


def _assert_question_register_fields(register_template: str) -> None:
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


def _assert_open_tasks_fields(open_tasks_template: str) -> None:
    assert "true external missing record" in open_tasks_template
    assert "`linked_question_ids`" in open_tasks_template
    assert "`next acquisition path`" in open_tasks_template
    assert "`resume_wave`" in open_tasks_template


def _assert_mcp_client_config_tools(mcp_client_config: str) -> None:
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

    _assert_runtime_paths(mcp_client_config)


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
