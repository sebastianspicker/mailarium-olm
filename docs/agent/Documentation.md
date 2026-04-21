# Documentation Log

Status: `public-synthetic`

Purpose:

- record verification and cleanup checkpoints that are safe for a public repository
- avoid storing local-only case facts, local absolute paths, personal names, or generated counsel artifacts
- keep detailed private run logs in the local private workspace, not in tracked docs

## 2026-04-20 publication-safety cleanup

### Scope

- added a path-only privacy scanner in `scripts/privacy_scan.py`
- added a repo contract test requiring the tracked publication surface to stay synthetic
- quarantined local private/runtime/generated artifacts outside the repository
- converted public examples and fixtures toward reserved-domain, role-based synthetic data
- renamed synthetic full-pack attendance fixtures away from private system names and regenerated dependent goldens

### Verification Plan

- `python scripts/privacy_scan.py --tracked-only --json`
  - Why: prove tracked files do not contain private artifacts or non-synthetic identifiers.
  - Gate type: publication-safety contract.
  - Result: PASS
    - output was an empty JSON list
- `python scripts/privacy_scan.py --include-history --json`
  - Why: report whether git history still contains risky paths that need a separate rewrite.
  - Gate type: history audit.
  - Result: PASS
    - output was an empty JSON list
- `python -m pytest -q --tb=short tests/test_repo_contracts.py`
  - Why: verify documentation and publication-safety contracts after cleanup.
  - Gate type: targeted regression.
  - Result: PASS
    - `41` passed
    - `2` skipped
- `python -m ruff check scripts/privacy_scan.py tests/test_repo_contracts.py`
  - Why: lint the new scanner and touched contract test.
  - Gate type: targeted lint.
  - Result: PASS
- `python -m ruff check .`
  - Why: lint the full repository after the synthetic-data rewrite touched many fixtures and expected strings.
  - Gate type: full lint.
  - Result: PASS
- `python -m ruff format --check scripts/privacy_scan.py tests/test_repo_contracts.py tests/_web_app_main_cases.py tests/test_relationship_analysis.py tests/test_triage_deep_context.py`
  - Why: verify formatting for the directly edited scanner and line-wrap fixes.
  - Gate type: targeted format check.
  - Result: PASS
- `python -m pytest -q --tb=short tests/test_repo_contracts.py tests/test_sanitization_shared.py tests/test_legal_support_exporter.py tests/test_qa_eval_cases.py`
  - Why: verify publication contracts, redaction behavior, legal-support export behavior, and QA fixture loading.
  - Gate type: targeted regression.
  - Result: PASS
    - `66` passed
    - `2` skipped
- `python scripts/refresh_qa_eval_captured_reports.py --check`
  - Why: verify regenerated synthetic QA reports and legal-support goldens match their source fixtures.
  - Gate type: captured-artifact contract.
  - Result: PASS
    - all scenarios reported `match`
- `python -m pytest -q --tb=short`
  - Why: verify the repository after synthetic fixture rewrites, generated-golden refreshes, and ingest transaction cleanup.
  - Gate type: full regression.
  - Result: PASS
    - `3296` passed
    - `3` skipped
    - `24` warnings
- `python -m src.cli --help`
  - Why: surface-probe the main CLI after public example and mailbox rewrites.
  - Gate type: CLI smoke.
  - Result: PASS
- `python -m src.cli case --help`
  - Why: surface-probe the case workflow CLI after public example and mailbox rewrites.
  - Gate type: CLI smoke.
  - Result: PASS

## 2026-04-20 public architecture and methods documentation

### Scope

- added `docs/ARCHITECTURE_AND_METHODS.md` as the public deep-dive for architecture, retrieval mathematics, evaluation methodology, and a synthetic end-to-end example
- linked the new guide from `README.md`, `docs/README.md`, and `docs/README_USAGE_AND_OPERATIONS.md`
- added repo-contract coverage for the new guide, including Mermaid and formula anchors
- replaced old public repository URL examples with neutral `example-org` metadata
- changed privacy-scan marker construction so prior sensitive marker strings do not appear literally in the scanner source

### Verification Plan

- `python scripts/privacy_scan.py --json`
  - Why: verify current tracked and untracked non-ignored files stay publication-safe.
  - Gate type: publication-safety contract.
  - Result: PASS
    - output was an empty JSON list
- `python scripts/privacy_scan.py --tracked-only --json`
  - Why: verify the tracked publication surface after adding the new public guide.
  - Gate type: publication-safety contract.
  - Result: PASS
    - output was an empty JSON list
- strict literal marker grep
  - Why: verify the current working tree no longer contains previous actor, institution, surname-substring, local-user-path, or sensitive workflow wording markers.
  - Gate type: publication-safety audit.
  - Result: PASS
    - no matches
- `python -m pytest -q --tb=short tests/test_repo_contracts.py`
  - Why: verify public documentation links and repo contracts.
  - Gate type: targeted regression.
  - Result: PASS
    - `41` passed
    - `2` skipped
- `python scripts/privacy_scan.py --include-history --json`
  - Why: verify risky path patterns in committed history.
  - Gate type: history-path audit.
  - Result: PASS
    - output was an empty JSON list
- `python -m ruff check .`
  - Why: full lint after docs, metadata, scanner, and contract-test changes.
  - Gate type: full lint.
  - Result: PASS
- `python -m ruff format --check .`
  - Why: verify repository formatting after scanner edits.
  - Gate type: full format check.
  - Result: PASS
    - `636` files already formatted
- `python -m pytest -q --tb=short`
  - Why: full regression after documentation contracts and scanner changes.
  - Gate type: full regression.
  - Result: PASS
    - `3296` passed
    - `3` skipped
    - `24` warnings
- `python -m src.cli --help`
  - Why: surface-probe the main CLI after metadata and documentation changes.
  - Gate type: CLI smoke.
  - Result: PASS
- `python -m src.cli case --help`
  - Why: surface-probe the case workflow CLI after documentation changes.
  - Gate type: CLI smoke.
  - Result: PASS

## 2026-04-20 public docs proofread and source review

### Scope

- proofread and source-hardened the public documentation set:
  `README.md`, `docs/README.md`, `docs/ARCHITECTURE_AND_METHODS.md`,
  `docs/README_USAGE_AND_OPERATIONS.md`, `docs/CLI_REFERENCE.md`,
  `docs/MCP_TOOLS.md`, `docs/RUNTIME_TUNING.md`, and
  `docs/API_COMPATIBILITY.md`
- added `docs/agent/public_docs_source_review.md` as the persistent source and
  editorial review record
- replaced person-like public examples with role-based synthetic examples
- tied retrieval mathematics and interface claims to primary or official
  sources for BM25, ColBERT, BGE-M3, ChromaDB, MCP, Outlook `.olm`, and spaCy
  NER

### Verification Plan

- `python scripts/privacy_scan.py --json`
  - Why: verify current tracked and untracked non-ignored files stay publication-safe after the public docs proofread.
  - Gate type: publication-safety contract.
  - Result: PASS
    - output was an empty JSON list
- `python scripts/privacy_scan.py --tracked-only --json`
  - Why: verify tracked publication surface after replacing person-like examples with role-based synthetic examples.
  - Gate type: publication-safety contract.
  - Result: PASS
    - output was an empty JSON list
- `python scripts/privacy_scan.py --include-history --json`
  - Why: verify risky path patterns in committed history remain absent.
  - Gate type: history-path audit.
  - Result: PASS
    - output was an empty JSON list
- public-doc marker grep
  - Why: verify the reviewed public docs do not contain previous private/institution/person-like example markers.
  - Gate type: publication-safety audit.
  - Result: PASS
    - no matches
- `python -m pytest -q --tb=short tests/test_repo_contracts.py`
  - Why: verify public documentation links, publication-safety contracts, and updated synthetic example contract.
  - Gate type: targeted regression.
  - Result: PASS
    - `41` passed
    - `2` skipped
- `python -m ruff check .`
  - Why: full lint after docs and contract-test updates.
  - Gate type: full lint.
  - Result: PASS
- `python -m ruff format --check .`
  - Why: verify repository formatting after the docs/test changes.
  - Gate type: full format check.
  - Result: PASS
    - `636` files already formatted
- `python -m pytest -q --tb=short`
  - Why: full regression after public documentation proofread, source review log, and contract update.
  - Gate type: full regression.
  - Result: PASS
    - `3296` passed
    - `3` skipped
    - `24` warnings
- `python -m src.cli --help`
  - Why: surface-probe the main CLI after updating public examples and docs contracts.
  - Gate type: CLI smoke.
  - Result: PASS
- `python -m src.cli case --help`
  - Why: surface-probe the case workflow CLI after updating public examples and docs contracts.
  - Gate type: CLI smoke.
  - Result: PASS
- `python -m src.ingest --help`
  - Why: surface-probe the ingest CLI after tightening `.olm` documentation.
  - Gate type: CLI smoke.
  - Result: PASS

## 2026-04-20 deep repo audit and GitHub polish

### Scope

- added `docs/agent/repo_audit_2026-04-20.md` as the persistent audit record
- removed the provider-specific repo-agent GitHub workflow and prompt surface from `.github/`
- renamed the agent-specific MCP configuration guide to `docs/agent/mcp_client_config_snippet.md`
- updated public docs, advanced runbooks, and repo-contract tests to use a generic MCP-client surface
- neutralized provider-specific historical changelog wording and one temporary test fixture path
- set live GitHub topics for the public repo while keeping package and docs URLs privacy-neutral

### Verification Plan

- `python -m ruff check .`
  - Why: full lint after docs, workflow-surface, contract-test, and fixture-path changes.
  - Gate type: full lint.
  - Result: PASS
- `python -m ruff format --check .`
  - Why: verify repository formatting after the audit and GitHub-polish changes.
  - Gate type: full format check.
  - Result: PASS
    - `636` files already formatted
- `python scripts/privacy_scan.py --json`
  - Why: verify current tracked and untracked non-ignored files stay publication-safe.
  - Gate type: publication-safety contract.
  - Result: PASS
    - output was an empty JSON list
- `python scripts/privacy_scan.py --tracked-only --json`
  - Why: verify tracked publication surface after GitHub-workflow and docs cleanup.
  - Gate type: publication-safety contract.
  - Result: PASS
    - output was an empty JSON list
- `python scripts/privacy_scan.py --include-history --json`
  - Why: verify risky path patterns in committed history remain absent.
  - Gate type: history-path audit.
  - Result: PASS
    - output was an empty JSON list
- provider-specific public-surface marker grep
  - Why: verify public docs, GitHub config, packaging, changelog, and tests no longer expose the removed repo-agent workflow/client markers.
  - Gate type: publication-safety audit.
  - Result: PASS
    - no matches
- `python -m mypy src`
  - Why: full type check after the audit pass.
  - Gate type: full type check.
  - Result: PASS
    - `Success: no issues found in 247 source files`
    - only untyped-function checking notes were emitted
- `python -m bandit -r src -q -ll -ii`
  - Why: security scan after trust-boundary review.
  - Gate type: security scan.
  - Result: PASS
    - no failing Bandit issues under the configured policy
    - no Bandit `nosec` parser/tester warnings remain
- `python scripts/dependency_audit.py`
  - Why: dependency vulnerability audit for release readiness.
  - Gate type: dependency audit.
  - Result: PASS
    - `No known vulnerabilities found`
- `python -m pytest -q --tb=short tests/test_repo_contracts.py`
  - Why: verify docs, workflow-surface, and publication contracts.
  - Gate type: targeted regression.
  - Result: PASS
    - `42` passed
    - `2` skipped
- `python -m pytest -q --tb=short tests/test_matter_file_ingestion.py`
  - Why: verify the neutralized missing-path fixture still exercises degraded-source handling.
  - Gate type: targeted regression.
  - Result: PASS
    - `13` passed
- `python -m pytest -q --tb=short`
  - Why: full regression after audit, docs, workflow, and metadata changes.
  - Gate type: full regression.
  - Result: PASS
    - `3297` passed
    - `3` skipped
    - no warning summary
- `python -m src.cli --help`
  - Why: surface-probe the main CLI.
  - Gate type: CLI smoke.
  - Result: PASS
- `python -m src.cli case --help`
  - Why: surface-probe the case workflow CLI.
  - Gate type: CLI smoke.
  - Result: PASS
- `python -m src.ingest --help`
  - Why: surface-probe the ingest CLI.
  - Gate type: CLI smoke.
  - Result: PASS
- GitHub metadata read-back
  - Why: verify live GitHub polish after setting topics.
  - Gate type: live GitHub API read-back.
  - Result: PASS
    - default branch: `dev`
    - visibility: public
    - license: MIT
    - topics: `chromadb`, `ediscovery`, `email-search`, `local-first`, `mcp`, `outlook`, `privacy`, `python`, `rag`, `sqlite`

## 2026-04-20 residual audit closure

### Scope

- treated the remaining caveats as fix targets instead of release notes:
  dirty-worktree wording, full-suite warning noise, Bandit suppression noise,
  and residual provider-specific public markers
- removed provider-specific legacy operator names from tracked `.gitignore`,
  changelog wording, and repo-contract expectations
- added targeted pytest warning filters for stale flat-flag and SWIG/importlib
  deprecations
- pinned Visualized-BGE auto-download to the HuggingFace file commit used for
  `Visualized_m3.pth`
- narrowed dynamic SQL and Markup suppressions to exact audited expression lines

### Verification Plan

- `python -m pytest -q --tb=short tests/test_image_embedder.py tests/test_image_embedder_extended.py tests/test_evidence_exporter.py tests/test_email_db_analytics.py tests/test_db_queries_refactor_seams.py tests/test_db_evidence_refactor_seams.py tests/test_matter_workspace.py tests/test_qa_eval_live_deps.py`
  - Why: targeted regression for the touched image-download, HTML-export, DB-query, and live-eval surfaces.
  - Gate type: targeted regression.
  - Result: PASS
    - `96` passed
- `python -m pytest -q --tb=short tests/test_repo_contracts.py`
  - Why: verify public-surface and repository hygiene contracts after removing remaining provider-specific markers.
  - Gate type: targeted regression.
  - Result: PASS
    - `42` passed
    - `2` skipped
- public-surface marker grep over `.github README.md docs SECURITY.md pyproject.toml CHANGELOG.md .gitignore tests`
  - Why: verify provider-specific, institutional, and private-actor markers are absent from public docs, GitHub config, packaging, changelog, ignore rules, and tests.
  - Gate type: publication-safety audit.
  - Result: PASS
    - no matches
- `python -m bandit -r src -q -ll -ii`
  - Why: verify security scan after suppression hygiene and HuggingFace revision pin.
  - Gate type: security scan.
  - Result: PASS
    - no output
- `python -m ruff check .`
  - Why: full lint after code, docs, and contract changes.
  - Gate type: full lint.
  - Result: PASS
- `python -m ruff format --check .`
  - Why: full format check after final edits.
  - Gate type: full format check.
  - Result: PASS
    - `636` files already formatted
- `python scripts/privacy_scan.py --json`
  - Why: verify current working tree remains synthetic and private-artifact free.
  - Gate type: privacy scan.
  - Result: PASS
    - output was an empty JSON list
- `python scripts/privacy_scan.py --tracked-only --json`
  - Why: verify tracked publication surface remains synthetic and private-artifact free.
  - Gate type: privacy scan.
  - Result: PASS
    - output was an empty JSON list
- `python scripts/privacy_scan.py --include-history --json`
  - Why: verify history path scan remains clean under the repo's privacy scanner.
  - Gate type: privacy scan.
  - Result: PASS
    - output was an empty JSON list

## 2026-04-20 trust-boundary remediation

### Scope

- tightened MCP ingest validation so `olm_path` must be an allowlisted readable
  `.olm` file and runtime overrides must stay inside runtime roots
- removed the repository root from default output roots and rejected tracked
  repository files as export targets
- added shared no-overwrite validation for HTML/PDF, CSV, GraphML, report, and
  JSONL file writers
- changed default export destinations to `private/exports/...`
- extended `privacy_scan.py --include-history` from path-only checks to
  historical blob-content scanning without printing matched text
- updated the LOC contract to include untracked files in the dirty worktree

### Verification Plan

- `pytest -q tests/test_mcp_models_base.py tests/test_evidence_exporter.py tests/test_privacy_scan.py tests/test_repo_contracts.py::test_repo_maintained_files_stay_under_800_loc_threshold tests/test_cli_subcommands_evidence_report.py tests/test_report_generator.py::test_cli_generate_report_default tests/test_report_generator.py::test_cli_export_network_default tests/test_cli_integration.py::test_parse_args_generate_report_default tests/test_cli_integration.py::test_parse_args_export_network_default`
  - Why: targeted regression for input path validation, output overwrite guards,
    history-content scanning, LOC contract coverage, and CLI default paths.
  - Gate type: targeted regression.
  - Result: PASS
    - `53` passed
- `ruff check src/repo_paths.py src/mcp_models_base.py src/mcp_models_search.py src/formatting.py src/evidence_exporter.py src/report_generator.py src/network_analysis.py src/training_data_generator.py src/mcp_models_evidence.py src/mcp_models_analysis.py src/mcp_models_case_analysis_legal_support.py scripts/privacy_scan.py tests/test_mcp_models_base.py tests/test_evidence_exporter.py tests/test_privacy_scan.py tests/test_repo_contracts.py tests/test_cli_subcommands_evidence_report.py tests/test_report_generator.py tests/test_cli_integration.py tests/conftest.py tests/_mcp_tools_search_runtime_cases.py tests/_mcp_tools_validation_cases.py tests/test_tools_evidence_export_formats.py`
  - Why: lint the touched Python implementation and regression tests.
  - Gate type: targeted lint.
  - Result: PASS
- `ruff format --check src/repo_paths.py src/mcp_models_base.py src/mcp_models_search.py src/formatting.py src/evidence_exporter.py src/report_generator.py src/network_analysis.py src/training_data_generator.py src/mcp_models_evidence.py src/mcp_models_analysis.py src/mcp_models_case_analysis_legal_support.py scripts/privacy_scan.py tests/test_mcp_models_base.py tests/test_evidence_exporter.py tests/test_privacy_scan.py tests/test_repo_contracts.py tests/conftest.py tests/_mcp_tools_search_runtime_cases.py tests/_mcp_tools_validation_cases.py tests/test_tools_evidence_export_formats.py tests/test_cli_subcommands_evidence_report.py tests/test_report_generator.py tests/test_cli_integration.py`
  - Why: verify formatter cleanliness after the final privacy-scan and LOC-contract edits.
  - Gate type: targeted format check.
  - Result: PASS
    - `23` files already formatted
- `pytest -q`
  - Why: full regression suite after tightening shared path validation.
  - Gate type: full test suite.
  - Result: PASS
    - `3305` passed
    - `3` skipped
- `python scripts/privacy_scan.py --tracked-only --json`
  - Why: verify the current tracked publication surface remains synthetic and
    private-artifact free.
  - Gate type: privacy scan.
  - Result: PASS
    - output was an empty JSON list
- `python scripts/privacy_scan.py --tracked-only --include-history --json`
  - Why: verify the new history-content scanner runs against historical blobs.
  - Gate type: privacy scan.
  - Result: FAIL
    - the strengthened scanner now reports historical blob-content findings
      under `history-*` categories
    - no matched private text was printed; output contains categories and paths
      only
    - remediation requires a separate history-rewrite decision, not an
      in-place source patch

## 2026-04-20 follow-up remediation pass

### Scope

- rewrote local Git history with synthetic replacements and restored `origin`
- made default export roots private-only
- routed case CLI and `scripts/prepare_case_inputs.py` through shared local-read
  and new-output validators
- added bounded dependency audit wrapper `scripts/dependency_audit.py`
- routed CI and the acceptance matrix through the bounded dependency audit
  wrapper
- added a BM25 warning-as-error gate to the acceptance matrix
- resolved the legacy evidence preservation decision in
  `docs/agent/runtime_path_remediation_plan.md`
- fixed the LOC contract test's unclosed file handle

### Verification

- `ruff check .`
  - Why: full lint after trust-boundary and verification-script edits.
  - Gate type: full lint.
  - Result: PASS
- `ruff format --check .`
  - Why: full formatter check after final edits.
  - Gate type: full format check.
  - Result: PASS
    - `641` files already formatted
- `python -m mypy src`
  - Why: type-check changed source and adjacent model paths.
  - Gate type: full type check.
  - Result: PASS
    - `Success: no issues found in 247 source files`
- `pytest -q`
  - Why: full regression after path validation, history rewrite recovery, and
    moved test-path index restoration.
  - Gate type: full test suite.
  - Result: PASS
    - `3313` passed
    - `3` skipped
- `python scripts/privacy_scan.py --json`
  - Why: verify the restored dirty working tree remains current-content clean.
  - Gate type: privacy scan.
  - Result: PASS
    - output was an empty JSON list
- `python scripts/privacy_scan.py --tracked-only --include-history --json`
  - Why: verify rewritten Git history is category/path clean.
  - Gate type: history privacy scan.
  - Result: PASS
    - output was an empty JSON list
- `pytest -q tests/test_repo_contracts.py::test_repo_maintained_files_stay_under_800_loc_threshold -W error::ResourceWarning`
  - Why: verify the LOC contract no longer leaks file handles.
  - Gate type: targeted warning gate.
  - Result: PASS
- `python scripts/dependency_audit.py --timeout-seconds 1`
  - Why: verify the dependency audit wrapper has bounded failure behavior.
  - Gate type: timeout behavior probe.
  - Result: PASS
    - exited `124` with a timeout message instead of hanging

## 2026-04-20 core-four LOC refactor pass

### Scope

- split `src/tools/search_answer_context_runtime.py` into runtime lane,
  ranking, budget, search, candidate-row, and builder helpers
- split `src/qa_eval_scoring_helpers.py` into core, case, behavior, legal,
  Slice-A, and summary helpers
- split `src/multi_source_case_bundle_helpers.py` into common, linking,
  reliability, chronology, and source-normalization helpers
- split `src/case_analysis_harvest.py` into common, coverage, quality,
  expansion, and bundle helpers
- kept compatibility facades at the original import paths so existing private
  helper imports and monkeypatch paths continue to work
- removed the four refactored modules from the LOC-contract exemption set

### Verification

- `pytest -q tests/test_repo_contracts.py::test_repo_maintained_files_stay_under_800_loc_threshold`
  - Why: targeted acceptance check for the hard 800-line maintainability
    contract after removing the four exemptions.
  - Gate type: targeted contract test.
  - Result: PASS
- `ruff check .`
  - Why: full lint after splitting runtime and helper modules.
  - Gate type: full lint.
  - Result: PASS
- `ruff format --check .`
  - Why: full formatter check after final import and facade edits.
  - Gate type: full format check.
  - Result: PASS
    - `660` files already formatted
- `python -m mypy src`
  - Why: full type-check after adding compatibility facades and split helper
    modules.
  - Gate type: full type check.
  - Result: PASS
    - `Success: no issues found in 269 source files`
- `pytest -q tests/test_search_answer_context.py tests/test_search_answer_context_runtime_diversity.py tests/test_search_answer_context_case_scope.py tests/_mcp_tools_search_answer_context_core_cases.py tests/test_case_analysis_archive_harvest.py tests/test_case_analysis_archive_harvest_bundle.py tests/test_case_analysis_archive_harvest_runtime.py`
  - Why: targeted regression for answer-context runtime, monkeypatch-stable
    private runtime imports, and archive-harvest orchestration.
  - Gate type: targeted regression.
  - Result: PASS
    - `74` passed
- `pytest -q tests/test_qa_eval.py tests/test_qa_eval_scoring.py tests/test_qa_eval_slice_a_metrics.py tests/_qa_eval_scoring_tail_cases.py tests/test_multi_source_case_bundle.py tests/test_multi_source_case_bundle_linking.py tests/test_multi_source_case_bundle_sources.py tests/test_multi_source_case_bundle_chronology.py`
  - Why: targeted regression for QA scoring and multi-source case-bundle
    helper splits.
  - Gate type: targeted regression.
  - Result: PASS
    - `66` passed
- `pytest -q`
  - Why: full regression after final facade import and mypy-visibility edits.
  - Gate type: full test suite.
  - Result: PASS
    - `3313` passed
    - `3` skipped
- `python scripts/privacy_scan.py --json`
  - Why: verify the current working tree remains free of configured private
    markers after the refactor.
  - Gate type: privacy scan.
  - Result: PASS
    - output was an empty JSON list
- `python scripts/privacy_scan.py --tracked-only --include-history --json`
  - Why: verify historical tracked blobs remain clean after the refactor pass.
  - Gate type: history privacy scan.
  - Result: PASS
    - output was an empty JSON list

## 2026-04-20 GitHub cleanup and polish pass

### Scope

- replaced placeholder GitHub URLs with the canonical
  `https://github.com/sebastianspicker/outlook-email-rag` repository URL
- added lightweight issue and pull-request templates with synthetic-data
  privacy boundaries
- consolidated the public docs hub so advanced operator material routes through
  `docs/agent/README.md`
- aligned `SECURITY.md` with the bounded dependency-audit wrapper
- neutralized unpolished informal eval wording as `rapid review`
- added repo contracts for canonical URLs, GitHub templates, privacy-safe
  template content, and the advanced docs index

### Verification

- `pytest -q tests/test_repo_contracts.py`
  - Why: targeted contract check for public docs, GitHub templates, privacy
    boundaries, and repo metadata.
  - Gate type: targeted contract test.
  - Result: PASS
    - `44` passed
    - `2` skipped
- `ruff check .`
  - Why: full lint after test and docs-surface edits.
  - Gate type: full lint.
  - Result: PASS
- `ruff format --check .`
  - Why: full formatter check after repository contract edits.
  - Gate type: full format check.
  - Result: PASS
    - `660` files already formatted
- `python scripts/privacy_scan.py --json`
  - Why: verify the current working tree remains clean after GitHub-template
    and docs-surface changes.
  - Gate type: privacy scan.
  - Result: PASS
    - output was an empty JSON list
- `python scripts/privacy_scan.py --tracked-only --include-history --json`
  - Why: verify historical tracked blobs remain clean while the current
    publication surface changes.
  - Gate type: history privacy scan.
  - Result: PASS
    - output was an empty JSON list
- `pytest -q`
  - Why: full regression after updating repo contracts and touched eval
    artifacts.
  - Gate type: full test suite.
  - Result: PASS
    - `3315` passed
    - `3` skipped

## 2026-04-21 main CI answer-context budget fix

### Scope

- preserved compact behavioral candidate surfaces during answer-context budget
  trimming
- kept top-level `case_patterns` available for scoped behavioral answer-context
  responses instead of treating it as an optional removable sidecar
- added low-budget regression coverage for the CI failures where
  `language_rhetoric` and `case_patterns` disappeared from the JSON payload

### Verification

- `pytest -q --tb=short tests/test_search_answer_context_behavioral.py`
  - Why: targeted regression for the two failing CI behavioral answer-context
    tests and adjacent behavioral context cases.
  - Gate type: targeted regression.
  - Result: PASS
    - `8` passed
- `ruff check src/tools/search_answer_context_runtime_budgeting.py src/tools/search_answer_context_evidence_payloads.py tests/_search_answer_context_behavioral_language_cases.py tests/_search_answer_context_behavioral_reply_pattern_cases.py`
  - Why: targeted lint for touched source and test files.
  - Gate type: targeted lint.
  - Result: PASS
- `ruff format --check src/tools/search_answer_context_runtime_budgeting.py src/tools/search_answer_context_evidence_payloads.py tests/_search_answer_context_behavioral_language_cases.py tests/_search_answer_context_behavioral_reply_pattern_cases.py`
  - Why: targeted format check after applying `ruff format` to the touched
    budgeting module.
  - Gate type: targeted format check.
  - Result: PASS
    - `4` files already formatted
- `mypy src`
  - Why: full source type check after changing answer-context runtime helpers.
  - Gate type: full type check.
  - Result: PASS
    - `Success: no issues found in 270 source files`
- `ruff check .`
  - Why: full lint before committing the CI fix.
  - Gate type: full lint.
  - Result: PASS
- `ruff format --check .`
  - Why: full format check before committing the CI fix.
  - Gate type: full format check.
  - Result: PASS
    - `665` files already formatted
- `pytest -q --tb=short`
  - Why: full local regression before committing the CI fix.
  - Gate type: full test suite.
  - Result: PASS
    - `3359` passed
    - `3` skipped

## 2026-04-21 main CI captured-artifact stabilization

### Scope

- rounded QA average metrics to a stable precision so Python 3.11/3.12 do not
  disagree on serialized captured-report values
- refreshed captured QA reports and legal-support full-pack goldens after the
  answer-context budget-surface change
- redacted fixture-local attendance-system filenames from public full-pack
  golden projections so publication-surface privacy scans stay clean

### Verification

- `python scripts/refresh_qa_eval_captured_reports.py --check`
  - Why: exact captured-artifact contract that CI checks, expanded to all
    captured scenarios and full-pack goldens.
  - Gate type: captured artifact contract.
  - Result: PASS
    - all scenarios reported `match`
- `pytest -q --tb=short tests/test_qa_eval_captured_artifacts_refresh.py tests/test_qa_eval_core_artifacts.py tests/test_repo_contracts.py`
  - Why: targeted regression for the CI failures plus the publication-surface
    privacy contract.
  - Gate type: targeted regression.
  - Result: PASS
    - `52` passed
    - `2` skipped
- `python scripts/privacy_scan.py --tracked-only --json`
  - Why: verify refreshed public artifacts and projection code do not introduce
    publication-risk markers.
  - Gate type: privacy scan.
  - Result: PASS
    - output was an empty JSON list
- `ruff check src/legal_support_acceptance_projection.py src/qa_eval_scoring_core.py src/qa_eval_thresholds.py`
  - Why: targeted lint for touched source files.
  - Gate type: targeted lint.
  - Result: PASS
- `ruff format --check src/legal_support_acceptance_projection.py src/qa_eval_scoring_core.py src/qa_eval_thresholds.py`
  - Why: targeted format check for touched source files.
  - Gate type: targeted format check.
  - Result: PASS
    - `3` files already formatted
- `mypy src`
  - Why: full source type check after QA metric and projection helper changes.
  - Gate type: full type check.
  - Result: PASS
    - `Success: no issues found in 270 source files`
- `pytest -q --tb=short`
  - Why: full local regression before committing the captured-artifact fix.
  - Gate type: full test suite.
  - Result: PASS
    - `3359` passed
    - `3` skipped
