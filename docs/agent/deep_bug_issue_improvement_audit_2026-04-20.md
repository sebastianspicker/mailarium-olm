# Deep Bug, Issue, And Improvement Audit

Date: 2026-04-20

Status: `read-only-audit`

Remediation status:

- `C1` fixed locally: Git history was rewritten with synthetic replacements, `origin` was restored, and `python scripts/privacy_scan.py --tracked-only --include-history --json` returns `[]`.
- `C2` fixed: default export roots are private-only.
- `C3` fixed: case CLI and case-input preparation now use shared path validators.
- `C4` fixed: dependency audit now runs through the bounded `scripts/dependency_audit.py` wrapper in CI and the acceptance matrix.
- `C5` remains a staged maintainability refactor: the LOC contract passes, including untracked-file coverage, but large maintained modules still rely on explicit exemptions.
- `C6` fixed as a regression gate: the acceptance matrix now includes the BM25 ResourceWarning warning-as-error probe.
- `C7` fixed: the runtime cleanup policy now selects preservation of verified evidence, harvested candidates, and custody history before clean ingest.

Scope:

- current workspace state, including untracked files
- private runtime/data folders treated as out of scope for content inspection
- dirty worktree intentionally ignored as requested; no unrelated cleanup or revert attempted
- public/release trust boundaries, privacy posture, export paths, CLI/MCP path handling, verification health, and maintainability contracts

## Executive Verdict

The current file tree passes the normal static, test, security, and current-content
privacy gates that were run in this pass. The previous high-risk MCP ingest and
tracked-file overwrite findings are no longer reproduced: `/etc/hosts` and
`/etc/passwd` are rejected by `EmailIngestInput`, and tracked files such as
`README.md` and `src/config.py` are rejected by export path validation.

The repository is not publication-clean at the Git-history level. The
content-aware history privacy scan now reports historical privacy markers by
category and path. That is the dominant release blocker if this repo is intended
to be pushed or advertised as fully synthetic.

## Verification Matrix

- `ruff check .`
  - Result: PASS
  - `All checks passed!`
- `ruff format --check .`
  - Result: PASS
  - `637 files already formatted`
- `python -m mypy src`
  - Result: PASS
  - `Success: no issues found in 247 source files`
  - Mypy still notes that some untyped function bodies are not checked unless stricter flags are used.
- `python -m bandit -r src -q -ll -ii`
  - Result: PASS
  - no findings under the configured policy
- `pytest -q`
  - Result: PASS
  - `3305 passed, 3 skipped`
- `python scripts/privacy_scan.py --json`
  - Result: PASS
  - current tracked and untracked scan returned `[]`
- `python scripts/privacy_scan.py --tracked-only --json`
  - Result: PASS
  - tracked current scan returned `[]`
- `python scripts/privacy_scan.py --tracked-only --include-history --json`
  - Result: FAIL_WITH_FINDINGS
  - 214 history findings by category/path only:
    - 18 `history-live-corpus-marker`
    - 1 `history-local-absolute-path`
    - 99 `history-non-reserved-email-domain`
    - 28 `history-private-matter-marker`
    - 68 `history-private-person-or-org-marker`
- `shellcheck scripts/*.sh`
  - Result: PASS
- `bash scripts/run_acceptance_matrix.sh local`
  - Result: PASS
  - included ruff, format, mypy, coverage-enforced pytest, legal-support artifact contracts, legal-support smoke tests, ingest smoke, campaign workflow smoke, CLI help probes, Streamlit sandbox-aware smoke, Bandit
  - local dependency audit was skipped because `pypi.org` was unreachable from this environment
- `PYTHONTRACEMALLOC=1 pytest -q tests/test_bm25_index_extended.py::TestBuildFromCollection::test_multi_batch_collection -W error::ResourceWarning`
  - Result: PASS
  - the ResourceWarning seen once in the full acceptance matrix did not reproduce in the targeted warning-as-error test

## Findings

### AUD-2026-04-20-C1: Git History Still Contains Privacy Markers

Severity: high

Affected boundary:

- public repository publication
- privacy guarantee that the repo is synthetic-only
- historical clone/fork surfaces

Evidence:

- Current working-tree privacy scans pass:
  - `python scripts/privacy_scan.py --json` returned `[]`.
  - `python scripts/privacy_scan.py --tracked-only --json` returned `[]`.
- History scan fails:
  - `python scripts/privacy_scan.py --tracked-only --include-history --json`
  - exit code: `1`
  - finding count: `214`
- Category distribution:
  - 18 `history-live-corpus-marker`
  - 1 `history-local-absolute-path`
  - 99 `history-non-reserved-email-domain`
  - 28 `history-private-matter-marker`
  - 68 `history-private-person-or-org-marker`
- Example affected historical paths include current public-facing files and docs/goldens such as:
  - `README.md`
  - `LICENSE`
  - `docs/CLI_REFERENCE.md`
  - `docs/agent/qa_eval_questions.*.json`
  - `docs/agent/legal_support_full_pack_golden.*.json`
  - `docs/agent/prompt_fixture.*.md`

Impact:

- A clean current tree is not enough for public release if old blobs remain
  reachable through Git history.
- A clone, fork, tag, or GitHub history view can still expose categories that
  point back to private actors, non-synthetic source usage, local paths, or
  private matter context.
- The scanner intentionally reports only category/path evidence here; it should
  not print matched private terms into logs or docs.

Minimal remediation:

- Decide whether the public/release branch requires destructive history rewrite.
- If yes, perform it in an isolated curated clone with immutable backup first.
- After rewrite, run all three privacy gates:
  - current full tree: `python scripts/privacy_scan.py --json`
  - tracked current tree: `python scripts/privacy_scan.py --tracked-only --json`
  - tracked history: `python scripts/privacy_scan.py --tracked-only --include-history --json`
- Only declare "synthetic-only public history" after the history gate returns `[]`.

### AUD-2026-04-20-C2: Default Export Roots Still Include Public/Sanitized Surfaces

Severity: medium

Affected boundary:

- evidence/dossier/report export paths
- accidental publication of generated artifacts
- private/public data separation

Evidence:

- `src/repo_paths.py` sets default output roots to:
  - `private`
  - `data`
  - `docs/screenshots`
- Tracked files are now rejected, which is good:
  - `EmailExportInput(uid="uid-1", output_path="README.md")` rejects.
  - `EvidenceExportInput(output_path="src/config.py")` rejects.
- But export models still accept non-tracked paths under public-ish roots:
  - `EmailExportInput(uid="uid-1", output_path="data/live-export.html")` accepts.
  - `EmailExportInput(uid="uid-1", output_path="docs/screenshots/email-export.html")` accepts.
  - `EvidenceExportInput(output_path="data/live-export.html")` accepts.
  - `EvidenceExportInput(output_path="docs/screenshots/email-export.html")` accepts.

Impact:

- A user or MCP caller can still route sensitive evidence/dossier/export output
  into `data/` or `docs/screenshots/`.
- Those roots are plausible publication/documentation surfaces. A later `git add`
  or docs packaging step could accidentally expose private matter content even
  though tracked-file overwrite protection is in place.

Minimal remediation:

- Make `private` or `private/exports` the only default export root for
  evidence, dossier, email, and legal-support outputs.
- Move `data` and `docs/screenshots` behind explicit opt-in environment
  variables or command flags for synthetic fixtures/screenshots only.
- Add regression tests proving sensitive export models reject:
  - `data/*.html`
  - `docs/screenshots/*.html`
  - tracked files such as `README.md`
  - source files such as `src/config.py`

### AUD-2026-04-20-C3: Case CLI And Preparation Script Bypass Shared Path Validators

Severity: medium

Affected boundary:

- case-input preparation
- case workflow CLI output
- private matter artifact routing
- source-tree integrity during analyst workflows

Evidence:

- `scripts/prepare_case_inputs.py` reads and writes direct filesystem paths:
  - `_read_json()` uses `Path(path).expanduser().read_text(...)`.
  - `_write_json()` uses `Path(path).expanduser()` and `write_text(...)`.
  - `--case-json-out` and `--overrides-out` are not passed through
    `validate_new_output_path()`.
- `src/cli_commands_case.py` writes direct CLI output paths:
  - `_write_text_or_exit()` calls `Path(path).write_text(...)`.
  - It is used by case analysis, wave execution, full-pack, and related case CLI
    output paths.
- The safer primitives already exist in `src/repo_paths.py`:
  - `validate_local_read_path()`
  - `validate_output_path()`
  - `validate_new_output_path()`

Impact:

- Case JSON and rendered case workflow outputs can be written to arbitrary paths
  accepted by the local process, including tracked project files if the operator
  gives the wrong path.
- This is lower risk than the MCP boundary because it is local CLI use, but it is
  still a real private-artifact routing problem in a repo whose core workflow
  handles sensitive evidence.

Minimal remediation:

- Use `validate_local_read_path()` for `--preflight` and `--case-json` when the
  input is expected to come from repo-managed private/data roots.
- Use `validate_new_output_path()` for `--case-json-out`, `--overrides-out`, and
  case CLI `--output` paths.
- Create parents only after validation.
- Add tests for:
  - accepting `private/cases/case.json`
  - accepting `private/results/*.json`
  - rejecting `README.md`
  - rejecting `src/*.py`
  - rejecting absolute paths outside allowed roots

### AUD-2026-04-20-C4: Dependency Audit Tooling Can Hang Outside The Matrix

Severity: medium

Affected boundary:

- release verification
- CI/local reproducibility
- security audit completeness

Evidence:

- Direct command attempted:
  - `python -m pip_audit -r requirements.txt --ignore-vuln CVE-2026-4539`
- In this restricted environment it hung for more than six minutes while spawning
  a temporary pip installation process.
- The process had to be terminated manually.
- `scripts/run_acceptance_matrix.sh local` has a connectivity preflight and
  skipped dependency audit when `pypi.org` was unreachable.
- `scripts/run_acceptance_matrix.sh release` correctly fails if `pypi.org` is
  unreachable, but `run_dependency_audit()` itself has no timeout around the
  actual pip-audit call.

Impact:

- A direct dependency audit can block an audit/release session indefinitely.
- If operators bypass the acceptance matrix, dependency status becomes unclear.
- In CI, a network stall could consume job time before failing.

Minimal remediation:

- Add a bounded wrapper for dependency audit, for example `timeout 180s`.
- Route docs and release checklists through `bash scripts/run_acceptance_matrix.sh release`
  instead of recommending the raw `pip_audit` command.
- Consider adding a lockfile or local vulnerability database strategy if offline
  verification is a hard requirement.

### AUD-2026-04-20-C5: LOC Contract Still Allows Large Maintained Modules

Severity: low-to-medium

Affected boundary:

- maintainability
- code review quality
- regression risk in shared workflow code

Evidence:

- Tracked files above 800 lines include:
  - `src/tools/search_answer_context_runtime.py`: 1900 lines
  - `src/qa_eval_scoring_helpers.py`: 1256 lines
  - `src/multi_source_case_bundle_helpers.py`: 1104 lines
  - `src/ingest_pipeline.py`: 980 lines
  - `tests/_ingest_pipeline_core_cases.py`: 929 lines
  - `src/db_evidence.py`: 916 lines
  - `tests/test_repo_contracts.py`: 843 lines
  - `src/db_schema_migrations.py`: 833 lines
  - `src/matter_evidence_index_helpers.py`: 827 lines
  - `src/ingest_reingest.py`: 813 lines
  - `src/email_db.py`: 810 lines
- Current untracked files above 800 lines include:
  - `src/case_analysis_harvest.py`: 1713 lines
  - `docs/agent/legal_support_full_pack_golden.disability_participation_failures.json`: 942 lines
  - `docs/agent/legal_support_full_pack_golden.eingruppierung_task_withdrawal.json`: 867 lines
  - `docs/agent/legal_support_full_pack_golden.chronology_contradiction.json`: 849 lines

Impact:

- The LOC contract remains useful, but it is currently a debt ledger rather than
  a hard maintainability boundary.
- Large source modules concentrate too many workflow responsibilities in one
  review unit.
- Large untracked modules can enter the repo without being visible to the
  tracked-file contract until after staging.

Minimal remediation:

- Split the largest maintained modules by responsibility before adding more
  behavior:
  - answer-context runtime orchestration
  - QA scoring metrics
  - multi-source bundle assembly
  - ingest pipeline phases
  - evidence database access
- Add a dirty-worktree LOC audit helper that includes untracked source files.
- Treat large generated/golden JSON separately from maintained source code in
  the contract.

### AUD-2026-04-20-C6: One Acceptance-Matrix ResourceWarning Needs Watchdog Coverage

Severity: low

Affected boundary:

- warning hygiene
- long-suite reliability

Evidence:

- `bash scripts/run_acceptance_matrix.sh local` emitted one warning during the
  coverage-enforced test suite:
  - `tests/test_bm25_index_extended.py::TestBuildFromCollection::test_multi_batch_collection`
  - `src/bm25_index.py:150: ResourceWarning: unclosed database`
- Targeted reproduction did not fail:
  - `PYTHONTRACEMALLOC=1 pytest -q tests/test_bm25_index_extended.py::TestBuildFromCollection::test_multi_batch_collection -W error::ResourceWarning`
  - result: PASS

Impact:

- This is not a confirmed deterministic leak in the targeted test.
- It is still worth tracking because ResourceWarnings in full suites can hide
  real fixture cleanup mistakes.

Minimal remediation:

- Add a focused warning-as-error job for database-heavy tests if the warning
  recurs.
- If it reproduces, close the SQLite handle in the fixture/source path that
  creates the collection used by the BM25 multi-batch case.

### AUD-2026-04-20-C7: Runtime Cleanup Policy Still Has A Human Decision Gate

Severity: low

Affected boundary:

- destructive clean ingest planning
- legacy evidence preservation

Evidence:

- `docs/agent/runtime_path_remediation_plan.md` contains:
  - `TODO(human): [Legacy evidence preservation policy before clean ingest] -> [Choose what to import into the clean rebuilt SQLite once the new ingest is ready] -> [A import verified evidence items only / B import verified evidence plus harvested candidates and custody history / C start with empty evidence tables and rerun all campaign harvesting from scratch]`

Impact:

- This is an intentional hand-off, not a bug.
- It blocks fully automated cleanup of legacy runtime/evidence state because the
  preservation policy has real evidentiary consequences.

Minimal remediation:

- Keep this as `TODO(human)` until the preservation policy is chosen.
- Once chosen, update the plan and add a testable migration checklist.

## Non-Findings

- Current tracked and untracked privacy scan is clean.
- MCP ingest rejects `/etc/hosts` as `olm_path`.
- MCP ingest rejects `/etc/passwd` as `sqlite_path`.
- Export validation rejects tracked files such as `README.md` and `src/config.py`.
- Streamlit paths inspected in this pass use `html_escape()` before rendering
  email-derived values with `unsafe_allow_html=True`; no concrete XSS finding was
  confirmed in the sampled surfaces.
- Ruff, format check, Mypy, Bandit, ShellCheck, pytest, and the local acceptance
  matrix passed.
- The one BM25 ResourceWarning seen in the full matrix did not reproduce under a
  targeted warning-as-error run.

## Recommended Fix Order

1. Resolve `C1` before any public/release claim: either rewrite history or state
   explicitly that only the current tree is synthetic-clean.
2. Tighten default export roots (`C2`) so private exports cannot land in
   `data/` or `docs/screenshots/` without explicit opt-in.
3. Apply shared path validators to case CLI and preparation outputs (`C3`).
4. Bound dependency-audit execution (`C4`).
5. Split large maintained modules and add an untracked-file LOC gate (`C5`).
6. Track the ResourceWarning only if it recurs (`C6`).
7. Keep the runtime preservation `TODO(human)` visible until policy is chosen
   (`C7`).

VERDICT: FAIL_WITH_FINDINGS
